"""Multilingual hybrid embedder (BGE-M3).

Single point of entry for all retrieval-side encoding in the canonical
pipeline. Replaces the five hardcoded SentenceTransformer(all-MiniLM-L6-v2)
call sites that existed before Phase 2.

References:
- Chen et al. (2024), "BGE M3-Embedding: Multi-Lingual, Multi-Functionality,
  Multi-Granularity Text Embeddings Through Self-Knowledge Distillation"
  (arXiv 2402.03216). Dense output is the [CLS] embedding (1024-dim,
  cosine); the lexical (sparse) head outputs token-weight dictionaries.
  Multi-vector (ColBERT-style) output is intentionally NOT enabled in
  Phase 2: the +5.1 nDCG it offers comes with a "heavy cost" and is paired
  naturally with Late Chunking, which is deferred to Phase 3.

The wrapper is a process-wide singleton constructed lazily on first call to
``get_embedder()``. CPU-only hosts run in FP32 (FP16 on CPU is unsupported
on most Intel/AMD chips); GPU hosts get FP16 automatically when CUDA is
available. The legacy single-vector ``encode(text)`` shim is kept so call
sites that only need a query vector don't have to thread a dict through.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Iterable, List, Optional, Sequence

import yaml


_INSTANCE: Optional["BGEM3Embedder"] = None
_LOCK = threading.Lock()


def _load_cfg(path: str = "configs/config.yaml") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


class BGEM3Embedder:
    """Hybrid dense + sparse embedder wrapping FlagEmbedding's BGE-M3."""

    def __init__(self, config_path: str = "configs/config.yaml") -> None:
        cfg = _load_cfg(config_path).get("embeddings", {}) or {}
        self.model_id: str = cfg.get("model_id", "BAAI/bge-m3")
        self.dim: int = int(cfg.get("dim", 1024))
        self.sparse_enabled: bool = bool(cfg.get("sparse_enabled", True))
        self.max_length: int = int(cfg.get("max_length", 1024))
        self.batch_size: int = int(cfg.get("batch_size", 8))

        try:
            import torch
            cuda = bool(torch.cuda.is_available())
        except Exception:
            cuda = False
        use_fp16 = cuda

        print(
            f"Initializing BGEM3Embedder (model={self.model_id}, dim={self.dim}, "
            f"sparse={self.sparse_enabled}, fp16={use_fp16})."
        )

        from FlagEmbedding import BGEM3FlagModel
        self._model = BGEM3FlagModel(
            self.model_id,
            use_fp16=use_fp16,
            return_dense=True,
            return_sparse=self.sparse_enabled,
            return_colbert_vecs=False,
            passage_max_length=self.max_length,
            query_max_length=min(self.max_length, 512),
            batch_size=self.batch_size,
        )

    def encode(self, text: str) -> List[float]:
        """SentenceTransformer-shaped shim returning a 1024-dim dense vector.

        Provided for the single-vector retrieval call sites that pre-date
        Phase 2's hybrid index.
        """
        out = self._model.encode(
            [text],
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return out["dense_vecs"][0].tolist()

    def encode_hybrid(self, texts: Sequence[str]) -> List[dict]:
        """Batch-encode for ingestion: returns [{dense: [float], sparse: {...}}, ...].

        Sparse output is the Qdrant-shaped {"indices": [int], "values": [float]}
        derived from BGE-M3's lexical_weights token-id dict.
        """
        if isinstance(texts, str):
            texts = [texts]
        out = self._model.encode(
            list(texts),
            return_dense=True,
            return_sparse=self.sparse_enabled,
            return_colbert_vecs=False,
        )
        dense = out["dense_vecs"]
        sparse_dicts = out.get("lexical_weights") if self.sparse_enabled else None

        records: List[dict] = []
        for idx, _t in enumerate(texts):
            rec: dict = {"dense": dense[idx].tolist()}
            if sparse_dicts is not None:
                lw = sparse_dicts[idx] or {}
                rec["sparse"] = {
                    "indices": [int(k) for k in lw.keys()],
                    "values": [float(v) for v in lw.values()],
                }
            records.append(rec)
        return records

    def get_sentence_embedding_dimension(self) -> int:
        """Compat shim for callers ported from SentenceTransformer."""
        return self.dim


def get_embedder(config_path: str = "configs/config.yaml") -> BGEM3Embedder:
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = BGEM3Embedder(config_path=config_path)
        return _INSTANCE


__all__ = ["BGEM3Embedder", "get_embedder"]
