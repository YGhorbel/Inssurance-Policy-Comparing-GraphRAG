class GraphPrompts:
    # Token limits for text truncation
    MAX_TEXT_LENGTH = 1500
    MAX_SUMMARY_LENGTH = 500
    
    EXTRACTION_TEMPLATE = """You are a Neo4j Graph Agent. Output ONLY valid Cypher. No explanations, no markdown.

SCHEMA:
Node Labels: Regulation, Article, Obligation, Authority, Entity, Concept, PolicyType, Country, Requirement
Relationships: APPLIES_TO, REQUIRES, REGULATED_BY, RELATED_TO, COVERS, HAS_POLICY, MENTIONS

SYNTAX RULES (CRITICAL):
- Nodes MUST be in parentheses: MERGE (r:Regulation {{name: "X"}})
- Relationships use arrows: MERGE (a)-[:RELATED_TO]->(b)
- Use MERGE to avoid duplicates
- Separate statements with semicolons
- NO explanations, just Cypher

ENRICHED METADATA:
- Country: {country}
- Policy Type: {policy_type}
- Clause Type: {clause_type}
- Keywords: {keywords}
- Requirements: {requirements}

EXAMPLE OUTPUT:
MERGE (c:Country {{name: "{country}"}});
MERGE (p:PolicyType {{name: "{policy_type}"}});
MERGE (c)-[:HAS_POLICY]->(p);
MERGE (r:Regulation {{name: "Insurance Code"}});
MERGE (a:Article {{id: "Art. 1"}});
MERGE (r)-[:REQUIRES]->(a);

INPUT TEXT (Summary):
{summary}

ORIGINAL TEXT (for context):
{text}

Generate Cypher:"""

    @staticmethod
    def get_extraction_prompt(text: str, metadata: dict = None) -> str:
        meta = metadata or {}
        country = meta.get("country", "Unknown")
        policy_type = meta.get("policy_type", "General")
        clause_type = meta.get("clause_type", "Requirement")
        
        # Handle enriched chunk structure
        summary = meta.get("summary", "")
        keywords = meta.get("keywords", [])
        requirements = meta.get("extracted_requirements", [])
        
        # Format keywords and requirements as strings
        keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
        requirements_str = "; ".join(requirements) if isinstance(requirements, list) else str(requirements)
        
        # Limit text to avoid token overflow using class constants
        truncated = text[:GraphPrompts.MAX_TEXT_LENGTH] if len(text) > GraphPrompts.MAX_TEXT_LENGTH else text
        summary_truncated = summary[:GraphPrompts.MAX_SUMMARY_LENGTH] if len(summary) > GraphPrompts.MAX_SUMMARY_LENGTH else summary
        
        return GraphPrompts.EXTRACTION_TEMPLATE.format(
            text=truncated,
            summary=summary_truncated,
            country=country,
            policy_type=policy_type,
            clause_type=clause_type,
            keywords=keywords_str,
            requirements=requirements_str
        )


