from core.llm.client import get_llm_client
from agents.graph_rag.db import Neo4jHandler
from agents.graph_rag.prompts import GraphPrompts
from agents.graph_rag.validator import CypherValidator

class GraphBuilder:
    def __init__(self, db_handler: Neo4jHandler):
        self.llm = get_llm_client()
        self.db = db_handler

    def process_text_chunk(self, text: str, metadata: dict = None):
        """
        Generates Cypher from text, validates, and executes it.
        Handles both enriched chunk structure and legacy metadata.
        """
        # If metadata contains the enriched structure, extract it
        if metadata and isinstance(metadata, dict):
            # Check if this is an enriched chunk
            if "summary" in metadata and "keywords" in metadata:
                # This is already enriched, use directly
                enriched_metadata = metadata
            else:
                # Legacy format, pass as-is
                enriched_metadata = metadata
        else:
            enriched_metadata = {}
        
        prompt = GraphPrompts.get_extraction_prompt(text, enriched_metadata)
        response = self.llm.generate(prompt)
        
        if response:
            return self._execute_validated_cypher(response)
        return False

    def _execute_validated_cypher(self, raw_cypher: str):
        """Execute only valid Cypher statements."""
        statements = CypherValidator.extract_cypher_statements(raw_cypher)
        
        if not statements:
            print("    > No valid Cypher extracted.")
            return False
        
        success = 0
        for stmt in statements:
            try:
                self.db.execute_query(stmt)
                success += 1
            except Exception as e:
                print(f"    > Query Error: {str(e)[:80]}")
        
        print(f"    > Executed {success}/{len(statements)} statements.")
        return success > 0

