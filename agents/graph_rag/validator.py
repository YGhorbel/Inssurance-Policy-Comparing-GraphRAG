import re

class CypherValidator:
    """Validates and sanitizes Cypher queries before execution."""
    
    VALID_KEYWORDS = {'MERGE', 'MATCH', 'CREATE', 'RETURN', 'WITH', 'WHERE', 'SET', 'UNWIND', 'OPTIONAL'}
    
    @staticmethod
    def is_valid_cypher(query: str) -> bool:
        """Check if query starts with a valid Cypher keyword."""
        if not query or not query.strip():
            return False
        
        first_word = query.strip().split()[0].upper()
        return first_word in CypherValidator.VALID_KEYWORDS
    
    @staticmethod
    def extract_cypher_statements(raw_output: str) -> list:
        """
        Extract valid Cypher statements from LLM output.
        Filters out explanations, markdown, and invalid syntax.
        """
        # Remove markdown code blocks
        raw_output = re.sub(r'```cypher\s*', '', raw_output)
        raw_output = re.sub(r'```\s*', '', raw_output)
        
        # Split by semicolons
        parts = raw_output.split(';')
        
        valid_statements = []
        for part in parts:
            cleaned = part.strip()
            if cleaned and CypherValidator.is_valid_cypher(cleaned):
                # Fix common LLM mistakes
                cleaned = CypherValidator.fix_common_errors(cleaned)
                if cleaned:
                    valid_statements.append(cleaned)
        
        return valid_statements
    
    @staticmethod
    def fix_common_errors(query: str) -> str:
        """Fix common Cypher syntax errors from LLM."""
        # Skip if it's just plain text explanation
        if query.startswith(('This ', 'The ', 'Here ', 'Note:', '**')):
            return None
            
        # Fix: MERGE :Label -> MERGE (:Label)
        query = re.sub(r'MERGE\s+:(\w+)', r'MERGE (:\1)', query)
        
        # Fix: MERGE (n) :REL -> MERGE (n)-[:REL]->
        query = re.sub(r'\)\s+:(\w+)\s*$', r')', query)  # Remove trailing :REL without proper syntax
        
        # Fix: node :RELATES_TO node -> node-[:RELATES_TO]->node (can't auto-fix, skip)
        if re.search(r'\}\s+:\w+\s+:', query):
            return None
        
        return query

def validate_and_execute(db, raw_cypher: str) -> tuple:
    """
    Validate Cypher, extract valid statements, execute them.
    Returns (success_count, error_count, errors)
    """
    statements = CypherValidator.extract_cypher_statements(raw_cypher)
    
    success = 0
    errors = []
    
    for stmt in statements:
        try:
            db.execute_query(stmt)
            success += 1
        except Exception as e:
            errors.append(f"Query Error: {str(e)[:100]}")
    
    return success, len(errors), errors
