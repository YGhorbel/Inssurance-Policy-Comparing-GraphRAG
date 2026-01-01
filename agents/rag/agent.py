from core.mcp.handler import mcp_registry
from agents.rag.db import QdrantHandler
from agents.shared.chunking import ChonkieHandler

qdrant = QdrantHandler()
chonkie_handler = ChonkieHandler()

# --- MCP Tools ---

async def rag_search(query: str, top_k: int = 5) -> list:
    """
    Perform semantic search on the regulatory documents.
    Returns list of relevant text chunks.
    """
    return qdrant.search(query, top_k)

async def chunk_document(text: str, metadata: dict) -> list:
    """Chunk text using Chonkie."""
    return chonkie_handler.chunk_text(text, metadata)

async def rag_ingest_chunks(chunks: list) -> bool:
    """Ingest pre-processed chunks into Qdrant."""
    return qdrant.ingest_chunks(chunks)

async def rag_ingest(text: str, metadata: dict) -> bool:
    """
    Chunk and ingest text into Qdrant vector database.
    """
    chunks = chonkie_handler.chunk_text(text, metadata)
    return qdrant.ingest_chunks(chunks)

# Register tools
mcp_registry.register_tool("rag_search", rag_search)
mcp_registry.register_tool("rag_ingest", rag_ingest)
mcp_registry.register_tool("chunk_document", chunk_document) # New
mcp_registry.register_tool("rag_ingest_chunks", rag_ingest_chunks) # New

print("RAG Agent initialized.")
