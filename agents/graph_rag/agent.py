from core.mcp.handler import mcp_registry
from agents.graph_rag.db import Neo4jHandler
from agents.graph_rag.builder import GraphBuilder
from agents.graph_rag.qdrant_ingest import QdrantToNeo4jIngestor
from agents.graph_rag.fusion import GraphRAG

db = Neo4jHandler()
builder = GraphBuilder(db)
ingestor = QdrantToNeo4jIngestor()
grag = GraphRAG()

# --- MCP Tools ---

async def query_knowledge_graph(cypher_query: str) -> list:
    """
    Execute a direct Cypher query against the Knowledge Graph.
    Useful for retrieval or checking existence of nodes.
    """
    return db.execute_query(cypher_query)

async def compare_policies(policy_a: str, policy_b: str) -> str:
    """
    Compare two policies by looking up their sub-graph and checking for CONFLICTS_WITH or EQUIVALENT_TO relations.
    """
    query = """
    MATCH (a:Regulation {name: $p1})
    MATCH (b:Regulation {name: $p2})
    OPTIONAL MATCH (a)-[r]-(b)
    RETURN a, b, r
    """
    result = db.execute_query(query, {"p1": policy_a, "p2": policy_b})
    # In a real agent, we would pass this result to the LLM to summarize.
    # For now, return raw data.
    return str(result)

async def build_graph_from_text(text: str, metadata: dict = None) -> bool:
    """
    Trigger the builder to extract entities and relations from text and ingest into Neo4j.
    """
    return builder.process_text_chunk(text, metadata)

# Register tools
mcp_registry.register_tool("graph_query", query_knowledge_graph)
mcp_registry.register_tool("graph_compare", compare_policies)
mcp_registry.register_tool("graph_ingest_chunk", build_graph_from_text)
mcp_registry.register_tool("graph_ingest_from_qdrant", ingestor.ingest_all)


async def graph_retrieve_fusion(query: str, top_k: int = 5) -> dict:
    """Perform GraphRAG retrieval fusion and return synthesis."""
    # Use grag; it needs an embedder - we'll use sentence-transformers here lazily
    try:
        from sentence_transformers import SentenceTransformer
        embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    except Exception:
        embedder = None

    if embedder is None:
        return {"error": "embedder not available"}

    return grag.retrieve(query, embedder, top_k=top_k)


mcp_registry.register_tool("graph_retrieve_fusion", graph_retrieve_fusion)

print("GraphRAG Agent initialized.")
