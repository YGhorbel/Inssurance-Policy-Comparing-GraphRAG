from core.mcp.handler import mcp_registry
from core.llm.client import get_llm_client

llm = get_llm_client()

SUMMARIZE_PROMPT = """
You are an Expert Legal Summarizer.
User Query: "{query}"

Context from Knowledge Base:
{context}

Task:
Provide a clear, comprehensive answer. 
If comparing, use a markdown table or bullet points.
Cite regulations where possible.
"""

async def summarize_results(query: str, context: str) -> str:
    """
    Generate a final answer based on the query and retrieved context.
    """
    prompt = SUMMARIZE_PROMPT.format(query=query, context=context)
    return llm.generate(prompt)

mcp_registry.register_tool("summarize_results", summarize_results)
print("Summarizer Agent initialized.")
