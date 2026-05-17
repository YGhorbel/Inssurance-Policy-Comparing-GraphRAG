"""Contract test for evaluation.harness.

Phase 1 scaffolds the runner contract; Phase 5 will add concrete runners.
This test confirms the contract works end-to-end with a fake in-memory
runner so the surface is locked.

Run from repo root:  python3 evaluation/test_harness_contract.py
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import yaml  # noqa: F401
except ImportError:
    print("SKIP: PyYAML not installed; harness contract test skipped.")
    raise SystemExit(0)

from evaluation.harness import Query, QueryResult, Runner, load_query_set
from evaluation.metrics.latency import latency_ms
from evaluation.metrics.ranking import (
    mrr,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


class _FakeRunner(Runner):
    mode = "fake"

    def run_one(self, query: Query) -> QueryResult:
        with latency_ms() as sw:
            chunks = ["c1", "c2", "c3"]
        return QueryResult(
            query=query.query,
            mode=self.mode,
            retrieved_chunks=chunks,
            ranks=[1, 2, 3],
            scores=[0.9, 0.6, 0.3],
            generated_answer="stub",
            latency_ms=sw.elapsed_ms,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )


def test_load_query_set_and_round_trip() -> None:
    queries = load_query_set("evaluation/queries/example.yaml")
    assert len(queries) >= 1
    assert all(q.query for q in queries)

    tmp = tempfile.mkdtemp(prefix="rrf_harness_")
    runner = _FakeRunner(results_dir=tmp)
    out = runner.run("evaluation/queries/example.yaml")
    assert out.startswith(tmp) and out.endswith(".jsonl")
    with open(out, "r", encoding="utf-8") as fh:
        lines = [json.loads(l) for l in fh if l.strip()]
    assert len(lines) == len(queries)
    assert lines[0]["mode"] == "fake"
    assert lines[0]["retrieved_chunks"] == ["c1", "c2", "c3"]
    assert isinstance(lines[0]["latency_ms"], int)


def test_ranking_metrics_match_hand_math() -> None:
    retrieved = ["a", "b", "c", "d", "e"]
    relevant = {"b", "d", "z"}

    assert recall_at_k(retrieved, relevant, 3) == 1 / 3
    assert recall_at_k(retrieved, relevant, 5) == 2 / 3
    assert precision_at_k(retrieved, relevant, 3) == 1 / 3
    assert reciprocal_rank(retrieved, relevant) == 1 / 2

    batch = mrr(
        [["a", "b", "c"], ["x", "y", "z"]],
        [{"b"}, {"y"}],
    )
    assert abs(batch - ((1 / 2 + 1 / 2) / 2)) < 1e-9


if __name__ == "__main__":
    test_load_query_set_and_round_trip()
    test_ranking_metrics_match_hand_math()
    print("OK: all 2 harness-contract tests passed.")
