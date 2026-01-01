class GraphPrompts:
    EXTRACTION_TEMPLATE = """You are a Neo4j Graph Agent. Output ONLY valid Cypher. No explanations, no markdown.

SCHEMA:
Node Labels: Regulation, Article, Obligation, Authority, Entity, Concept
Relationships: APPLIES_TO, REQUIRES, REGULATED_BY, RELATED_TO

SYNTAX RULES (CRITICAL):
- Nodes MUST be in parentheses: MERGE (r:Regulation {{name: "X"}})
- Relationships use arrows: MERGE (a)-[:RELATED_TO]->(b)
- Use MERGE to avoid duplicates
- Separate statements with semicolons
- NO explanations, just Cypher

EXAMPLE OUTPUT:
MERGE (r:Regulation:{country} {{name: "Insurance Code"}});
MERGE (a:Article {{id: "Art. 1"}});
MERGE (r)-[:REQUIRES]->(a);

INPUT TEXT:
{text}

METADATA: Country={country}, Type={doc_type}

Generate Cypher:"""

    @staticmethod
    def get_extraction_prompt(text: str, metadata: dict = None) -> str:
        meta = metadata or {}
        country = meta.get("country", "Unknown")
        doc_type = meta.get("doc_type", "Document")
        # Limit text to avoid token overflow
        truncated = text[:2000] if len(text) > 2000 else text
        return GraphPrompts.EXTRACTION_TEMPLATE.format(text=truncated, country=country, doc_type=doc_type)

