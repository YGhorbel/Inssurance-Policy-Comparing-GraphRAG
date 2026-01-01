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
        """
        prompt = GraphPrompts.get_extraction_prompt(text, metadata)
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

