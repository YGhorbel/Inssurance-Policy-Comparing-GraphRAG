"""Ranking quality metrics for retrieval evaluation.

Phase 1 ships the metric primitives; Phase 5 calls them over the JSONL
result files produced by harness Runners.
"""

from __future__ import annotations

from typing import Iterable, Sequence


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of relevant items captured in the top-k of retrieved."""
    rel = set(relevant)
    if not rel:
        return 0.0
    top = list(retrieved[:k])
    hits = sum(1 for r in top if r in rel)
    return hits / len(rel)


def precision_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of top-k retrieved items that are relevant."""
    if k <= 0:
        return 0.0
    rel = set(relevant)
    top = list(retrieved[:k])
    if not top:
        return 0.0
    hits = sum(1 for r in top if r in rel)
    return hits / min(k, len(top))


def reciprocal_rank(retrieved: Sequence[str], relevant: Iterable[str]) -> float:
    """1 / rank of the first relevant hit (1-indexed); 0 if none in list."""
    rel = set(relevant)
    for index, doc in enumerate(retrieved):
        if doc in rel:
            return 1.0 / (index + 1)
    return 0.0


def mrr(rankings: Iterable[Sequence[str]], relevants: Iterable[Iterable[str]]) -> float:
    """Mean reciprocal rank across a batch of (ranking, relevant) pairs."""
    rrs = []
    for retrieved, rel in zip(rankings, relevants):
        rrs.append(reciprocal_rank(retrieved, rel))
    return sum(rrs) / len(rrs) if rrs else 0.0


__all__ = ["recall_at_k", "precision_at_k", "reciprocal_rank", "mrr"]
