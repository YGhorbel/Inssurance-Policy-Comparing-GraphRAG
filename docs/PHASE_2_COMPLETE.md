# Phase 2 — Complete

All 10 Phase 2 subtasks closed. This doc is the reviewer-friendly
roll-up; per-subtask detail lives in `BENCHMARKS.md` (E.x), `SECURITY.md`
(F/G/H), and `PHASE_LOG.md` (chronological).

## Commit lineage

| Hash | Subtask | Subject |
|---|---|---|
| `aa156ba` | A | Phase 2 pre-change baseline + Ollama Cloud LLM routing |
| `df23529` | B | BGE-M3 hybrid embedding swap + atomic collection cutover + planner-route fix |
| `d1eeb20` | E.1 | MultiHop-RAG regression baseline (B-only) |
| `f50452a` | C | Summary-Augmented Chunking (SAC) capability |
| `604bcb9` | E.2 | MultiHop-RAG regression (B+C, SAC chunking) |
| `687bbe6` | D | BGE-reranker-v2-m3 cross-encoder with CPU self-disable |
| `8f00be4` | E.3 | MultiHop-RAG regression (B+C+D, Amendment 4 fired) |
| `caf991a` | E.4 | combined results table + cleanup decision |
| `a458139` | F | SSRF + path-traversal guards |
| `8923961` | G | Prompt-injection guard wired into summarizer |
| `b345bb6` | H | EXPLAIN cardinality guard in GraphBuilder._execute |
| `a47cc6d` | wrap | retire ingestion/ + processing/ namespace dirs |

Plus four doc-only commits.

## Retrieval-quality results (MultiHop-RAG, 100 stratified queries, answerable n=75)

| Run | Recall@2 | Recall@5 | MRR | Notes |
|---|---|---|---|---|
| E.1 (B = BGE-M3) | **0.440** | 0.661 | 0.750 | baseline |
| E.2 (B + C, SAC) | 0.418 | **0.672** | **0.816** | MRR +0.066, R@5 +0.011, R@2 −0.022 |
| E.3 (B + C + D, reranker) | 0.418 | 0.672 | 0.816 | Amendment 4 fired on query 1 (41.6s on CPU); 99/100 fell back to B+C |

**Production recommendation:** B+C. SAC's MRR lift is the biggest
Phase 2 retrieval win. D is in-tree for GPU deployments where its sub-
second rerank latency makes the lift measurable.

## Security guards (paper §2.5 + §2.6)

| Subtask | Module | Audit JSONL |
|---|---|---|
| F | `core/mcp/url_guard.py` — HTTPS-only, allowlist, IP-resolution check | `logs/mcp_url_rejections.jsonl` |
| F | `core/mcp/path_guard.py` — MinIO key + local-path traversal | `logs/mcp_path_rejections.jsonl` |
| G | `agents/shared/pi_guard.py` — imperative scan + DO_NOT_EXECUTE wrap | `logs/pi_quarantine.jsonl` |
| H | `GraphBuilder._execute` EXPLAIN precheck | `logs/cypher_rejections.jsonl` (`reason=explain_cardinality_exceeded`) |

All four log files are append-only JSONL. Empirical attempt-rates for
the paper are `wc -l` away.

## Tests (run from repo root)

```bash
for t in test_rrf_smoke test_cypher_validator test_analyzer_success \
         test_harness_contract test_mcp_guards test_pi_guard \
         test_explain_guard; do
  .venv/bin/python -m evaluation.$t
done
```

| Suite | Tests | Notes |
|---|---|---|
| `test_rrf_smoke` | 3 | Phase 0 RRF math |
| `test_cypher_validator` | 7 | Phase 1 schema validator |
| `test_analyzer_success` | 2 | Phase 1 analyzer-failure aggregator |
| `test_harness_contract` | 2 | Phase 1 Runner ABC |
| `test_mcp_guards` | 24 | Subtask F (SSRF + path-traversal) |
| `test_pi_guard` | 12 | Subtask G (PI scan + wrap) |
| `test_explain_guard` | 6 | Subtask H (mock + live Neo4j Amendment 5) |
| **Total** | **56** | All green |

