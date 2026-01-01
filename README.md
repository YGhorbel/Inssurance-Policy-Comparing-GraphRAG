# Insurance Policy Comparing - Multi-Agent GraphRAG

An end-to-end system that ingests PDF regulatory documents, chunks them semantically, and stores knowledge in Neo4j + Qdrant for intelligent querying.

## 🏗️ Architecture
- **LLM**: LiquidAI/LFM2-2.6B-Exp (local GPU)
- **Vector DB**: Qdrant
- **Graph DB**: Neo4j
- **Storage**: MinIO
- **Orchestration**: MCP (JSON-RPC 2.0)
- **UI**: Streamlit

## 🚀 Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/YGhorbel/Inssurance-Policy-Comparing-GraphRAG.git
cd Inssurance-Policy-Comparing-GraphRAG
pip install -r requirements.txt
```

### 2. Setup Data Folders
The `data/` folder is gitignored (contains large Neo4j/Qdrant volumes). Create it:
```bash
mkdir -p data/neo4j data/minio data/qdrant
```

### 3. Environment Variables
Create a `.env` file:
```env
HF_TOKEN=your_huggingface_token
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### 4. Start Infrastructure (Docker)
```bash
docker-compose up -d
```
This starts:
- **MinIO**: http://localhost:9001 (`minioadmin`/`minioadmin`)
- **Neo4j**: http://localhost:7474 (`neo4j`/`password`)
- **Qdrant**: http://localhost:6333

### 5. Upload Documents
1. Open MinIO Console → Create bucket `regulations`
2. Upload your PDF files

### 6. Start the System
```bash
# Terminal 1: API Server
python api/server.py

# Terminal 2: UI
streamlit run ui/app.py
```

### 7. Use the Admin Dashboard
1. Go to **Admin Dashboard** tab
2. Click **Sync Metadata** to detect documents
3. Assign **Country** and **Type** to each document
4. Click **Process All Pending**

### 8. Ask Questions
Use the **Chat Assistant** tab:
- "What are the car rental insurance requirements in Tunisia?"
- "Compare European and Tunisian insurance capital requirements"

## 📁 Repository Structure
```
├── agents/              # Multi-agent modules
│   ├── analyzer/        # Intent classification
│   ├── document_access/ # MinIO + Metadata
│   ├── graph_rag/       # Neo4j + Cypher
│   ├── planner/         # Orchestrator
│   ├── rag/             # Qdrant search
│   └── summarizer/      # Answer generation
├── api/                 # FastAPI MCP server
├── core/                # LLM client + MCP handler
├── ui/                  # Streamlit app
├── data/                # (gitignored) Docker volumes
└── docker-compose.yml   # Infrastructure
```

## ⚠️ Notes
- `data/` folder is **gitignored** (contains large DB files)
- First run will download the LiquidAI model (~5GB)
- Requires CUDA-capable GPU for fast inference

