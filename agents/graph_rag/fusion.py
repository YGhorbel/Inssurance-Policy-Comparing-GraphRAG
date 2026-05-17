from typing import Any, Dict, List, Tuple
from qdrant_client import QdrantClient
from agents.graph_rag.db import Neo4jHandler
from agents.shared.fusion import reciprocal_rank_fusion
from core.llm.client import get_llm_client
import yaml


class GraphRAG:
    """Hybrid retrieval: Qdrant vector search fused with Neo4j graph-driven
    chunk expansion using Reciprocal Rank Fusion (Cormack et al., SIGIR 2009,
    k=60).

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
        results = []
        for term in seed_terms:
            q = (
                "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($t) "
                "OPTIONAL MATCH (n)-[r]-(m) RETURN n, r, m LIMIT 50"
            )
            rows = self.db.execute_query(q, {"t": term})
            results.extend(rows or [])
        return results

    @staticmethod
    def _hit_id(hit: Any) -> Any:
        """Extract a stable id from a Qdrant hit, preferring chunk_id in payload."""
        payload = getattr(hit, "payload", None)
        if payload is None and isinstance(hit, dict):
            payload = hit.get("payload", {})
        payload = payload or {}
        chunk_id = payload.get("chunk_id")
        if chunk_id:
            return chunk_id
        return getattr(hit, "id", None) or (hit.get("id") if isinstance(hit, dict) else None)

    @staticmethod
    def _hit_payload(hit: Any) -> Dict[str, Any]:
        payload = getattr(hit, "payload", None)
        if payload is None and isinstance(hit, dict):
            payload = hit.get("payload", {})
        return payload or {}

    @staticmethod
    def _entity_names_from_graph_rows(rows: List[Any]) -> List[str]:
        """Pull entity .name values out of Neo4j (n, r, m) result rows in order."""
        names: List[str] = []
        seen: set = set()
        for row in rows or []:
            for key in ("n", "m"):
                node = None
                if isinstance(row, dict):
                    node = row.get(key)
                else:
                    node = getattr(row, key, None)
                if node is None:
                    continue
                name = None
                if isinstance(node, dict):
                    name = node.get("name")
                else:
                    name = getattr(node, "name", None)
                    if name is None:
                        try:
                            name = node["name"]
                        except Exception:
                            name = None
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
        return names

    def _graph_chunk_ranking(
        self,
        entity_names: List[str],
        embedder,
        top_k: int,
    ) -> Tuple[List[Any], Dict[Any, Dict[str, Any]]]:
        """For each graph-derived entity, find chunks via Qdrant vector search.

        Returns (ordered_chunk_ids, id_to_payload). Order preserves first
        occurrence across the per-entity searches; duplicates are dropped so
        the resulting list is a clean ranking suitable for RRF.
        """
        ordered_ids: List[Any] = []
        seen: set = set()
        payloads: Dict[Any, Dict[str, Any]] = {}
        for name in entity_names:
            try:
                vec = embedder.encode(name)
            except Exception:
                continue
            hits = self._vector_search(vec, top_k=top_k)
            for hit in hits:
                cid = self._hit_id(hit)
                if cid is None or cid in seen:
                    continue
                seen.add(cid)
                ordered_ids.append(cid)
                payloads[cid] = self._hit_payload(hit)
        return ordered_ids, payloads

    def retrieve(self, query: str, embedder, top_k=5) -> Dict:
        q_vec = embedder.encode(query)

        vec_hits = self._vector_search(q_vec, top_k=top_k)

        vector_ranking: List[Any] = []
        id_to_payload: Dict[Any, Dict[str, Any]] = {}
        seed_terms: List[str] = []
        for hit in vec_hits:
            payload = self._hit_payload(hit)
            cid = self._hit_id(hit)
            if cid is None:
                continue
            vector_ranking.append(cid)
            id_to_payload[cid] = payload

            meta = payload.get("metadata", {}) or {}
            country = meta.get("country") or payload.get("country")
            summary_text = payload.get("summary", "")
            if country:
                seed_terms.append(country)
            if summary_text:
                seed_terms.extend(summary_text.split()[:5])

        graph_evidence = self._expand_graph(seed_terms)
        entity_names = self._entity_names_from_graph_rows(graph_evidence)
        graph_ranking, graph_payloads = self._graph_chunk_ranking(
            entity_names, embedder, top_k=top_k
        )
        for cid, payload in graph_payloads.items():
            id_to_payload.setdefault(cid, payload)

        fused = reciprocal_rank_fusion([vector_ranking, graph_ranking])
        fused_payloads: List[Dict[str, Any]] = [
            id_to_payload[cid] for cid, _score in fused[:top_k] if cid in id_to_payload
        ]

        context_text = "\n\n".join([p.get("summary", "") for p in fused_payloads])
        graph_text = str(graph_evidence)[:2000]

        synth_prompt = (
            "Given the following document summaries and graph evidence, produce a concise comparison and identify gaps:\n\n"
            "Document Summaries:\n" + context_text + "\n\nGraph Evidence:\n" + graph_text + "\n\nAnswer:"
        )

        synthesis = self.llm.generate(synth_prompt)

        return {"vector_hits": fused_payloads, "graph": graph_evidence, "synthesis": synthesis}


__all__ = ["GraphRAG"]
