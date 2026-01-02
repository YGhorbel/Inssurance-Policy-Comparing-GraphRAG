from typing import List, Dict
from qdrant_client import QdrantClient
from agents.graph_rag.builder import GraphBuilder
from agents.graph_rag.db import Neo4jHandler
import yaml


class QdrantToNeo4jIngestor:
    """Ingests chunks stored in Qdrant into Neo4j using GraphBuilder."""

    def __init__(self, config_path: str = "configs/config.yaml"):
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        qcfg = cfg.get("qdrant", {})
        url = qcfg.get("url", "http://localhost:6333")
        collection = qcfg.get("collection", "regulations_chunks")

        self.q_client = QdrantClient(url=url)
        self.collection = collection

        self.db = Neo4jHandler(config_path=config_path)
        self.builder = GraphBuilder(self.db)

    def _iterate_points(self, batch_size=100):
        # Basic scroll through all points using cursor pagination if needed
        offset = 0
        while True:
            try:
                res = self.q_client.scroll(collection_name=self.collection, limit=batch_size, offset=offset)
            except Exception:
                # Fallback to retrieval without offset if method not available
                res = self.q_client.get(collection_name=self.collection, limit=batch_size)

            points = getattr(res, 'points', None) or res.get('result', {}).get('points', [])
            if not points:
                break

            for p in points:
                yield p

            offset += batch_size

    def ingest_all(self) -> Dict[str, int]:
        count = 0
        success = 0
        for p in self._iterate_points():
            payload = getattr(p, 'payload', None) or p.get('payload', {})
            # payload expected to contain original_text and metadata
            text = payload.get('original_text') or payload.get('text')
            metadata = payload.get('metadata', {})

            if not text:
                continue

            count += 1
            try:
                ok = self.builder.process_text_chunk(text, metadata)
                if ok:
                    success += 1
            except Exception as e:
                print(f"Graph ingest error for point {p.get('id', '')}: {e}")

        return {"total": count, "ingested": success}


__all__ = ["QdrantToNeo4jIngestor"]
