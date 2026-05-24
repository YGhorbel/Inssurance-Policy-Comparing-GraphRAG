"""BGE-reranker-v2-m3 cross-encoder for top-20 → top-K reranking.

Inserted between Qdrant retrieval and the summarizer LLM. The reranker
scores each (query, passage) pair; downstream callers re-sort their
candidates by reranker score before taking the final top-K.

Amendment 4 (Phase 2 approval): on CPU hosts the cross-encoder can
take tens of seconds per query, which would make 100-query benchmarks
infeasible. Each rerank call is wall-clock timed; if the call exceeds
``RERANK_DISABLE_THRESHOLD_S`` (env-tunable, default 15s), the reranker
becomes **sticky-disabled** for the rest of the process and a per-query
tag is appended to ``logs/reranker_disabled.jsonl``. Subsequent
``rerank()`` calls return ``None``, signalling the caller to fall back
to the upstream Qdrant ranking unchanged. This matches Amendment 4's
requirement that the system degrades gracefully on CPU without
abandoning the run.

GPU FP16 hosts will not trip the disable — BGE-reranker-v2-m3 finishes
20-passage rerank in well under a second there.
"""

from __future__ import annotations

import os
import threading
import time
from typing import List, Optional, Sequence

from agents.shared.jsonl_logger import log_event

DEFAULT_MODEL_ID = "BAAI/bge-reranker-v2-m3"
RERANK_DISABLE_THRESHOLD_S = float(os.getenv("RERANK_DISABLE_THRESHOLD_S", "15.0"))

_INSTANCE: Optional["BGEReranker"] = None
_LOCK = threading.Lock()


class BGEReranker:
    """Cross-encoder reranker wrapping ``sentence_transformers.CrossEncoder``.

    Originally used ``FlagEmbedding.FlagReranker`` but that wrapper still
    calls ``tokenizer.prepare_for_model`` which was removed in transformers
    5.8+; ``sentence_transformers.CrossEncoder`` uses the modern
    ``__call__``-based tokenizer API and works against the same
    ``BAAI/bge-reranker-v2-m3`` weights.
    """

    def __init__(self, model_id: str = DEFAULT_MODEL_ID) -> None:
        try:
            import torch
            cuda = bool(torch.cuda.is_available())
        except Exception:
            cuda = False

        from sentence_transformers import CrossEncoder
        print(f"Initializing BGEReranker (model={model_id}, cuda={cuda}).")
        kwargs: dict = {"max_length": 512}
        if cuda:
            kwargs["device"] = "cuda"
        self._model = CrossEncoder(model_id, **kwargs)
        self.model_id = model_id
        self._disabled = False
        self._slow_first_query: Optional[str] = None

    @property
    def disabled(self) -> bool:
        return self._disabled

    def rerank(self, query: str, passages: Sequence[str]) -> Optional[List[float]]:
        """Score each (query, passage) pair.

        Returns a list of floats (one per passage) on success, or ``None``
        when the reranker is disabled (either by a prior slow call or by
        this call exceeding the threshold). Callers must check the return
        and fall back to upstream ranking on ``None``.
        """
        if self._disabled:
            return None
        if not passages:
            return []
        t0 = time.perf_counter()
        pairs = [[query, p] for p in passages]
        scores = self._model.predict(pairs)
        elapsed = time.perf_counter() - t0

        if elapsed > RERANK_DISABLE_THRESHOLD_S:
            self._disabled = True
            self._slow_first_query = query
            log_event("reranker_disabled.jsonl", {
                "query": query[:200],
                "n_passages": len(passages),
                "elapsed_s": elapsed,
                "threshold_s": RERANK_DISABLE_THRESHOLD_S,
                "model_id": self.model_id,
                "reason": "first_slow_query_sticky_disable",
            })
            return None

        if hasattr(scores, "tolist"):
            scores = scores.tolist()
        if isinstance(scores, float):
            scores = [scores]
        return [float(s) for s in scores]


def get_reranker(model_id: str = DEFAULT_MODEL_ID) -> BGEReranker:
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = BGEReranker(model_id=model_id)
        return _INSTANCE


__all__ = ["BGEReranker", "get_reranker", "RERANK_DISABLE_THRESHOLD_S", "DEFAULT_MODEL_ID"]
