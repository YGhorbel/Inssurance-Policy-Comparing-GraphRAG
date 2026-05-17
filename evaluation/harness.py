"""Top-level evaluation harness contract.

Concrete benchmark runners live under evaluation/runners/ and subclass
``Runner`` here. Phase 5 will wire them up; Phase 1 only ships the
contract so the surface is locked before the experiments begin.

A query set is a YAML file:

    - query: "What requirements does the Tunisian Insurance Code impose?"
      expected_chunks: ["chunk-id-1", "chunk-id-2"]      # optional
      tags: ["tunisia", "auto"]                          # optional

A run produces one JSONL file under evaluation/results/ with one line per
query:

    {
      "query": "...",
      "mode": "rrf" | "vector_only" | ...,
      "retrieved_chunks": [chunk_id, ...],
      "ranks": [1, 2, 3, ...],
      "scores": [0.8, 0.6, ...],
      "generated_answer": "...",
      "latency_ms": 1234,
      "timestamp": "ISO-8601 Z"
    }
"""

from __future__ import annotations

import abc
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class Query:
    query: str
    expected_chunks: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


def load_query_set(path: str) -> List[Query]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load YAML query sets.")
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or []
    out: List[Query] = []
    for row in raw:
        if not isinstance(row, dict) or not row.get("query"):
            continue
        out.append(Query(
            query=row["query"],
            expected_chunks=list(row.get("expected_chunks") or []),
            tags=list(row.get("tags") or []),
        ))
    return out


@dataclass
class QueryResult:
    query: str
    mode: str
    retrieved_chunks: List[str]
    ranks: List[int]
    scores: List[float]
    generated_answer: str
    latency_ms: int
    timestamp: str


class Runner(abc.ABC):
    """Subclasses live under evaluation/runners/ and implement run_one()."""

    mode: str = "abstract"

    def __init__(self, results_dir: str = "evaluation/results") -> None:
        self.results_dir = results_dir

    @abc.abstractmethod
    def run_one(self, query: Query) -> QueryResult:
        """Execute one query end-to-end. Implementers must return a
        fully populated QueryResult, including latency_ms and timestamp.
        Phase 5 will wire concrete subclasses to the MCP /mcp endpoint."""

    def run(self, query_set_path: str) -> str:
        """Run a YAML query set and write JSONL results. Returns the path
        of the produced JSONL file. Implementations should generally not
        override this method."""
        queries = load_query_set(query_set_path)
        os.makedirs(self.results_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(query_set_path))[0]
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        out_path = os.path.join(self.results_dir, f"{self.mode}_{stem}_{ts}.jsonl")
        with open(out_path, "w", encoding="utf-8") as fh:
            for q in queries:
                res = self.run_one(q)
                fh.write(json.dumps(res.__dict__, ensure_ascii=False) + "\n")
        return out_path


__all__ = ["Query", "QueryResult", "Runner", "load_query_set"]
