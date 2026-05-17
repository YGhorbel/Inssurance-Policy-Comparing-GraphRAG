"""Rank fusion utilities for hybrid retrieval.

Implements Reciprocal Rank Fusion (RRF) following:

    Cormack, G. V., Clarke, C. L. A., & Buettcher, S. (2009).
    Reciprocal Rank Fusion outperforms Condorcet and individual rank
    learning methods. In Proceedings of the 32nd International ACM SIGIR
    Conference on Research and Development in Information Retrieval
    (SIGIR '09), pp. 758-759.

The formula combines multiple input rankings into a single fused ranking
using only the rank position of each document in each input list:

    RRFscore(d) = sum over r in R of  1 / (k + rank_r(d))

where R is the set of input rankings, rank_r(d) is the 1-indexed position
of document d in ranking r, and k is a constant that dampens the influence
of top-ranked outlier results while preserving signal from lower-ranked
documents.

The original paper recommends k = 60 based on TREC validation runs. The
authors note the choice is "near-optimal" but "not critical"; we keep it
hardcoded so the implementation matches the paper exactly. If a future
ablation requires sweeping k we will parameterize it then, not now.

Documents that appear in only some of the input rankings contribute zero
from the rankings where they do not appear -- there is no explicit
penalty term in the paper's formulation.
"""

from typing import Hashable, List, Sequence, Tuple


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[Hashable]],
    k: int = 60,
) -> List[Tuple[Hashable, float]]:
    """Fuse multiple rank-ordered lists into a single ranking via RRF.

    Args:
        rankings: A sequence of rankings. Each ranking is a sequence of
            document identifiers in rank order, where index 0 is the
            top-ranked document (rank 1 in the paper's 1-indexed
            convention).
        k: The RRF dampening constant. Defaults to 60 per
            Cormack, Clarke & Buettcher (SIGIR 2009).

    Returns:
        A list of ``(document_id, fused_score)`` tuples sorted by
        ``fused_score`` descending. A document's score is the sum of
        ``1 / (k + rank)`` contributions across every input ranking in
        which it appears; rankings where it does not appear contribute
        nothing (no penalty term, per the original paper).
    """
    scores: dict[Hashable, float] = {}
    for ranking in rankings:
        for index, doc_id in enumerate(ranking):
            rank = index + 1
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


__all__ = ["reciprocal_rank_fusion"]
