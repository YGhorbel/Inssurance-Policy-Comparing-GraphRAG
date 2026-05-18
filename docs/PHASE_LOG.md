# Phase log

Chronological record of revision work. Each phase corresponds to a tight
slice of commits on `main`. Use this file to pick up the thread: every
claim points at a commit hash, a file path, or a test suite that can be
re-run.

For architectural overview, see `CLAUDE.md`. For the per-paragraph paper
update notes produced at the end of Phase 1, see the relevant manuscript
revision document.

---

## Phase 0 — Citation patches + hybrid retrieval fusion (closed)

**Goal.** Bring the codebase into agreement with the manuscript's claim
that hybrid retrieval uses Reciprocal Rank Fusion (Cormack, Clarke &
Buettcher, SIGIR 2009) with `k=60`. Previously the merge step concatenated
vector hits and graph evidence into a single LLM prompt — not fusion.

**Commits.**

| Hash | Subject |
|---|---|
| `c5009f2` | `graph_rag: implement Reciprocal Rank Fusion for hybrid retrieval (Cormack et al. 2009, k=60)` |
| `6187afb` | `docs: add CLAUDE.md describing the canonical MCP pipeline` |

**What landed.**

- `agents/shared/fusion.py` — `reciprocal_rank_fusion(rankings, k=60)`,
  stdlib only, 1-indexed ranks, no penalty term for missing documents
  (matches Cormack et al.'s formulation verbatim).
- `agents/graph_rag/fusion.py::GraphRAG.retrieve` — produces two chunk-id
  rankings (Qdrant vector hits + Neo4j-driven entity-to-chunk expansion)
  and fuses them via RRF. The return shape is preserved so HTTP and MCP
  callers do not break.
- `evaluation/test_rrf_smoke.py` — three deterministic assertions on the
  RRF math; included in the gitignore negation pattern so it ships.

**Key design point.** Neo4j nodes do not carry `chunk_id` (the legacy
LLM-Cypher prompt never wrote it), so the graph-side ranking is built by
extracting entity names from graph expansion rows and re-querying Qdrant
for chunks via the same vector path. Both rankings are therefore in the
same `chunk_id` space, which is the precondition RRF needs.

---

## Phase 1 — Engineering integrity (closed)

**Goal.** Retire the legacy pipeline, add schema enforcement to the
LLM-driven graph builder, replace silent JSON fallbacks with structured
logging, and create an evaluation harness scaffold. Phase 1 deliberately
did *not* attempt retrieval methodology upgrades, new agents, or
generation-quality improvements; those are Phase 2/3/4/5 work.

**Commits.**

| Hash | Subtask | Subject |
|---|---|---|
| `cfe3fbb` | A | retire legacy ingestion/query pipeline; consolidate to MCP-based canonical path |
| `16595ba` | B | schema enforcement for LLM-generated Cypher (reconciled 7-edge taxonomy) |
| `9b3f989` | C | structured logging for analyzer JSON-parse failures |
| `f786cb0` | D | evaluation harness scaffold for Phase 5 benchmarks |

### Subtask A — Retire legacy pipeline

568 lines of code moved at 100% rename (`git mv`) into `legacy/`. New code
must not import from there; CLAUDE.md documents the rule. `ingestion/`
and `processing/` survive as thin namespace directories holding three
modules still imported by `agents/analyzer/pipeline.py`
(`ingestion/pdf_loader.py`, `ingestion/minio_loader.py`,
`processing/chunker.py`); full migration under `agents/shared/` is
deferred to Phase 2.

### Subtask B — Schema enforcement (reconciled taxonomy)

The manuscript and the live prompt previously disagreed on the edge
vocabulary. The current MCP-pipeline prompt produced `HAS_POLICY`,
`MENTIONS`, `RELATED_TO`; the manuscript claimed `EQUIVALENT_TO`,
`CONFLICTS_WITH`, `REFERENCES`, `PART_OF`, `DEFINES`. Only `APPLIES_TO`
and `REQUIRES` overlapped. Figure 3.2's reported counts came from a
corpus extracted under an even older (now-`legacy/`) prompt and cannot be
reproduced by the live prompt as committed.

Reconciled taxonomy (committed in code at `agents/graph_rag/validator.py`
and in the prompt at `agents/graph_rag/prompts.py`):

| # | Edge | Direction | Role |
|---|---|---|---|
| 1 | `APPLIES_TO` | directed | scope (Regulation/PolicyType → Country); subsumes legacy `HAS_POLICY` and inverse `REGULATED_BY` |
| 2 | `REQUIRES` | directed | obligation imposition (Regulation/Article → Requirement) |
| 3 | `REFERENCES` | directed | internal and external citation (Article → Article/Regulation) |
| 4 | `EQUIVALENT_TO` | **symmetric** | cross-jurisdictional semantic equivalence — load-bearing for the comparison thesis |
| 5 | `CONFLICTS_WITH` | **symmetric** | cross-jurisdictional contradiction — load-bearing for the gap-analysis thesis |
| 6 | `PART_OF` | directed | structural hierarchy (Article → Regulation; sub-requirement → requirement) |
| 7 | `DEFINES` | directed | definitional anchor (Regulation/Article → Concept/Entity); subsumes the legacy `MENTIONS` use case |

Node label whitelist (9, unchanged): `Regulation, Article, Obligation,
Authority, Entity, Concept, PolicyType, Country, Requirement`.

`agents/graph_rag/validator.py::validate(raw, chunk_id, source_document)`
returns `(accepted_statements, rejections)`. Rejection reasons:

- `not_cypher_or_prose` — opening token outside `{MERGE, MATCH, CREATE, RETURN, WITH, WHERE, SET, UNWIND, OPTIONAL}` or text begins like prose (`The `, `Here `, `**`, …).
- `destructive_keyword` — contains `DROP`, `DELETE`, `REMOVE`, `DETACH DELETE`, `CREATE INDEX`, `CREATE CONSTRAINT`, `CALL apoc.`, or `LOAD CSV`.
- `label_not_in_whitelist` — `(:Label)` references a non-allowed node label.
- `relationship_not_in_whitelist` — `[:TYPE]` references a non-allowed edge.
- `neo4j_execution_failed` — emitted by `agents/graph_rag/builder.py` when an accepted statement fails at runtime.

Every rejection is appended to `logs/cypher_rejections.jsonl` (the path
is configurable via the `AGENT_LOG_DIR` env var; default `logs/` is
gitignored). Each line carries the originating `chunk_id` and source
document so a per-corpus rejection rate can be aggregated cleanly.

CORE-KG-inspired name normalization is applied to the `name` property in
MERGE clauses before execution: leading title/role tokens are stripped
(`the `, `Article `, `Officer `, `Dr. `, …), internal whitespace is
collapsed, and a conservative `.title()` is applied. CORE-KG itself
argues this MVP is insufficient for lexically dense legal text — see the
Honest Gaps section.

### Subtask C — Structured analyzer logging

`agents/analyzer/pipeline.py::_parse_json_from_llm` previously swallowed
parse failures silently. It now appends one record per miss to
`logs/analyzer_failures.jsonl` with the extractor name (`keywords`,
`questions`, `requirements`, `classification`), `chunk_id`,
`source_document`, the first 200 chars of the LLM output, and the error
type (`no_json_match` or `json_decode_error`). The return-value contract
is unchanged — callers still receive `None` and still run their naive
fallback — so external behaviour is identical.

Total LLM-call counts are accumulated in an in-memory `Counter` keyed by
`(extractor, source_document)` and flushed to
`logs/analyzer_totals.jsonl` via an `atexit` handler. Without the flush,
a mid-document SIGKILL would silently inflate apparent success rates
because failure events are written immediately while the denominator is
only persisted at process exit.

Aggregate helper: `evaluation/metrics/analyzer_success.py::extraction_success_rate(log_dir)`
returns `{total_calls, failures, success_rate, per_document, per_extractor}`.
The helper raises `FileNotFoundError` if `analyzer_totals.jsonl` is
missing rather than silently reporting 1.0.

### Subtask D — Evaluation harness scaffold

Phase 1 ships the contract; Phase 5 wires concrete runners.

```
evaluation/
├── __init__.py
├── harness.py                  # Runner ABC + Query / QueryResult dataclasses
├── metrics/
│   ├── analyzer_success.py     # Subtask C aggregator
│   ├── ranking.py              # recall_at_k, precision_at_k, reciprocal_rank, mrr
│   └── latency.py              # latency_ms() context manager
├── queries/example.yaml        # YAML schema demonstration
├── results/.gitkeep            # outputs land here; gitignored except .gitkeep
├── runners/
│   ├── __init__.py
│   └── README.md               # contract docs for Phase 5 authors
├── test_analyzer_success.py
├── test_cypher_validator.py
├── test_harness_contract.py
└── test_rrf_smoke.py
```

Runner contract: a runner subclasses `evaluation.harness.Runner`, sets a
`mode` string, and implements `run_one(query) -> QueryResult`. The base
class iterates a YAML query set, writes JSONL into
`evaluation/results/<mode>_<stem>_<UTC-timestamp>.jsonl`.

---

## Tests (run from repo root)

```bash
python3 evaluation/test_rrf_smoke.py            # 3/3
python3 evaluation/test_cypher_validator.py     # 7/7
python3 evaluation/test_analyzer_success.py     # 2/2
python3 evaluation/test_harness_contract.py     # 2/2  (skips politely if PyYAML missing)
```

All four are deterministic, stdlib-mostly, and do not require Docker or
the LLM stack to be loaded.

---

## Honest gaps (carried forward to Phase 2+)

1. **Phase 1 enforces structural validity, not generation quality.**
   The Text2Cypher benchmark (Ozsoy et al. 2024) reports execution
   accuracy of 9.43%–14.49% for foundational 7B–9B open models on
   zero-shot Cypher; a fine-tuned 3B reaches only 15.22%. The validator
   catches malformed Cypher and logs it; it does not improve the
   generator. No fine-tuning was attempted in Phase 1.

2. **No live runtime-cost guard on accepted Cypher.** `EXPLAIN` dry-run
   for unbounded `MATCH` clauses is deferred to Phase 2 alongside the
   rest of the MCP-security hardening.

3. **Two of Guo et al.'s top three MCP risks are deferred.** Phase 1's
   validator addresses the Cypher-injection risk. Server-side request
   forgery via MinIO/Qdrant tool arguments, and indirect prompt injection
   from document content, are explicitly Phase 2 work.

4. **`compare_policies` Cypher uses an untyped `OPTIONAL MATCH (a)-[r]-(b)`.**
   Tightening it to `[r:EQUIVALENT_TO|CONFLICTS_WITH]` would silently
   regress comparative-query results to empty until corpus reingestion.
   Phase 1 updated only the docstring; the typed query rewrite is Phase 5.

5. **The CORE-KG-style name normalization is the MVP, not the method.**
   Real coreference resolution and alias chaining (CORE-KG's actual
   contribution) requires a sequential type-wise LLM pass and is not
   implemented.

6. **Amendment 7 (post-deletion live `/mcp ingest_documents` smoke) was
   satisfied statically only.** The repo's project Python dependencies
   were not installed in the verification environment, so the runtime
   POST against the live MCP endpoint could not be executed. Static
   evidence: full AST parse over 26 live `.py` files passed with no
   syntax errors and zero remaining imports of `main`, `query`, `graph`,
   or `models` from the live tree. The live ingestion should be replayed
   once dependencies are installed in a CI or local venv.

7. **`ingestion/` and `processing/` are partly-empty namespace
   directories.** Migration under `agents/shared/` is Phase 2. The
   duplicate MinIO handler (`ingestion/minio_loader.py` vs
   `agents/document_access/minio.py`) is part of the same migration.

---

## Numbers a paper reviewer can verify today

- Node label count `= 9` — `agents/graph_rag/validator.py::ALLOWED_NODES`.
- Edge type count `= 7` — `agents/graph_rag/validator.py::ALLOWED_RELATIONSHIPS`;
  symmetric subset `= 2` (`EQUIVALENT_TO`, `CONFLICTS_WITH`).
- Active MCP tools registered `= 23`, across 6 agent modules.
  `grep -c register_tool agents/**/agent.py`.
- LOC retired to `legacy/` `= 568` (12 files moved at 100% rename).
  `find legacy -name '*.py' -exec wc -l {} +`.

## Numbers that require Phase 5 corpus reingestion

- Cypher schema-validation rejection rate (corpus and per-document) —
  mechanism in `logs/cypher_rejections.jsonl`.
- Analyzer extraction success rate (corpus, per-document, per-extractor)
  — mechanism in `evaluation/metrics/analyzer_success.py`.
- Updated Figure 3.2 edge counts under the reconciled taxonomy.
