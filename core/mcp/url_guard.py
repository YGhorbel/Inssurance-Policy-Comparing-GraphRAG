"""SSRF guard for MCP tools that fetch URLs.

Threat model (paper §2.5): an attacker who controls an MCP tool argument
that ends up in an outbound HTTP request can pivot to:

- cloud metadata services (169.254.169.254 / IMDS, GCP metadata.google.internal),
- the loopback (127.0.0.1, ::1) — services bound only locally,
- RFC1918 private ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16),
- link-local (169.254.0.0/16) and unspecified (0.0.0.0/8) ranges,
- arbitrary external hosts (data exfiltration / credential phish).

The guard is HTTPS-only by default, requires the host to appear in an
allowlist of approved endpoints (Ollama Cloud, Qdrant, Neo4j, MinIO,
HuggingFace, GitHub LFS), and resolves the hostname to confirm it does
not point at a private/metadata address even if the hostname itself
looks public. Rejections are appended to ``logs/mcp_url_rejections.jsonl``
so a post-hoc audit can detect attempted SSRF.

Usage::

    from core.mcp.url_guard import validate_url, SSRFGuardError
    try:
        url = validate_url(user_supplied_url, context="my_tool")
    except SSRFGuardError as exc:
        return {"error": str(exc)}

Configure allowlist per-call via ``allowlist=[...]`` or set
``MCP_URL_ALLOWLIST=host1.com,host2.com`` in the environment.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Iterable, Optional
from urllib.parse import urlparse

from agents.shared.jsonl_logger import log_event


class SSRFGuardError(ValueError):
    """Raised when a URL fails SSRF validation."""


_DEFAULT_ALLOWLIST = {
    # LLM
    "ollama.com",
    "api.ollama.com",
    # Local infra (always allowed at the host level — port still bound)
    "localhost",
    "127.0.0.1",
    # HuggingFace model downloads (one-shot during ingest)
    "huggingface.co",
    "hf.co",
    "cdn-lfs.huggingface.co",
    # GitHub LFS for the MultiHop-RAG dataset
    "media.githubusercontent.com",
    "raw.githubusercontent.com",
    "api.github.com",
}

_BLOCKED_HOSTS = {
    # Cloud metadata services
    "169.254.169.254",  # AWS, Azure, OpenStack IMDS
    "metadata.google.internal",
    "metadata.aws",
    "metadata.azure.com",
}

_ALLOWED_SCHEMES = {"https"}
# Allow http for the local infra hosts (Qdrant/Neo4j/MinIO run http locally)
_HTTP_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _is_private_or_metadata_ip(host: str) -> bool:
    """Resolve and check whether the host points at a private/metadata range."""
    if host in _BLOCKED_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback and host not in _HTTP_ALLOWED_HOSTS:
            return True
        if ip.is_private:
            return host not in _HTTP_ALLOWED_HOSTS
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            return True
        return False
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except Exception:
            return True
        for info in infos:
            try:
                ip = ipaddress.ip_address(info[4][0])
            except Exception:
                continue
            if str(ip) in _BLOCKED_HOSTS:
                return True
            if ip.is_loopback and host not in _HTTP_ALLOWED_HOSTS:
                return True
            if ip.is_private and host not in _HTTP_ALLOWED_HOSTS:
                return True
            if ip.is_link_local or ip.is_unspecified or ip.is_reserved:
                return True
        return False


def _env_allowlist() -> set:
    raw = os.environ.get("MCP_URL_ALLOWLIST", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _hit_allowlist(host: str, extra: Optional[Iterable[str]] = None) -> bool:
    host = host.lower()
    allow = set(_DEFAULT_ALLOWLIST) | _env_allowlist()
    if extra:
        allow |= {h.lower() for h in extra}
    if host in allow:
        return True
    for entry in allow:
        if entry.startswith(".") and host.endswith(entry):
            return True
        if host.endswith("." + entry):
            return True
    return False


def validate_url(
    url: str,
    *,
    context: str = "unknown",
    allowlist: Optional[Iterable[str]] = None,
) -> str:
    """Return ``url`` if it passes the SSRF guard, else raise SSRFGuardError.

    Check sequence:
      1. Parse the URL (reject malformed).
      2. Scheme must be in {https} unless host is local infra.
      3. Host must be in the allowlist (default + env + per-call extra).
      4. Host must not resolve to a private/metadata IP range.

    Rejections are logged to ``logs/mcp_url_rejections.jsonl`` with the
    context, reason, and the URL prefix (no full URL — could contain
    secrets in query strings).
    """
    if not url or not isinstance(url, str):
        _log_reject(url, context, "empty_or_non_string")
        raise SSRFGuardError("URL must be a non-empty string")

    try:
        parsed = urlparse(url)
    except Exception:
        _log_reject(url, context, "urlparse_failure")
        raise SSRFGuardError(f"Malformed URL: {url[:80]}")

    if not parsed.scheme or not parsed.netloc:
        _log_reject(url, context, "missing_scheme_or_netloc")
        raise SSRFGuardError(f"URL missing scheme or host: {url[:80]}")

    host = (parsed.hostname or "").lower()
    scheme = parsed.scheme.lower()

    if scheme not in _ALLOWED_SCHEMES and host not in _HTTP_ALLOWED_HOSTS:
        _log_reject(url, context, "scheme_not_https", scheme=scheme, host=host)
        raise SSRFGuardError(
            f"Scheme {scheme!r} not allowed (https-only outside loopback)"
        )

    if not _hit_allowlist(host, extra=allowlist):
        _log_reject(url, context, "host_not_in_allowlist", host=host)
        raise SSRFGuardError(f"Host {host!r} not in URL allowlist")

    if _is_private_or_metadata_ip(host):
        _log_reject(url, context, "host_resolves_to_private_or_metadata", host=host)
        raise SSRFGuardError(
            f"Host {host!r} resolves to a private/metadata IP range"
        )

    return url


def _log_reject(url: str, context: str, reason: str, **extra) -> None:
    log_event("mcp_url_rejections.jsonl", {
        "context": context,
        "reason": reason,
        "url_prefix": (url or "")[:120],
        **extra,
    })


__all__ = ["validate_url", "SSRFGuardError"]
