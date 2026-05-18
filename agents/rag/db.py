from typing import Optional

import uuid
import yaml
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from agents.shared.embeddings import get_embedder


class QdrantHandler:
    def __init__(self, config_path: str = "configs/config.yaml", collection_name: Optional[str] = None):
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
        except Exception:
            cfg = {}
        qcfg = cfg.get("qdrant", {})
        self.client = QdrantClient(url=qcfg.get("url", "http://localhost:6333"))
        self.collection_name = collection_name or qcfg.get("collection", "regulations_chunks_v2")

        self.embedder = get_embedder(config_path=config_path)
        self.sparse_enabled = bool(cfg.get("embeddings", {}).get("sparse_enabled", True))
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        try:
            self.client.get_collection(self.collection_name)
            return
        except Exception:
            pass

        vectors_cfg = {"dense": qmodels.VectorParams(size=self.embedder.dim, distance=qmodels.Distance.COSINE)}
        sparse_cfg = {"sparse": qmodels.SparseVectorParams()} if self.sparse_enabled else None
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=vectors_cfg,
                sparse_vectors_config=sparse_cfg,
            )
        except Exception:
            try:
                self.client.recreate_collection(
                    collection_name=self.collection_name,
                    vectors_config=vectors_cfg,
                    sparse_vectors_config=sparse_cfg,
                )
            except Exception as exc:
                print(f"Qdrant collection creation failed: {str(exc)[:120]}")

    def ingest_chunks(self, chunks, batch_size: int = 32) -> bool:
        if not chunks:
            return False

        texts = [chunk["text"] for chunk in chunks]
        try:
            hybrids = self.embedder.encode_hybrid(texts)
        except Exception as exc:
            print(f"    > Embedding failed: {str(exc)[:120]}")
            return False

        points = []
        for chunk, hybrid in zip(chunks, hybrids):
            meta = chunk.get("metadata", {})
            vector_struct: dict = {"dense": hybrid["dense"]}
            if "sparse" in hybrid:
                vector_struct["sparse"] = qmodels.SparseVector(
                    indices=hybrid["sparse"]["indices"],
                    values=hybrid["sparse"]["values"],
                )
            points.append(qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector_struct,
                payload={"text": chunk["text"], **meta},
            ))

        total = len(points)
        for i in range(0, total, batch_size):
            batch = points[i:i + batch_size]
            try:
                self.client.upsert(collection_name=self.collection_name, points=batch)
                print(f"    > Qdrant: uploaded batch {i // batch_size + 1}/{(total + batch_size - 1) // batch_size}")
            except Exception as exc:
                print(f"    > Qdrant batch upload error: {str(exc)[:120]}")
                return False
        return True

    def search(self, query: str, top_k: int = 5):
        hybrid = self.embedder.encode_hybrid([query])[0]
        try:
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=hybrid["dense"],
                using="dense",
                limit=top_k,
                with_payload=True,
            ).points
        except Exception:
            try:
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=("dense", hybrid["dense"]),
                    limit=top_k,
                )
            except Exception as exc:
                print(f"    > Qdrant search error: {str(exc)[:120]}")
                return []

        out = []
        for hit in results:
            payload = getattr(hit, "payload", None) or {}
            score = getattr(hit, "score", None)
            text = payload.get("text", "")
            out.append({"text": text, "score": score, "metadata": payload})
        return out
