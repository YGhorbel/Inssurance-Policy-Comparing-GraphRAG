import sys
from graph.neo4j_client import Neo4jClient
from models.hf_client import FHClient

class GraphQueryEngine:
    def __init__(self):
        self.neo4j = Neo4jClient()
        self.llm = FHClient()

    def summarize_regulation(self, regulation_name):
        print(f"Summarizing {regulation_name}...")
        query = """
        MATCH (r:Regulation {name: $name})<-[:REGULATED_BY|APPLIES_TO]-(n)
        RETURN r, collect(n) as related_nodes
        """
        results = self.neo4j.execute_query(query, {"name": regulation_name})
        
        if not results:
            print("Regulation not found.")
            return

        # Simple context construction
        context = str(results)
        prompt = f"Summarize the following regulation details based on the graph data: {context}"
        return self.llm.generate(prompt)

    def compare_regulations(self, reg1, reg2):
        print(f"Comparing {reg1} vs {reg2}...")
        query = """
        MATCH (r:Regulation) WHERE r.name IN [$r1, $r2]
        OPTIONAL MATCH (r)-[:CONFLICTS_WITH]->(c)
        RETURN r.name, r, collect(c) as conflicts
        """
        results = self.neo4j.execute_query(query, {"r1": reg1, "r2": reg2})
        
        context = str(results)
        prompt = f"Compare the following two regulations based on the graph data provided. Highlight conflicts or similarities: {context}"
        return self.llm.generate(prompt)

    def close(self):
        self.neo4j.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python query.py [summarize|compare] [args...]")
        sys.exit(1)

    engine = GraphQueryEngine()
    
    cmd = sys.argv[1]
    if cmd == "summarize" and len(sys.argv) > 2:
        print(engine.summarize_regulation(sys.argv[2]))
    elif cmd == "compare" and len(sys.argv) > 3:
        print(engine.compare_regulations(sys.argv[2], sys.argv[3]))
    else:
        print("Unknown command or missing args.")
    
    engine.close()
