# Research Assistant for Insurance Policy Design — Full Workflow
AI system to analyze, compare, and propose improvements for insurance policies and regulations (focus: Tunisia & international). Uses multi-agent orchestration with semantic search, knowledge graphs, and LLM reasoning.

## Table of contents
- Project overview
- Key features
- Architecture & components
- Data flow
- Core technologies
- Quick start
- Usage examples
- **Benchmarks** (MultiHop-RAG retrieval-quality)
- **Security guards** (SSRF, path-traversal, prompt-injection, EXPLAIN)
- Development notes
- Contribution

## Project overview
This project builds an end-to-end pipeline that:
- Ingests regulatory PDFs
- Extracts structured knowledge (summaries, requirements, metadata)
- Stores embeddings for semantic retrieval (Qdrant)
- Builds a knowledge graph (Neo4j) for reasoning and comparison
- Produces human-readable summaries, gap analyses, and recommendations

## Key features
- PDF ingestion + metadata (country, policy type, date)
- Chunking, summarization, and requirement extraction
- Embeddings (HuggingFace) for semantic clause search
- Qdrant vector store + rich metadata filtering
- Neo4j knowledge graph for relationships and cross-jurisdiction queries
- Planner/Summarizer agents for orchestration and outputs
- Streamlit dashboard + FastAPI for UI & API

## Architecture & components
- MinIO: object storage for raw PDFs and versions
- Analyzer Agent (Knowledge Ingestion): chunking, enrichment (summary, keywords, questions), requirement extraction, metadata classification, embeddings storage in Qdrant
- Qdrant: single vector store for all chunks + metadata
- Neo4j: knowledge graph (countries, policies, requirements, docs)
- GraphRAG: combined vector + graph retrieval and reasoning
- Planner & Summarizer agents: compose outputs and orchestrate workflows
  - Phase 1: Document summarization
  - Phase 2: Comparison, gap analysis, and recommendations
- FastAPI: API endpoints for triggers and agent comms
- Streamlit: admin dashboard and chat interface

Reconciled 7-edge graph schema (enforced by
`agents/graph_rag/validator.py`):

| # | Edge | Direction | Role |
|---|---|---|---|
| 1 | `APPLIES_TO` | directed | scope (Regulation / PolicyType → Country) |
| 2 | `REQUIRES` | directed | obligation imposition |
| 3 | `REFERENCES` | directed | citation (Article → Article / Regulation) |
| 4 | `EQUIVALENT_TO` | **symmetric** | cross-jurisdictional equivalence |
| 5 | `CONFLICTS_WITH` | **symmetric** | cross-jurisdictional contradiction |
| 6 | `PART_OF` | directed | structural hierarchy |
| 7 | `DEFINES` | directed | definitional anchor |

Node label whitelist (9): `Regulation, Article, Obligation, Authority,
Entity, Concept, PolicyType, Country, Requirement`.

LLM-generated Cypher passes through two layers before execution:
**structure validator** (taxonomy + destructive-keyword blocklist) and
**EXPLAIN cardinality guard** (default 100 000-row threshold). See
[docs/SECURITY.md](docs/SECURITY.md).

## Data flow
1. Upload PDFs → MinIO (with metadata)
2. Analyzer Agent (Knowledge Ingestion):
   - Chunk documents (preserve headings/tables)
   - Enrich chunks with summary, keywords, and questions
   - Extract explicit requirements
   - Classify metadata (country, policy_type, clause_type)
   - Generate embeddings
   - Store enriched chunks in Qdrant with complete metadata
3. Enriched chunk structure stored in Qdrant:
   ```json
   {
     "chunk_id": "...",
     "text": "...",
     "summary": "...",
     "keywords": [...],
     "questions": [...],
     "country": "Tunisia",
     "policy_type": "Auto",
     "clause_type": "Requirement",
     "extracted_requirements": [...],
     "source": {
       "document": "...",
       "page": 12,
       "section": "Article 5"
     },
     "embedding": [...]
   }
   ```
4. GraphRAG:
   - Retrieve similar clauses from Qdrant
   - Traverse/augment Neo4j graph using enriched metadata
   - Produce comparative analyses
5. Summarizer / Planner → Streamlit / API outputs
   - Phase 1: Document summaries
   - Phase 2: Comparisons, gap analyses, and recommendations

## Core technologies
- **Storage**: MinIO (object store for raw PDFs)
- **Chunking**: Chonkie `SemanticChunker` (regulations); paragraph-aware
  fixed-window `target=768 / max=1024` chars (MultiHop-RAG eval corpus)
