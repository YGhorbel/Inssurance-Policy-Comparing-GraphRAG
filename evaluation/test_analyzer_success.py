"""Deterministic test for the analyzer extraction-success-rate aggregator.

Run from repo root:  python3 evaluation/test_analyzer_success.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.metrics.analyzer_success import extraction_success_rate


def _write(path: str, rows: list) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_corpus_rate_matches_hand_math() -> None:
    tmp = tempfile.mkdtemp(prefix="rrf_metric_")
    _write(os.path.join(tmp, "analyzer_totals.jsonl"), [
        {"extractor": "keywords", "source_document": "a.pdf", "total_calls": 10},
        {"extractor": "keywords", "source_document": "b.pdf", "total_calls": 5},
        {"extractor": "questions", "source_document": "a.pdf", "total_calls": 10},
    ])
    _write(os.path.join(tmp, "analyzer_failures.jsonl"), [
        {"extractor": "keywords", "source_document": "a.pdf", "error_type": "no_json_match"},
        {"extractor": "keywords", "source_document": "a.pdf", "error_type": "json_decode_error"},
        {"extractor": "questions", "source_document": "a.pdf", "error_type": "no_json_match"},
    ])

    r = extraction_success_rate(log_dir=tmp)

    assert r["total_calls"] == 25
    assert r["failures"] == 3
    assert abs(r["success_rate"] - (22 / 25)) < 1e-9

    assert r["per_document"]["a.pdf"]["total_calls"] == 20
    assert r["per_document"]["a.pdf"]["failures"] == 3
    assert abs(r["per_document"]["a.pdf"]["success_rate"] - (17 / 20)) < 1e-9
    assert r["per_document"]["b.pdf"]["failures"] == 0
    assert r["per_document"]["b.pdf"]["success_rate"] == 1.0

    assert r["per_extractor"]["keywords"]["total_calls"] == 15
    assert r["per_extractor"]["keywords"]["failures"] == 2


def test_missing_totals_raises() -> None:
    tmp = tempfile.mkdtemp(prefix="rrf_metric_no_totals_")
    _write(os.path.join(tmp, "analyzer_failures.jsonl"), [
        {"extractor": "keywords", "source_document": "a.pdf"},
    ])
    try:
        extraction_success_rate(log_dir=tmp)
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError when totals are missing")


if __name__ == "__main__":
    test_corpus_rate_matches_hand_math()
    test_missing_totals_raises()
    print("OK: all 2 analyzer-success-rate tests passed.")
