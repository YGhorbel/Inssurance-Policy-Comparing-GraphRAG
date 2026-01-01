from neo4j import GraphDatabase
import yaml

class Neo4jHandler:
    def __init__(self, config_path="configs/config.yaml"):
        # Load config
        try:
            with open(config_path, "r") as f:
                self.config = yaml.safe_load(f).get("neo4j", {})
        except Exception:
            self.config = {}

        self.uri = self.config.get("uri", "bolt://localhost:7687")
        self.user = self.config.get("user", "neo4j")
        self.password = self.config.get("password", "password")

        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            print("Neo4j Connected.")
        except Exception as e:
            print(f"Neo4j Connection Failed: {e}")
            self.driver = None

    def execute_query(self, query, params=None):
        if not self.driver:
            return None
        try:
            with self.driver.session() as session:
                result = session.run(query, params or {})
                return [record.data() for record in result]
        except Exception as e:
            print(f"Query Error: {e}")
            return []

    def close(self):
        if self.driver:
            self.driver.close()