- **Embeddings**: **BGE-M3** (Chen et al. 2024) — multilingual hybrid
  dense (1024-d, cosine) + sparse (token-id `lexical_weights`) head.
  The collection is Qdrant named-vector (`{dense, sparse}`); retrieval
  is dense-only today, sparse channel ingested for future hybrid
  fusion.
- **Reranker** (optional): **BGE-reranker-v2-m3** cross-encoder, top-20
  → top-5; a runtime self-disable falls back to upstream ranking when
  per-query latency exceeds the CPU budget, so GPU deploys get the
  lift and CPU hosts gracefully degrade.
- **Summary-Augmented Chunking**: one ≤150-char LLM-generated document
  summary prepended to each chunk at embed time, cached by
  `(file_hash, prompt_version)`.
- **LLM**: **Ollama Cloud** (`kimi-k2.6:cloud`) is the default router
  target (CPU-bound local inference is too slow for live iteration);
  an in-process local fallback stays in-tree. Route via the
  `LLM_PROVIDER` env var (`ollama_cloud` → `OllamaClient`, else →
  `LiquidClient`).
- **Vector DB**: Qdrant
- **Knowledge graph**: Neo4j with 7-edge reconciled taxonomy + EXPLAIN
  cardinality guard
- **Hybrid fusion**: Reciprocal Rank Fusion (Cormack, Clarke & Buettcher,
  SIGIR 2009, k=60) over vector hits + graph-driven chunk expansion
- **Orchestration**: MCP (JSON-RPC) — all agents register tools at
  import time into a single `mcp_registry` singleton
- **API**: FastAPI (`/mcp` JSON-RPC adapter at port 8001)
- **UI**: Streamlit
- **Deployment**: Docker Compose (MinIO :9000/:9001, Neo4j :7474/:7687,
  Qdrant :6333)

## Quick start (high level)
1. Install Docker & Docker Compose
2. Configure `.env` with MinIO, Qdrant, Neo4j credentials
3. Start services: `docker-compose up -d`
4. `pip install -r requirements.txt`
5. Run backend API & agents: `uvicorn api.server:app --reload --host 0.0.0.0 --port 8001`
6. Open Streamlit dashboard: `streamlit run ui/app.py`

## Run locally (Windows — recommended quick steps)

These commands assume you're on Windows PowerShell and in the project root (where `docker-compose.yml` and `requirements.txt` live).

- Prerequisites:
   - Docker Desktop (with WSL2 backend recommended)
   - Python 3.10+ and `venv`

- Start infrastructure (MinIO, Qdrant, Neo4j, etc.)

```powershell
docker-compose up -d
```

- Create a Python virtual environment and install dependencies

```powershell
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

- Configure environment variables (example `.env` / PowerShell export)

Create a `.env` file or export these vars in your environment. Example `.env` entries:

```text
# Required for the canonical Phase 2+ stack
LLM_PROVIDER=ollama_cloud
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_MODEL=kimi-k2.6:cloud
OLLAMA_API_KEY=your_ollama_cloud_key_here

