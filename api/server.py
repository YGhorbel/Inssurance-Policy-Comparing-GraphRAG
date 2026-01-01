import sys
import os
# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from core.mcp.handler import mcp_registry
# Import planner to load the full pipeline
import agents.planner.agent 

app = FastAPI(title="Multi-Agent MCP Server")

@app.post("/mcp")
async def handle_mcp(request: Request):
    data = await request.json()
    response = await mcp_registry.handle_request(data)
    return response

@app.get("/health")
def health():
    return {"status": "ok", "tools": list(mcp_registry.methods.keys())}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
