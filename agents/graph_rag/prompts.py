class GraphPrompts:
    MAX_TEXT_LENGTH = 1500
    MAX_SUMMARY_LENGTH = 500

    EXTRACTION_TEMPLATE = """You are a Neo4j Graph Agent. Output ONLY valid Cypher. No explanations, no markdown.

SCHEMA:
Node Labels: Regulation, Article, Obligation, Authority, Entity, Concept, PolicyType, Country, Requirement
Relationships: APPLIES_TO, REQUIRES, REFERENCES, EQUIVALENT_TO, CONFLICTS_WITH, PART_OF, DEFINES

RELATIONSHIP SEMANTICS:
- (Regulation|PolicyType)-[:APPLIES_TO]->(Country)       directed; scope
- (Regulation|Article)-[:REQUIRES]->(Requirement)        directed; obligation
- (Article)-[:REFERENCES]->(Article|Regulation)          directed; citation
- (Requirement|Regulation)-[:EQUIVALENT_TO]->(...)       symmetric; cross-jurisdictional equivalence
- (Requirement)-[:CONFLICTS_WITH]->(Requirement)         symmetric; cross-jurisdictional conflict
- (Article|Requirement)-[:PART_OF]->(Regulation|Requirement)  directed; containment
- (Regulation|Article)-[:DEFINES]->(Concept|Entity)      directed; definitional anchor

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

EXAMPLE OUTPUT (taxonomy demonstration):
MERGE (c:Country {{name: "{country}"}});
MERGE (p:PolicyType {{name: "{policy_type}"}});
MERGE (p)-[:APPLIES_TO]->(c);
MERGE (reg:Regulation {{name: "Tunisian Insurance Code"}});
MERGE (a1:Article {{id: "Art. 1"}});
MERGE (a2:Article {{id: "Art. 5"}});
MERGE (a3:Article {{id: "Art. 7"}});
MERGE (a1)-[:PART_OF]->(reg);
MERGE (a2)-[:PART_OF]->(reg);
MERGE (a3)-[:PART_OF]->(reg);
MERGE (a2)-[:REFERENCES]->(a1);
MERGE (a3)-[:REFERENCES]->(a2);
MERGE (req:Requirement {{name: "Third-party liability cover"}});
MERGE (reg)-[:REQUIRES]->(req);
MERGE (concept:Concept {{name: "Liability"}});
MERGE (a1)-[:DEFINES]->(concept);
MERGE (eu_req:Requirement {{name: "Compulsory motor insurance"}});
MERGE (req)-[:EQUIVALENT_TO]->(eu_req);
MERGE (excl:Requirement {{name: "Driver intoxication exclusion"}});
MERGE (req)-[:CONFLICTS_WITH]->(excl);

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

        summary = meta.get("summary", "")
        keywords = meta.get("keywords", [])
        requirements = meta.get("extracted_requirements", [])

        keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
        requirements_str = "; ".join(requirements) if isinstance(requirements, list) else str(requirements)

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
