from core.mcp.handler import mcp_registry
from core.llm.client import get_llm_client
import json
try:
    from . import document_analyzer  # noqa: F401  (dead module; soft-imported, Phase 3 will delete)
except Exception as _doc_analyzer_exc:
    print(f"Note: agents.analyzer.document_analyzer skipped ({_doc_analyzer_exc.__class__.__name__}); slated for removal in Phase 3.")
from .pipeline import AnalyzerPipeline

llm = get_llm_client()

QUERY_ANALYSIS_PROMPT = """
You are a Gatekeeper and Analyzer AI.
Analyze the following user query:
"{query}"

1. Validate intent: Is this related to insurance regulations? (Yes/No)
2. Classify: 
   - "RAG" if it asks for specific facts.
   - "GraphRAG" if it asks for comparison, relationships, or complex reasoning (e.g., "compare", "how does X related to Y").
3. Extract Entities: Region (e.g., Tunisia, Europe), Topic (e.g., Car, Health).

Return ONLY a valid JSON object:
{{
  "is_valid": true,
  "classification": "RAG" or "GraphRAG",
  "entities": {{
    "region": ["Region1"],
    "topic": "Topic"
  }}
}}
"""

async def analyze_query(query: str) -> dict:
    """
    Analyze user query to determine intent and routing.
    """
    prompt = QUERY_ANALYSIS_PROMPT.format(query=query)
    response = llm.generate(prompt)
    
    # Simple JSON extraction
    try:
        import re
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
    
    # Fallback
    return {"is_valid": True, "classification": "RAG", "entities": {}}

mcp_registry.register_tool("analyze_query", analyze_query)
print("Analyzer Agent initialized.")

# Register processing tools
pipeline = AnalyzerPipeline()


async def process_new_documents():
  return pipeline.process_new_files()


mcp_registry.register_tool("analyzer.process_new_files", process_new_documents)
print("Analyzer pipeline registered.")
