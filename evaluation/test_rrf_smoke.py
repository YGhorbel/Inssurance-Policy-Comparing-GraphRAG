"""Smoke tests for Reciprocal Rank Fusion (Cormack et al., SIGIR 2009).

Run from repo root:  python evaluation/test_rrf_smoke.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.shared.fusion import reciprocal_rank_fusion


def test_identical_rankings_double_scores() -> None:
    ranking = ["a", "b", "c"]
    fused = reciprocal_rank_fusion([ranking, ranking])
    fused_order = [doc for doc, _score in fused]
    assert fused_order == ranking, f"order changed: {fused_order}"

    scores = dict(fused)
    expected = {"a": 2 / 61, "b": 2 / 62, "c": 2 / 63}
    for doc, exp in expected.items():
        assert abs(scores[doc] - exp) < 1e-12, f"{doc}: {scores[doc]} != {exp}"


def test_rank1_in_B_outscores_rank5_in_A() -> None:
    ranking_a = ["x1", "x2", "x3", "x4", "only_in_A"]
    ranking_b = ["only_in_B", "y2", "y3", "y4", "y5"]
    fused = dict(reciprocal_rank_fusion([ranking_a, ranking_b]))
    assert fused["only_in_B"] > fused["only_in_A"], (
        f"only_in_B={fused['only_in_B']} not > only_in_A={fused['only_in_A']}"
    )


def test_rank1_in_both_equals_two_over_sixty_one() -> None:
    fused = dict(reciprocal_rank_fusion([["d"], ["d"]]))
    expected = 2 / (60 + 1)
    assert round(fused["d"], 6) == round(expected, 6), (
        f"{fused['d']} != {expected}"
    )


if __name__ == "__main__":
    test_identical_rankings_double_scores()
    test_rank1_in_B_outscores_rank5_in_A()
    test_rank1_in_both_equals_two_over_sixty_one()
    print("OK: all 3 RRF smoke tests passed.")
