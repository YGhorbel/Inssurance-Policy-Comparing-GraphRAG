"""Aggregate analyzer extraction-success rates from JSONL logs.

Reads:
  logs/analyzer_failures.jsonl  (one line per parse miss)
  logs/analyzer_totals.jsonl    (one line per (extractor, source_document)
                                 with the call count, flushed at process exit)

Reports a per-document success rate and a corpus-wide rate for §2.4 of the
paper. Defensive against partial logs (atexit may not fire on SIGKILL): a
missing totals file means we cannot report a denominator and the helper
raises rather than silently inflating success.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Dict


def _read_jsonl(path: str) -> list:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def extraction_success_rate(log_dir: str = "logs") -> Dict[str, object]:
    """Compute success rates across the analyzer's four JSON-returning extractors.

    Returns a dict with keys:
      - total_calls (int)
      - failures (int)
      - success_rate (float in [0, 1])
      - per_document (dict[str, dict] with total/failures/success_rate)
      - per_extractor (dict[str, dict] with total/failures/success_rate)
    """
    failures_path = os.path.join(log_dir, "analyzer_failures.jsonl")
    totals_path = os.path.join(log_dir, "analyzer_totals.jsonl")

    if not os.path.exists(totals_path):
        raise FileNotFoundError(
            f"{totals_path} missing; analyzer process did not flush totals. "
            "Rates would be misleading without the denominator."
        )

    totals_per_doc: Dict[str, int] = defaultdict(int)
    totals_per_extractor: Dict[str, int] = defaultdict(int)
    total = 0
    for row in _read_jsonl(totals_path):
        count = int(row.get("total_calls", 0))
        total += count
        totals_per_doc[row.get("source_document") or "<unknown>"] += count
        totals_per_extractor[row.get("extractor") or "<unknown>"] += count

    failures_per_doc: Dict[str, int] = defaultdict(int)
    failures_per_extractor: Dict[str, int] = defaultdict(int)
    fail_total = 0
    for row in _read_jsonl(failures_path):
        fail_total += 1
        failures_per_doc[row.get("source_document") or "<unknown>"] += 1
        failures_per_extractor[row.get("extractor") or "<unknown>"] += 1

    def _rate(denom: int, num_failures: int) -> float:
        if denom <= 0:
            return 0.0
        return max(0.0, min(1.0, (denom - num_failures) / denom))

    per_document = {
        doc: {
            "total_calls": totals_per_doc[doc],
            "failures": failures_per_doc.get(doc, 0),
            "success_rate": _rate(totals_per_doc[doc], failures_per_doc.get(doc, 0)),
        }
        for doc in totals_per_doc
    }
    per_extractor = {
        ex: {
            "total_calls": totals_per_extractor[ex],
            "failures": failures_per_extractor.get(ex, 0),
            "success_rate": _rate(totals_per_extractor[ex], failures_per_extractor.get(ex, 0)),
        }
        for ex in totals_per_extractor
    }

    return {
        "total_calls": total,
        "failures": fail_total,
        "success_rate": _rate(total, fail_total),
        "per_document": per_document,
        "per_extractor": per_extractor,
    }


__all__ = ["extraction_success_rate"]