# Storage + indexes
QDRANT_URL=http://localhost:6333
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Optional
HF_TOKEN=your_hf_token_here              # higher HF rate limits
MCP_URL_ALLOWLIST=                        # extra hosts for the SSRF guard
EXPLAIN_CARDINALITY_THRESHOLD=100000      # Cypher EXPLAIN guard threshold
RERANK_DISABLE_THRESHOLD_S=15             # CPU rerank budget (seconds)
AGENT_LOG_DIR=logs                        # JSONL audit directory
```

The `.env` file is gitignored — never commit secrets. Drop in the
`OLLAMA_API_KEY` and you're set.

- Start the FastAPI server (backend / MCP endpoint)

```powershell
uvicorn api.server:app --reload --host 0.0.0.0 --port 8001
```

- Ingest documents (via MCP JSON-RPC) — example: trigger planner ingestion

```powershell
curl -X POST http://localhost:8001/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"ingest_documents","id":"1"}'
```

- Ingest Qdrant → Neo4j (GraphRAG) via API

```powershell
curl -X POST http://localhost:8001/graph/ingest
```

- Run the Streamlit UI

```powershell
streamlit run ui/app.py
```

- Example retrieval fusion (compare/analysis) via API

```powershell
curl -X POST http://localhost:8001/graph/retrieve -H "Content-Type: application/json" -d '{"query":"compare auto insurance Tunisia France","top_k":5}'
```

Notes
- If `chonkie` or large model dependencies are not installed, some functionality will fall back or raise errors — install optional packages listed in `requirements.txt` as needed.
- If Qdrant client methods differ by version, the pipeline includes fallbacks but test the flow and adapt if needed.
- For production, secure `.env` values and consider using Docker secrets / a proper configuration store.

## Usage examples
- "Compare auto insurance requirements in France and Tunisia"
- "Find expiration clauses for health policies in Tunisia"
- "Show requirements present in EU but missing in Tunisia"

Outputs: markdown reports, comparative matrices, citations with provenance.

## Benchmarks

Retrieval-quality runs against **MultiHop-RAG** (Tang & Yang,
arXiv 2401.15391, ODC-BY 1.0). 100 stratified queries from the dataset
(seed=42, 25 each of `inference / comparison / temporal / null_query`).
Relevance is article-URL level, matching the original paper.
**Headline subset** is the 75 answerable queries (`null_query` is a
negative-control bucket and scores 0.0 by construction).

| Config | Recall@2 | Recall@5 | MRR | Latency |
|---|---|---|---|---|
| BGE-M3 dense | **0.440** | 0.661 | 0.750 | 13.2 ms |
| + SAC chunking | 0.418 | **0.672** | **0.816** | 15.3 ms |
| + cross-encoder reranker | 0.418 | 0.672 | 0.816 | 19 ms¹ |

¹ Reranker-pass on CPU: the cross-encoder self-disabled on query 1 at
41.6 s against the 15 s budget; 99/100 queries fell back to the
SAC-enabled dense ordering. Numbers identical to the SAC-only row on
this host. GPU FP16 is expected to deliver the reranker's quality
lift.

Headline takeaway: **SAC delivers +0.066 MRR** on the answerable
subset. Production recommendation is BGE-M3 + SAC; the reranker is
in-tree for GPU deploys via `--rerank`. Full per-tag tables,
dataset-format notes, and the honest-gaps caveats live in
[docs/BENCHMARKS.md](docs/BENCHMARKS.md). Machine-readable summaries
ship at `evaluation/results/baseline_mhrag_*.json`.

Reproduce locally:

```bash
# Dense baseline
.venv/bin/python -m evaluation.runners.multihop_rag --ingest
.venv/bin/python -m evaluation.runners.multihop_rag --run

# + SAC chunking
.venv/bin/python -m evaluation.runners.multihop_rag --ingest --sac \
    --collection mhrag_eval_v2_sac
.venv/bin/python -m evaluation.runners.multihop_rag --run \
    --collection mhrag_eval_v2_sac

# + cross-encoder reranker (top-20 → top-5)
.venv/bin/python -m evaluation.runners.multihop_rag --run --rerank \
    --collection mhrag_eval_v2_sac
```

## Security guards

Four runtime guards land on the boundaries where untrusted input flows
into trusted components. Each rejection writes an append-only JSONL
audit row under `logs/`.

| Module | Threat | JSONL |
|---|---|---|
| `core/mcp/url_guard.py` | SSRF (IMDS, RFC1918, link-local, unknown external hosts) | `mcp_url_rejections.jsonl` |
| `core/mcp/path_guard.py` | MinIO key + local path-traversal | `mcp_path_rejections.jsonl` |
| `agents/shared/pi_guard.py` | Indirect prompt injection from document content | `pi_quarantine.jsonl` |
| `agents/graph_rag/builder.py::_execute` | Runaway Cypher cardinality on validated MERGE/MATCH | `cypher_rejections.jsonl` |

Full design + per-guard API in [docs/SECURITY.md](docs/SECURITY.md).

## Development notes
- Keep chunk size tuned to BGE-M3's 1024-token passage limit
  (`agents/shared/embeddings.py`); the MultiHop-RAG runner enforces a
  hard `MAX_CHARS=1024` chunker for that reason.
- Store chunk metadata (country, doc, policy_type, pub_date,
  clause_type) for efficient filtering — the enriched-chunk schema in
  `agents/analyzer/pipeline.py::process_file` is the source of truth.
- Use deterministic prompts (`agents/graph_rag/prompts.py`,
  `agents/shared/sac.py`) for extraction to improve graph consistency
  and SAC cache hit rate.
- Unit tests live under `evaluation/test_*.py` — 56 today, all stdlib
  + pytest-free. New features should land with a test in the same
  style.

## Contribution
- Open issues for bugs or enhancements
- Pull requests: run tests and linting before submitting

