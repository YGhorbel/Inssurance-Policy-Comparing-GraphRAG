import sys
import os
# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from core.mcp.handler import mcp_registry
# Import planner to load the full pipeline
import agents.planner.agent 
from pydantic import BaseModel

from agents.graph_rag.agent import ingestor, grag

app = FastAPI(title="Multi-Agent MCP Server")

@app.post("/mcp")
async def handle_mcp(request: Request):
    data = await request.json()
    response = await mcp_registry.handle_request(data)
    return response

@app.get("/health")
def health():
    return {"status": "ok", "tools": list(mcp_registry.methods.keys())}


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5


@app.post("/graph/ingest")
def graph_ingest():
    """Trigger ingestion of Qdrant-indexed chunks into Neo4j."""
    try:
        result = ingestor.ingest_all()
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/graph/retrieve")
def graph_retrieve(body: RetrieveRequest):
    """Run GraphRAG retrieval fusion and return synthesis."""
    try:
        # Use SentenceTransformer inside graph_retrieve_fusion already if needed
        coro = mcp_registry.methods.get("graph_retrieve_fusion")
        if coro:
            # coro is async, run it via asyncio
            import asyncio
            res = asyncio.run(coro(body.query, top_k=body.top_k))
            return {"status": "ok", "result": res}

        # Fallback to calling grag directly (needs embedder)
        from sentence_transformers import SentenceTransformer
        embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        res = grag.retrieve(body.query, embedder, top_k=body.top_k)
        return {"status": "ok", "result": res}

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
