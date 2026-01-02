from typing import List, Dict
from qdrant_client import QdrantClient
from agents.graph_rag.db import Neo4jHandler
from core.llm.client import get_llm_client
import yaml


class GraphRAG:
    """Retrieval fusion: vector retrieval from Qdrant + graph neighborhood expansion in Neo4j.

    Returns combined evidence for downstream summarizers/planners.
    """

    def __init__(self, config_path: str = "configs/config.yaml"):
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        qcfg = cfg.get("qdrant", {})
        self.q_client = QdrantClient(url=qcfg.get("url", "http://localhost:6333"))
        self.collection = qcfg.get("collection", "regulations_chunks")

        self.db = Neo4jHandler(config_path=config_path)
        self.llm = get_llm_client()

    def _vector_search(self, query_vector, top_k=5):
        try:
            hits = self.q_client.search(collection_name=self.collection, query_vector=query_vector, limit=top_k)
            return hits
        except Exception:
            return []

    def _expand_graph(self, seed_terms: List[str], depth: int = 1):
        # Simple expansion: find nodes whose name matches seed terms and get neighbors
        results = []
        for term in seed_terms:
            q = (
                "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($t) "
                "OPTIONAL MATCH (n)-[r]-(m) RETURN n, r, m LIMIT 50"
            )
            rows = self.db.execute_query(q, {"t": term})
            results.extend(rows or [])
        return results

    def retrieve(self, query: str, embedder, top_k=5) -> Dict:
        # 1) embed query using provided embedder
        q_vec = embedder.encode(query)

        # 2) vector search
        vec_hits = self._vector_search(q_vec, top_k=top_k)

        # extract seed terms from top results (simple heuristic: metadata country+keywords)
        seed_terms = []
        docs = []
        for h in vec_hits:
            payload = getattr(h, 'payload', None) or h.get('payload', {})
            meta = payload.get('metadata', {})
            docs.append(payload)
            country = meta.get('country')
            keywords = payload.get('summary', '')
            if country:
                seed_terms.append(country)
            if keywords:
                seed_terms.extend(keywords.split()[:5])

        # 3) graph expand
        graph_evidence = self._expand_graph(seed_terms)

        # 4) fuse results and ask LLM for a short synthesis
        context_text = "\n\n".join([d.get('summary', '') for d in docs])
        graph_text = str(graph_evidence)[:2000]

        synth_prompt = (
            "Given the following document summaries and graph evidence, produce a concise comparison and identify gaps:\n\n"
            "Document Summaries:\n" + context_text + "\n\nGraph Evidence:\n" + graph_text + "\n\nAnswer:"
        )

        synthesis = self.llm.generate(synth_prompt)

        return {"vector_hits": docs, "graph": graph_evidence, "synthesis": synthesis}


__all__ = ["GraphRAG"]
