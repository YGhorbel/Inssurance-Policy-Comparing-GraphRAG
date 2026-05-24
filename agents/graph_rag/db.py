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

    def explain_estimated_rows(self, query, params=None):
        """Subtask H + Amendment 5: run EXPLAIN <query>, walk the query
        plan tree, return the maximum ``EstimatedRows`` reported by any
        operator.

        Returns:
          - int: worst-case estimated rows across the plan tree
          - None: driver unavailable, EXPLAIN failed to compile, or no
                  EstimatedRows arguments present (older Neo4j versions).
                  Callers treat None as fail-open (execute the query).
        """
        if not self.driver:
            return None
        try:
            with self.driver.session() as session:
                result = session.run("EXPLAIN " + query, params or {})
                summary = result.consume()
                plan = summary.plan or summary.profile
        except Exception as e:
            print(f"EXPLAIN error: {str(e)[:120]}")
            return None
        if plan is None:
            return None

        max_rows = 0
        seen = False

        def _walk(node):
            nonlocal max_rows, seen
            args = getattr(node, "arguments", None) or {}
            for key in ("EstimatedRows", "estimatedRows", "Estimated Rows"):
                if key in args:
                    try:
                        rows = float(args[key])
                        seen = True
                        if rows > max_rows:
                            max_rows = rows
                    except Exception:
                        pass
                    break
            for child in (getattr(node, "children", None) or []):
                _walk(child)

        _walk(plan)
        return int(max_rows) if seen else None

    def close(self):
        if self.driver:
            self.driver.close()
