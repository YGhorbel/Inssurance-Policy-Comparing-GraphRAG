from graph.neo4j_client import Neo4jClient

class GraphBuilder:
    def __init__(self):
        self.client = Neo4jClient()

    def build_graph(self, extraction_result: dict):
        """
        Takes a dictionary with 'entities' and 'relationships' and ingests them into Neo4j.
        """
        if not extraction_result:
            return

        entities = extraction_result.get("entities", [])
        relationships = extraction_result.get("relationships", [])

        # Create Entities
        for entity in entities:
            label = entity.get("label", "Entity")
            props = entity.get("properties", {})
            uid = entity.get("id")
            
            # Simple merge query
            # Note: In production we'd want safer parameter passing for labels, 
            # but Neo4j drivers don't support parametrizing labels directly easily.
            # We assume trusted input from our LLM/Prompt (sanitization recommended for prod).
            
            # Construct property string for MERGE (simplified)
            # merging on 'id' is key.
            query = f"MERGE (n:`{label}` {{id: $id}}) SET n += $props"
            self.client.execute_query(query, {"id": uid, "props": props})

        # Create Relationships
        for rel in relationships:
            src_id = rel.get("source")
            tgt_id = rel.get("target")
            rel_type = rel.get("type", "RELATED_TO")
            
            query = f"""
            MATCH (a {{id: $src_id}}), (b {{id: $tgt_id}})
            MERGE (a)-[r:`{rel_type}`]->(b)
            """
            self.client.execute_query(query, {"src_id": src_id, "tgt_id": tgt_id})

    def close(self):
        self.client.close()
