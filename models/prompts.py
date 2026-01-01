class GraphPrompts:
    """
    Prompt templates for extracting Neo4j Cypher graphs
    from regulatory or legal text.
    """

    EXTRACTION_TEMPLATE = (
        "You are an expert Neo4j developer.\n"
        "Your task is to convert the following regulatory text into a set of Cypher MERGE statements "
        "to build a knowledge graph.\n\n"
        "Use the following Node Labels and keys:\n"
        "- :Regulation (name)\n"
        "- :Article (id)\n"
        "- :Obligation (description)\n"
        "- :Authority (name)\n"
        "- :Entity (name)\n\n"
        "Use the following Relationship Types:\n"
        "- :APPLIES_TO\n"
        "- :REQUIRES\n"
        "- :REGULATED_BY\n"
        "- :CONFLICTS_WITH\n"
        "- :EQUIVALENT_TO\n\n"
        "Rules:\n"
        "- Use MERGE to avoid duplicates.\n"
        "- Generate ONLY valid Cypher code.\n"
        "- Do NOT add explanations or markdown.\n"
        "- Separate statements with semicolons.\n\n"
        "Input Text:\n"
        "{text}"
    )

    @staticmethod
    def get_extraction_prompt(text: str) -> str:
        return GraphPrompts.EXTRACTION_TEMPLATE.format(
            text=text.strip()
        )
