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
- Analyzer Agent: chunking, summarization, requirement extraction, embeddings
- Qdrant: single vector store for all chunks + metadata
- Neo4j: knowledge graph (countries, policies, requirements, docs)
- GraphRAG: combined vector + graph retrieval and reasoning
- Planner & Summarizer agents: compose outputs and orchestrate workflows
- FastAPI: API endpoints for triggers and agent comms
- Streamlit: admin dashboard and chat interface

Example graph schema:
(Country)-[:HAS_POLICY]->(PolicyType)-[:COVERS]->(Requirement)<-[:MENTIONS]-(Document)

## Data flow
1. Upload PDFs → MinIO (with metadata)
2. Analyzer Agent:
   - Chunk documents (preserve headings/tables)
   - Summarize chunks
   - Extract explicit requirements
   - Generate embeddings
3. Store enriched chunks in Qdrant
4. GraphRAG:
   - Retrieve similar clauses from Qdrant
   - Traverse/augment Neo4j graph
   - Produce comparative analyses
5. Summarizer / Planner → Streamlit / API outputs

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

