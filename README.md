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
- Development notes
- Contribution
- License & contact

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

Example graph schema:
(Country)-[:HAS_POLICY]->(PolicyType)-[:COVERS]->(Requirement)<-[:MENTIONS]-(Document)

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
- Storage: MinIO
- Chunking & parsing: llama_index (SentenceSplitter)
- LLM reasoning: Ollama (llama3:8b) — summarization, extraction
- Embeddings: HuggingFace all-MiniLM-L6-v2
- Vector DB: Qdrant
- Knowledge graph: Neo4j
- Orchestration: MCP (JSON-RPC)
- API: FastAPI
- UI: Streamlit
- Deployment: Docker Compose

## Quick start (high level)
1. Install Docker & Docker Compose (Windows)
2. Configure .env with MinIO, Qdrant, Neo4j credentials
3. Start services:
   - Open PowerShell in project root:
     - docker-compose up -d
4. Run backend API & agents:
   - Activate your Python venv
   - pip install -r requirements.txt
   - python -m app.main  # example entrypoint
5. Open Streamlit dashboard:
   - streamlit run app/ui/dashboard.py

(Adjust commands/entrypoints to match your local structure.)

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
HF_TOKEN=your_hf_token_here
QDRANT_URL=http://localhost:6333
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

- Start the FastAPI server (backend / MCP endpoint)

```powershell
uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
```

- Ingest documents (via MCP JSON-RPC) — example: trigger planner ingestion

```powershell
curl -X POST http://localhost:8001/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"ingest_documents","id":"1"}'
```

- Ingest Qdrant → Neo4j (GraphRAG) via API

```powershell
curl -X POST http://localhost:8000/graph/ingest
```

- Run the Streamlit UI

```powershell
streamlit run ui/app.py
```

- Example retrieval fusion (compare/analysis) via API

```powershell
curl -X POST http://localhost:8000/graph/retrieve -H "Content-Type: application/json" -d '{"query":"compare auto insurance Tunisia France","top_k":5}'
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

## Development notes
- Keep chunk size tuned to LLM token limits
- Store chunk metadata (country, doc, policy_type, pub_date) for efficient filtering
- Use deterministic prompts for requirement extraction to improve graph consistency
- Add unit tests for ingestion, embedding creation, and graph ingestion

## Contribution
- Open issues for bugs or enhancements
- Pull requests: run tests and linting before submitting

## License & contact
- License: Add your license file (e.g., MIT)
- Contact: maintainers / project owner (add email or repo link)

