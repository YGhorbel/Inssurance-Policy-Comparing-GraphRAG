"""Path-traversal guard for MCP tools that accept file paths or
storage-object names.

Threat model: an attacker controlling an MCP argument like
``object_name`` (MinIO key) or ``local_path`` (filesystem destination)
can:

- read or overwrite files outside the intended directory via ``../``
  or absolute paths (``/etc/passwd``, ``C:\\Windows\\System32\\…``),
- pivot through symlinks pointing outside the allowed root,
- inject control characters (NUL, CR/LF) into downstream filename
  handlers.

The guard normalises the path, rejects absolute paths, traversal
components, NUL bytes, and (when an ``allowed_root`` is supplied)
confirms the resolved path stays within that root. Rejections are
appended to ``logs/mcp_path_rejections.jsonl``.
"""

from __future__ import annotations

import os
from typing import Optional

from agents.shared.jsonl_logger import log_event


class PathGuardError(ValueError):
    """Raised when a path fails the path-traversal guard."""


_CONTROL_BYTES = {"\x00", "\r", "\n"}


def validate_object_name(name: str, *, context: str = "unknown") -> str:
    """Validate a storage-object name (MinIO key, S3 key).

    Allowed: forward-slash-separated relative segments, total length
    1..512.

    Rejected: absolute paths (``/foo``), traversal (``..``), backslashes,
    control bytes, double slashes, leading/trailing slash, empty.
    """
    if not isinstance(name, str) or not name:
        _log_reject(name, context, "empty_or_non_string")
        raise PathGuardError("Object name must be a non-empty string")
    if len(name) > 512:
        _log_reject(name, context, "name_too_long", length=len(name))
        raise PathGuardError("Object name too long (max 512 chars)")
    for b in _CONTROL_BYTES:
        if b in name:
            _log_reject(name, context, "control_byte_in_name")
            raise PathGuardError("Object name contains control bytes")
    if "\\" in name:
        _log_reject(name, context, "backslash_in_name")
        raise PathGuardError("Object name must use forward slashes only")
    if name.startswith("/"):
        _log_reject(name, context, "absolute_path")
        raise PathGuardError("Object name must be relative (no leading '/')")
    if name.endswith("/"):
        _log_reject(name, context, "trailing_slash")
        raise PathGuardError("Object name must not end with '/'")
    if "//" in name:
        _log_reject(name, context, "double_slash")
        raise PathGuardError("Object name must not contain '//'")
    parts = name.split("/")
    for p in parts:
        if not p:
            _log_reject(name, context, "empty_segment")
            raise PathGuardError("Object name has an empty path segment")
        if p in (".", ".."):
            _log_reject(name, context, "traversal_segment", segment=p)
            raise PathGuardError(f"Object name contains traversal segment {p!r}")
    return name


def validate_local_path(
    path: str,
    *,
    allowed_root: str,
    context: str = "unknown",
    must_exist: bool = False,
) -> str:
    """Validate a filesystem path resolves inside ``allowed_root``.

    Returns the normalised absolute path on success. Symlinks and
    ``..`` are normalised away with ``os.path.realpath``; the result
    must be a descendant of ``realpath(allowed_root)``.
    """
    if not isinstance(path, str) or not path:
        _log_reject(path, context, "empty_or_non_string")
        raise PathGuardError("Local path must be a non-empty string")
    for b in _CONTROL_BYTES:
        if b in path:
            _log_reject(path, context, "control_byte_in_path")
            raise PathGuardError("Local path contains control bytes")
    if not allowed_root:
        raise PathGuardError("allowed_root must be supplied for validate_local_path")
    root = os.path.realpath(os.path.abspath(allowed_root))
    resolved = os.path.realpath(os.path.abspath(path))
    try:
        common = os.path.commonpath([root, resolved])
    except ValueError:
        common = ""
    if common != root:
        _log_reject(path, context, "escapes_allowed_root", root=root, resolved=resolved)
        raise PathGuardError(
            f"Local path {path!r} escapes allowed root {allowed_root!r}"
        )
    if must_exist and not os.path.exists(resolved):
        _log_reject(path, context, "path_does_not_exist", resolved=resolved)
        raise PathGuardError(f"Local path does not exist: {resolved}")
    return resolved


def _log_reject(path: str, context: str, reason: str, **extra) -> None:
    log_event("mcp_path_rejections.jsonl", {
        "context": context,
        "reason": reason,
        "path_prefix": (path if isinstance(path, str) else "")[:200],
        **extra,
    })


__all__ = ["validate_object_name", "validate_local_path", "PathGuardError"]
