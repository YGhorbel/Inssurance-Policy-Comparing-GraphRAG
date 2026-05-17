from neo4j import GraphDatabase
import yaml

class Neo4jClient:
    def __init__(self, config_path="configs/config.yaml"):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)["neo4j"]
        
        self.uri = config["uri"]
        self.user = config["user"]
        self.password = config["password"]
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self):
        self.driver.close()

    def execute_query(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters)
            return [record for record in result]
    
    def reset_db(self):
        """Warning: clear entire database."""
        self.execute_query("MATCH (n) DETACH DELETE n")
