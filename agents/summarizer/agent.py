from core.mcp.handler import mcp_registry
from core.llm.client import get_llm_client

llm = get_llm_client()

# Phase 1: Document summarization
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

# Phase 2: Comparison summarization
COMPARISON_SUMMARY_PROMPT = """
You are an Expert Comparative Insurance Analyst.

Comparison Data:
{comparison_data}

Task:
Summarize the key similarities and differences between the insurance policies or regulations.
Organize your summary clearly with:
- Common requirements
- Unique requirements for each jurisdiction
- Key differences in coverage or obligations
Use markdown tables or structured lists for clarity.
"""

# Phase 2: Gap analysis summarization
GAP_SUMMARY_PROMPT = """
You are an Expert Regulatory Gap Analyst.

Reference Policy (Baseline):
{reference}

Analyzed Policy:
{analyzed}

Task:
Identify and summarize gaps where the analyzed policy is missing requirements or coverage present in the reference policy.
Organize findings as:
- Critical gaps (high-priority missing requirements)
- Secondary gaps (optional but recommended additions)
- Strengths (areas where analyzed policy exceeds reference)
"""

# Phase 2: Recommendations summarization
RECOMMENDATION_SUMMARY_PROMPT = """
You are an Expert Insurance Policy Advisor.

Current Policy Analysis:
{analysis}

Identified Gaps:
{gaps}

Task:
Provide actionable recommendations for policy improvements.
Structure your recommendations as:
1. Priority 1 (Critical): Urgent changes needed for compliance or coverage
2. Priority 2 (Important): Recommended improvements for better protection
3. Priority 3 (Optional): Enhancements for competitive advantage

Include specific language or clauses where possible.
"""

async def summarize_results(query: str, context: str) -> str:
    """
    Phase 1: Generate a final answer based on the query and retrieved context.
    """
    prompt = SUMMARIZE_PROMPT.format(query=query, context=context)
    return llm.generate(prompt)

async def summarize_comparison(comparison_data: str) -> str:
    """
    Phase 2: Summarize comparison results between policies or jurisdictions.
    """
    prompt = COMPARISON_SUMMARY_PROMPT.format(comparison_data=comparison_data)
    return llm.generate(prompt)

async def summarize_gaps(reference: str, analyzed: str) -> str:
    """
    Phase 2: Summarize gaps identified in policy analysis.
    """
    prompt = GAP_SUMMARY_PROMPT.format(reference=reference, analyzed=analyzed)
    return llm.generate(prompt)

async def summarize_recommendations(analysis: str, gaps: str) -> str:
    """
    Phase 2: Generate actionable recommendations based on analysis and gaps.
    """
    prompt = RECOMMENDATION_SUMMARY_PROMPT.format(analysis=analysis, gaps=gaps)
    return llm.generate(prompt)

# Register all tools
mcp_registry.register_tool("summarize_results", summarize_results)
mcp_registry.register_tool("summarize_comparison", summarize_comparison)
mcp_registry.register_tool("summarize_gaps", summarize_gaps)
mcp_registry.register_tool("summarize_recommendations", summarize_recommendations)

print("Summarizer Agent initialized with Phase 1 and Phase 2 capabilities.")
