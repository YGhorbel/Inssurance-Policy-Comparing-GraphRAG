"""Summary-Augmented Chunking (SAC).

Generates a short (≤150 char) document-level summary ONCE per document and
prepends it to each chunk's text *at encoding time only*. The chunk
payload stored in Qdrant keeps the original chunk text intact — only the
embedded vector sees the prefix. This mirrors Anthropic's Contextual
Retrieval pattern (Sept 2024): the dense vector captures the
document-wide context that a 768-char chunk would otherwise lose.

Cache invalidation key per Phase 2 Amendment 3: (file_hash,
prompt_version). Identical content with the same prompt version reuses
the cached summary; a prompt change bumps SAC_PROMPT_VERSION and forces
re-computation on next ingest. The cache lives at
``data/sac/cache_v{N}.json`` (``data/`` is gitignored).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Optional

from core.llm.client import get_llm_client

SAC_PROMPT_VERSION = 1
SAC_MAX_PREFIX_CHARS = 150
DEFAULT_CACHE_DIR = os.path.join("data", "sac")
_BODY_EXCERPT_CHARS = 4000

_PROMPT = (
    "Summarize the following document in ONE concise sentence focused on "
    "the main subject and key entities. Output ONLY the summary text, no "
    "preamble, no quotes, no markdown. Keep it under 150 characters.\n\n"
    "Document:\n{body}"
)

_CACHE_LOCK = threading.Lock()
_CACHE: Optional[dict] = None
_CACHE_FILE: Optional[str] = None


def _file_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()


def _cache_path(cache_dir: str = DEFAULT_CACHE_DIR) -> str:
    return os.path.join(cache_dir, f"cache_v{SAC_PROMPT_VERSION}.json")


def _load_cache(cache_dir: str = DEFAULT_CACHE_DIR) -> dict:
    global _CACHE, _CACHE_FILE
    path = _cache_path(cache_dir)
    with _CACHE_LOCK:
        if _CACHE is not None and _CACHE_FILE == path:
            return _CACHE
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    _CACHE = json.load(fh)
            except Exception:
                _CACHE = {}
        else:
            _CACHE = {}
        _CACHE_FILE = path
        return _CACHE


def _save_cache() -> None:
    with _CACHE_LOCK:
        if _CACHE is None or _CACHE_FILE is None:
            return
        os.makedirs(os.path.dirname(_CACHE_FILE) or ".", exist_ok=True)
        tmp = _CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(_CACHE, fh, indent=2)
        os.replace(tmp, _CACHE_FILE)


def sac_summary(body: str, cache_dir: str = DEFAULT_CACHE_DIR) -> str:
    """Return a cached or freshly-generated ≤150-char summary of ``body``.

    Cache key: SHA-256 of ``body``, scoped by ``SAC_PROMPT_VERSION``.
    Empty body returns empty string. LLM failures fall back to the empty
    string (the caller then encodes the bare chunk text — equivalent to
    SAC-off for that document).
    """
    if not body:
        return ""
    cache = _load_cache(cache_dir)
    key = _file_hash(body)[:16]
    entry = cache.get(key)
    if entry and entry.get("prompt_version") == SAC_PROMPT_VERSION:
        return entry.get("summary") or ""

    body_excerpt = body[:_BODY_EXCERPT_CHARS]
    try:
        llm = get_llm_client()
        raw = llm.generate(_PROMPT.format(body=body_excerpt)) or ""
    except Exception:
        raw = ""
    summary = " ".join(raw.split())[:SAC_MAX_PREFIX_CHARS].strip()

    cache[key] = {"summary": summary, "prompt_version": SAC_PROMPT_VERSION}
    _save_cache()
    return summary


def prefix_chunk(chunk_text: str, summary: str) -> str:
    """Prepend the summary to the chunk for embedding-only use.

    Callers MUST keep the original ``chunk_text`` in the Qdrant payload
    (i.e. only the embedded vector should see the prefixed string),
    otherwise downstream consumers will see the same summary repeated
    across every chunk of the same document.
    """
    if not summary:
        return chunk_text
    return f"{summary}\n\n{chunk_text}"


def cache_stats(cache_dir: str = DEFAULT_CACHE_DIR) -> dict:
    """Inspect the on-disk SAC cache (for ops/diagnostics)."""
    cache = _load_cache(cache_dir)
    versions: dict = {}
    for entry in cache.values():
        v = entry.get("prompt_version")
        versions[v] = versions.get(v, 0) + 1
    return {
        "cache_file": _cache_path(cache_dir),
        "total_entries": len(cache),
        "by_prompt_version": versions,
        "current_prompt_version": SAC_PROMPT_VERSION,
    }


__all__ = [
    "sac_summary",
    "prefix_chunk",
    "cache_stats",
    "SAC_PROMPT_VERSION",
    "SAC_MAX_PREFIX_CHARS",
]
