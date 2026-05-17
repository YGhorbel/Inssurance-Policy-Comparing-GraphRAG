"""Append-only JSONL logging for agent failure events.

Two consumers in Phase 1:
- agents/graph_rag/validator.py writes cypher_rejections.jsonl
- agents/analyzer/pipeline.py writes analyzer_failures.jsonl and
  analyzer_totals.jsonl

Each log file lives under logs/ at the repo root (gitignored). The writer
opens in append mode for every call to keep the API stateless and crash-safe;
the per-call open cost is negligible at our throughput.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import threading
from typing import Any, Mapping

_LOG_DIR = os.environ.get("AGENT_LOG_DIR", "logs")
_LOCK = threading.Lock()


def _ensure_dir() -> None:
    os.makedirs(_LOG_DIR, exist_ok=True)


def log_event(filename: str, event: Mapping[str, Any]) -> None:
    """Append one JSON event as a line to logs/<filename>.

    A timestamp field is injected if the caller did not provide one.
    Failures inside the logger are swallowed so callers never raise on log writes.
    """
    payload = dict(event)
    payload.setdefault("timestamp", _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z")
    line = json.dumps(payload, ensure_ascii=False, default=str)
    try:
        with _LOCK:
            _ensure_dir()
            with open(os.path.join(_LOG_DIR, filename), "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:
        pass


def log_dir() -> str:
    return _LOG_DIR


__all__ = ["log_event", "log_dir"]