## Honest gaps carried into Phase 5

1. **No answer-quality evaluation on MultiHop-RAG.** All retrieval-only.
   Per-query LLM synthesis across 100 multi-hop questions exceeds the
   30-min budget on Ollama Cloud. Phase 5 adds answer-quality on the
   regulations corpus where the query set will be hand-labeled.
2. **Reranker quality contribution unmeasured on CPU.** Subtask D's
   cross-encoder self-disabled after query 1 at 41.6s vs the 15s
   threshold (Amendment 4 design intent). Quantifying D's lift needs
   either GPU FP16 (sub-second rerank) or a smaller reranker
   (`bge-reranker-base`, ~380 MB).
3. **Article-level relevance, not fact-level.** MultiHop-RAG evaluation
   convention: a retrieved chunk is "relevant" iff its source URL is
   in `evidence_list`. Tighter fact-string match would be a paper-
   appendix audit row.
4. **No Cypher-generator fine-tuning.** Phase 1's validator + Phase 2's
   EXPLAIN guard catch malformed and expensive Cypher; they don't
   improve the generator. Text2Cypher accuracy on 7B-9B open models is
   the published ceiling.
5. **`compare_policies` Cypher still untyped.** Tightening
   `OPTIONAL MATCH (a)-[r]-(b)` to `[r:EQUIVALENT_TO|CONFLICTS_WITH]`
   would silently regress comparative queries to empty until reingest;
   docstring-only fix per the Phase 1 Refinement 3 decision.
6. **CORE-KG name normalization is MVP.** Real coreference resolution
   and alias chaining is the published CORE-KG contribution; not
   implemented.

## Repo layout after Phase 2

```
agents/
├── analyzer/        Phase 1 + Phase 2 enrichment + BGE-M3 hybrid index
├── document_access/ MinIO + metadata (Subtask F path-guarded)
├── graph_rag/       LLM→Cypher with Phase 1 validator + Phase 2 EXPLAIN guard
├── planner/         pipeline orchestration (post-Subtask-B analyzer-routed)
├── rag/             Qdrant search (named-vector aware)
├── shared/
│   ├── chunking.py            generic Chonkie wrapper
│   ├── document_chunker.py    (migrated from processing/)
│   ├── embeddings.py          BGE-M3 singleton
│   ├── fusion.py              RRF
│   ├── ingestion_pipeline.py  (migrated from ingestion/, now MinioHandler-backed)
│   ├── jsonl_logger.py
│   ├── pi_guard.py            Subtask G
│   ├── reranker.py            Subtask D
│   └── sac.py                 Subtask C
└── summarizer/      Phase 1 + 2 prompts, Subtask G wrap

core/
├── llm/             Ollama Cloud / LFM2 routing (Subtask A)
└── mcp/
    ├── handler.py
    ├── path_guard.py          Subtask F
    └── url_guard.py           Subtask F

evaluation/
├── data/multihop_rag/    MultiHop-RAG corpus (gitignored)
├── queries/              YAML query sets (incl. multihop_rag_100.yaml)
├── results/              JSONL traces + baseline_*.json summaries
├── runners/              MhragRunner (E.1/E.2/E.3 driver)
├── metrics/              recall/precision/MRR + analyzer-success
├── harness.py            Runner contract
└── test_*.py             56 unit tests

docs/
├── BENCHMARKS.md         retrieval-quality results
├── PHASE_LOG.md          chronological dev log
├── PHASE_2_COMPLETE.md   this file
└── SECURITY.md           F/G/H guards

legacy/                   pre-Phase-1 direct-ingestion path (not on import path)
```

Phase 2 is closed. Phase 5 (answer-quality + larger labeled query sets)
is the natural next milestone.
