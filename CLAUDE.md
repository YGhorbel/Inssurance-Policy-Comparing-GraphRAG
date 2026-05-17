# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Multi-agent GraphRAG system for analyzing and comparing insurance regulations (focus: Tunisia + international). PDFs in MinIO → chunked/enriched → indexed in Qdrant → projected into a Neo4j knowledge graph → retrieved via vector+graph fusion → summarized by an LLM. Agents communicate over JSON-RPC (MCP) routed by `core.mcp.handler.mcp_registry`.

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

`app.py` at the repo root is a *different*, older Streamlit UI that drives the standalone `ingestion.pipeline.Pipeline` directly (no MCP, no Qdrant) — see "Two parallel pipelines" below before editing.

## Common commands

```bash
# Run the legacy direct ingestion pipeline (MinIO → chunks → Neo4j, no Qdrant)
python main.py

# Trigger MCP-based ingestion (Qdrant + Neo4j) via JSON-RPC
curl -X POST http://localhost:8001/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"ingest_documents","id":"1"}'

# Project Qdrant chunks into Neo4j
curl -X POST http://localhost:8001/graph/ingest

# GraphRAG retrieval fusion
curl -X POST http://localhost:8001/graph/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query":"compare auto insurance Tunisia France","top_k":5}'

# Direct CLI query against Neo4j (legacy path)
python query.py summarize "GDPR Article 12"
python query.py compare "Reg A" "Reg B"
```

There is no test suite, no linter config, and no build step — `.gitignore` excludes `test_*.py` and `check_gpu.py` as ad-hoc test artifacts.

## Architecture

### Two parallel pipelines (important)

The repo contains **two coexisting implementations** that both ingest PDFs but use different stacks. Edits to one do not affect the other.

| Pipeline | Entry | Stack | Used by |
|---|---|---|---|
| **MCP / multi-agent** (current) | `api/server.py` + `ui/app.py` | `agents/*` + `core/` + Qdrant + Neo4j | Streamlit chat, `/mcp` endpoint |
| **Legacy direct** | `main.py` + `app.py` (root) | `ingestion/` + `processing/` + `graph/` + `models/` | `python main.py`, root Streamlit |

The legacy pipeline writes Cypher directly from LLM output via `ingestion/graph_builder.py`; the MCP pipeline goes through Qdrant first and then `agents/graph_rag/qdrant_ingest.py` projects enriched chunks into Neo4j. New work should target the MCP pipeline unless explicitly asked otherwise.

### MCP agent registry

`core/mcp/handler.py` exposes a single `mcp_registry` singleton. Every agent module registers tools at import time via `mcp_registry.register_tool(name, func)`. `agents/planner/agent.py` imports all other agents to force registration — adding a new agent means adding an import there. The FastAPI `/mcp` endpoint is a thin JSON-RPC adapter over the registry; tools may be sync or async and `handle_request` introspects which.

### Agent roles

- **`planner`** — `execute_pipeline(query)` (analyze → route to RAG or GraphRAG → summarize) and `ingest_pending_documents()` (orchestrates the full ingestion flow). Routes via `analyze_query`'s `classification` field (`"RAG"` vs `"GraphRAG"`).
- **`analyzer`** — `analyze_query` classifies user intent; `AnalyzerPipeline.process_file` does the heavy enrichment: summary, keywords, questions, requirements, policy/clause classification, embedding, then upsert to Qdrant.
- **`document_access`** — MinIO listing/download, PDF text extraction (`pypdf`), and JSON-file-backed metadata (`MetadataManager`).
- **`rag`** — Qdrant search + `rag_ingest_chunks`. Uses `agents/shared/chunking.py` (Chonkie semantic chunker).
- **`graph_rag`** — `GraphBuilder` (LLM → Cypher), `QdrantToNeo4jIngestor` (Qdrant scroll → graph), `GraphRAG.retrieve` (vector hits + graph neighborhood expansion + LLM synthesis).
- **`summarizer`** — Phase 1 answer synthesis + Phase 2 prompts (`summarize_comparison`, `summarize_gaps`, `summarize_recommendations`).

### LLM clients (there are two)

- `core/llm/client.py::LiquidClient` — singleton, uses HuggingFace `transformers.pipeline`, loaded once per process. Used by all `agents/*`.
- `models/hf_client.py::FHClient` — 4-bit-quantized variant with Streamlit `cache_resource` + a CLI module-level cache. Used by the legacy `query.py` and `ingestion/pipeline.py`.

Both default to `LiquidAI/LFM2-2.6B-Exp` per `configs/config.yaml`. Don't add a third client — pick one based on which pipeline you're touching.

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

- All Python imports assume the repo root is on `sys.path`. Entry points (`app.py`, `api/server.py`) append it explicitly; if you create a new entry point do the same.
- Agents print init banners on import (`print("X Agent initialized.")`) — this is the registration signal. Keep it.
- LLM responses are parsed with regex-extracted JSON (`re.search(r'\{.*\}', ..., re.DOTALL)`) and silent fallbacks. When adding new LLM-driven extractors, follow the same pattern in `AnalyzerPipeline._parse_json_from_llm` rather than failing hard.
- Qdrant client method names differ across versions — existing code wraps calls in try/except with fallbacks (`create_collection` → `recreate_collection`, `scroll` → `get`). Preserve this when extending.
- Temp PDFs are downloaded to `temp_*.pdf` in CWD (gitignored). Don't refactor without updating both pipelines.
