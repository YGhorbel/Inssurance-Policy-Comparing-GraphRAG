# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Multi-agent GraphRAG system for analyzing and comparing insurance regulations (focus: Tunisia + international). PDFs in MinIO → chunked/enriched → indexed in Qdrant → projected into a Neo4j knowledge graph → retrieved via vector+graph fusion → summarized by an LLM. Agents communicate over JSON-RPC (MCP) routed by `core.mcp.handler.mcp_registry`.

For the chronological record of revision work (Phase 0 RRF closure, Phase 1 engineering-integrity sweep, known gaps carried forward), see `docs/PHASE_LOG.md`.

## Running the stack

```bash
# 1. Infrastructure (MinIO :9000/:9001, Neo4j :7474/:7687, Qdrant :6333)
docker-compose up -d

# 2. Python deps
pip install -r requirements.txt

# 3. Env vars (read by core/llm/client.py and configs/config.yaml)
#    HF_TOKEN, QDRANT_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
#    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY

# 4. Backend (FastAPI + MCP registry, all agents auto-register on import)
uvicorn api.server:app --reload --host 0.0.0.0 --port 8001

# 5. UI (talks to the MCP endpoint at http://localhost:8001/mcp)
streamlit run ui/app.py
```

## Common commands

```bash
# Trigger ingestion via JSON-RPC (MinIO → Qdrant → Neo4j)
curl -X POST http://localhost:8001/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"ingest_documents","id":"1"}'

# Project Qdrant chunks into Neo4j
curl -X POST http://localhost:8001/graph/ingest

# Hybrid retrieval (RRF over vector + graph-driven chunk rankings)
curl -X POST http://localhost:8001/graph/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query":"compare auto insurance Tunisia France","top_k":5}'

# RRF smoke test
python3 evaluation/test_rrf_smoke.py
```

There is no full test suite, no linter config, and no build step. `.gitignore` masks ad-hoc `test_*.py` artifacts at the repo root, but the negation `!evaluation/test_*.py` keeps anything under `evaluation/` tracked.

## Architecture

The repo has one canonical pipeline: the MCP-based multi-agent stack rooted at `api/server.py` and `ui/app.py`. The previous direct ingestion path (`main.py`, root `app.py`, `query.py`, plus `ingestion/pipeline.py`, `graph/`, `models/`) has been retired to `legacy/` and is kept for historical reference only — do not import from it. The dirs `ingestion/` and `processing/` remain at the repo root but are now deprecated namespace directories holding three modules (`ingestion/pdf_loader.py`, `ingestion/minio_loader.py`, `processing/chunker.py`) still imported by `agents/analyzer/pipeline.py`; full migration under `agents/shared/` is deferred to Phase 2.

### MCP agent registry

`core/mcp/handler.py` exposes a single `mcp_registry` singleton. Every agent module registers tools at import time via `mcp_registry.register_tool(name, func)`. `agents/planner/agent.py` imports all other agents to force registration — adding a new agent means adding an import there. The FastAPI `/mcp` endpoint is a thin JSON-RPC adapter over the registry; tools may be sync or async and `handle_request` introspects which.

### Agent roles

- **`planner`** — `execute_pipeline(query)` (analyze → route to RAG or GraphRAG → summarize) and `ingest_pending_documents()` (orchestrates the full ingestion flow). Routes via `analyze_query`'s `classification` field (`"RAG"` vs `"GraphRAG"`).
- **`analyzer`** — `analyze_query` classifies user intent; `AnalyzerPipeline.process_file` does the heavy enrichment: summary, keywords, questions, requirements, policy/clause classification, embedding, then upsert to Qdrant.
- **`document_access`** — MinIO listing/download, PDF text extraction (`pypdf`), and JSON-file-backed metadata (`MetadataManager`).
- **`rag`** — Qdrant search + `rag_ingest_chunks`. Uses `agents/shared/chunking.py` (Chonkie semantic chunker).
- **`graph_rag`** — `GraphBuilder` (LLM → Cypher, validated against the 7-edge schema in `validator.py`), `QdrantToNeo4jIngestor` (Qdrant scroll → graph), `GraphRAG.retrieve` (Qdrant vector ranking + Neo4j-driven entity-to-chunk ranking → RRF fusion → LLM synthesis; see `agents/shared/fusion.py`).
- **`summarizer`** — Phase 1 answer synthesis + Phase 2 prompts (`summarize_comparison`, `summarize_gaps`, `summarize_recommendations`).

### LLM client

`core/llm/client.py::get_llm_client()` is the singleton entrypoint. It routes by environment:
- `LLM_PROVIDER=ollama` / `ollama_cloud` → `core/llm/ollama_client.py::OllamaClient` (Ollama-protocol HTTP, local daemon or Ollama Cloud). Configuration via `.env` keys `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`, `OLLAMA_MODEL`. Thinking-model chain-of-thought is always disabled (`think: false`) so reasoning models behave like instruction-following completion models.
- otherwise → `LiquidClient` (HuggingFace `transformers.pipeline`, in-process LLM weights, default `LiquidAI/LFM2-2.6B-Exp`).

Phase 2+ defaults to Ollama Cloud on this host because local LFM2 inference is CPU-bound and too slow for live iteration. New code must call `get_llm_client()` — never instantiate either client directly. The legacy 4-bit `FHClient` in `legacy/models/hf_client.py` is historical only.

### Enriched chunk schema (Qdrant payload)

`AnalyzerPipeline.process_file` produces this structure; `QdrantToNeo4jIngestor` and `GraphRAG.retrieve` both depend on these field names:

```
chunk_id, text, summary, keywords[], questions[],
country, policy_type, clause_type,
extracted_requirements[],
source: { document, page, section },
embedding[]
```

Qdrant collection name comes from `configs/config.yaml::qdrant.collection` (default `regulations_chunks`); vector size is inferred from `sentence-transformers/all-MiniLM-L6-v2` (384). The collection is auto-created on first run.

### Config

`configs/config.yaml` is the source of truth for endpoints, model id, and chunk params. Env vars override only where explicitly checked (`HF_TOKEN`, `QDRANT_URL`). Most agent constructors take `config_path="configs/config.yaml"` — relative path, so commands must be run from the repo root.

## Project conventions

- All Python imports assume the repo root is on `sys.path`. Entry points (`api/server.py`) append it explicitly; if you create a new entry point do the same.
- Agents print init banners on import (`print("X Agent initialized.")`) — this is the registration signal. Keep it.
- LLM responses are parsed with regex-extracted JSON (`re.search(r'\{.*\}', ..., re.DOTALL)`) and fallbacks. When adding new LLM-driven extractors, follow the same pattern in `AnalyzerPipeline._parse_json_from_llm` rather than failing hard.
- Qdrant client method names differ across versions — existing code wraps calls in try/except with fallbacks (`create_collection` → `recreate_collection`, `scroll` → `get`). Preserve this when extending.
- Temp PDFs are downloaded to `temp_*.pdf` in CWD (gitignored).
- The `legacy/` tree is not on the import path and must not be imported from new code; it exists for git-history traceability only.
