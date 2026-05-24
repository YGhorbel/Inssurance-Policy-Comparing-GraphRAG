# Security

Phase 2 hardening for the MCP-based multi-agent pipeline. Three guard
modules sit on the boundaries where untrusted input (storage object
names, outbound URLs, LLM-generated Cypher, document text fed to the
summarizer) flows into trusted components (filesystem, network,
Neo4j, the LLM context).

| Subtask | Module | Threat model | Logged at |
|---|---|---|---|
| F | `core/mcp/url_guard.py` | SSRF (metadata IMDS, RFC1918, link-local, arbitrary external hosts) | `logs/mcp_url_rejections.jsonl` |
| F | `core/mcp/path_guard.py` | Path traversal in MinIO keys + local filesystem destinations | `logs/mcp_path_rejections.jsonl` |
| G | `agents/shared/pi_guard.py` | Indirect prompt injection from document content | `logs/pi_quarantine.jsonl` |
| H | `agents/graph_rag/builder.py::_execute` | Runaway Cypher cardinality on validated MERGE/MATCH | `logs/cypher_rejections.jsonl` (`reason="explain_cardinality_exceeded"`) |

All four log files live under `logs/` (gitignored, configurable via
`AGENT_LOG_DIR`). Records are append-only JSONL — one event per line —
so post-hoc audit and paper §2.5/§2.6 attempt-rate reporting are
mechanical.

## Subtask F — SSRF + path-traversal guards

### `validate_url(url, *, context, allowlist=None) -> str`

Defensive checks in order:

1. **Parse.** Reject malformed input, missing scheme, missing host.
2. **HTTPS-only.** `http://` is allowed only when host is in
   `_HTTP_ALLOWED_HOSTS` (`localhost`, `127.0.0.1`, `::1`) so the
   intra-stack Qdrant/Neo4j/MinIO calls still work.
3. **Allowlist.** The host must match the default allowlist (Ollama
   Cloud, HuggingFace, GitHub LFS, localhost) ∪ the per-call extra
   ∪ the `MCP_URL_ALLOWLIST` env var (comma-separated).
4. **Resolve.** Hostnames are resolved via `socket.getaddrinfo`; any
   result in 169.254.169.254, RFC1918, link-local, multicast,
   unspecified, or reserved ranges is rejected. Resolution failure is
   treated as a refusal (fail-closed).

Rejections write a `{context, reason, url_prefix (≤120 chars), host}`
record to `logs/mcp_url_rejections.jsonl`. The full URL is **not**
logged because query strings can carry secrets.

Exception type: `SSRFGuardError`.

### `validate_object_name(name, *, context) -> str`

Storage-side guard. Accepts forward-slash-separated relative segments
of length 1..512. Rejects absolute paths (`/etc/passwd`), traversal
segments (`..`, `.`), backslashes, NUL/CR/LF bytes, double slashes,
leading/trailing slash, empty segments.

### `validate_local_path(path, *, allowed_root, context, must_exist=False) -> str`

Filesystem-side guard. Resolves symlinks and `..` via `os.path.realpath`,
then asserts `commonpath([allowed_root, resolved]) == allowed_root`.
This catches symlinks pointing outside the root (the standard pitfall
of pure-string traversal checks).

### Where wired

| Call site | Guard |
|---|---|
| `agents/document_access/minio.py::MinioHandler.download_document(object_name, local_path)` | `validate_object_name(object_name)` + `validate_local_path(local_path, allowed_root=tempfile.gettempdir())` |
| `agents/document_access/agent.py::get_document_path(filename)` | Writes under `tempfile.gettempdir()` so `validate_local_path` accepts the destination — consistent with the MCP-tool contract. |

The duplicate MinIO handler at `ingestion/minio_loader.py` is **not**
wired in this commit; that handler is retired in the Phase 2 wrap
(namespace-migration commit).

`url_guard` ships in-tree but has no MCP-tool consumer yet — the
canonical pipeline does not currently expose a URL-taking tool. The
guard is in place for the prompted §2.5 paper closure and for the
next time someone adds a tool like "fetch reference document at URL"
(which would otherwise be a textbook SSRF surface).

### Tests

`evaluation/test_mcp_guards.py` — 24 tests, all stdlib, all pass:

- 10 object-name cases (accept simple keys; reject absolute, traversal,
  backslash, NUL, double-slash, empty, overly long)
- 4 local-path cases (accept inside root; reject outside, traversal,
  NUL byte)
- 10 URL cases (accept Ollama / HF / localhost; reject http-external,
  IMDS, RFC1918 literal, unknown host, missing scheme, empty; accept
  per-call extra allowlist)

Run: `.venv/bin/python -m evaluation.test_mcp_guards`.

## Subtask G — Prompt-injection guard

*Filed in this doc when G lands.*

## Subtask H — EXPLAIN cardinality guard

*Filed in this doc when H lands.*
