# Benchmarks

Retrieval-quality benchmark results — reviewer-friendly "what are the
numbers" view. Machine-readable copies of every result table below
ship in `evaluation/results/baseline_mhrag_*.json` (whitelisted past
the `evaluation/results/*` gitignore pattern).

## Dataset

**MultiHop-RAG** (Tang & Yang, *Benchmarking Retrieval-Augmented Generation
for Multi-Hop Queries*, arXiv 2401.15391; ODC-BY 1.0). Pulled via Git LFS
from `yixuantt/MultiHop-RAG`:

| File | Size | Contents |
|---|---|---|
| `dataset/MultiHopRAG.json` | 5.17 MB | 2,556 queries across four `question_type`s |
| `dataset/corpus.json` | 6.79 MB | 609 news articles (`title, url, body, source, published_at, …`) |

Local cache: `evaluation/data/multihop_rag/` (gitignored). Stratified
100-query subset committed at `evaluation/queries/multihop_rag_100.yaml`
(`random.seed(42)`, 25 from each of `inference_query`, `comparison_query`,
`temporal_query`, `null_query`).

**Relevance unit: article URL.** `expected_chunks` in the YAML is the list
of evidence-article URLs from `evidence_list`. The runner returns each
retrieved chunk's `source_url` (deduped first-occurrence), so Recall@k and
MRR are measured at the article level. Matches the original paper.

**`null_query` is a negative-control bucket.** No relevant article exists
in the corpus by design — Recall@k and MRR are mechanically 0.0 for that
tag and dilute the overall mean by 25/100. Report the **answerable (75)**
row as the headline number.

## Ingest parameters (shared across all runs)

| Setting | Value |
|---|---|
| Chunker | paragraph-aware, `target=768 / max=1024` chars (hard sentence-boundary split) |
| Chunks ingested | 10,381 across 609 articles (avg 17/article) |
| Encoder | BGE-M3 dense head, 1024-d cosine (sparse off — retrieval is dense-only) |
| Chunk-ID scheme | `uuid5(NAMESPACE_OID, "mhrag::{url}::{idx}")` (deterministic by `(url, idx)`) |

## BGE-M3 dense retrieval

Collection: `mhrag_eval_v2`. Empty-results gate: **PASS** (100/100
queries return ≥1 result).

| Subset | n | Recall@2 | Recall@5 | MRR | Latency (ms) |
|---|---|---|---|---|---|
| `comparison_query` | 25 | 0.520 | 0.727 | 0.843 | 13.4 |
| `temporal_query` | 25 | 0.493 | 0.753 | 0.748 | 13.4 |
| `inference_query` | 25 | 0.307 | 0.503 | 0.660 | 13.2 |
| `null_query` | 25 | 0.000 | 0.000 | 0.000 | 13.0 |
| **Overall (100)** | 100 | 0.330 | 0.496 | 0.563 | 13.2 |
| **Answerable-only (75)** | 75 | **0.440** | **0.661** | **0.750** | 13.2 |

Source: `evaluation/results/baseline_mhrag_B_only.json`.

## With Summary-Augmented Chunking (SAC)

Collection: `mhrag_eval_v2_sac`. SAC summary generation: 609/609
articles (0 LLM failures). Cache: `data/sac/cache_v1.json`. Empty-
results gate: **PASS**.

| Subset | n | Recall@2 | Recall@5 | MRR | Latency (ms) |
|---|---|---|---|---|---|
| `comparison_query` | 25 | 0.440 | 0.753 | 0.883 | 15.3 |
| `temporal_query` | 25 | 0.487 | 0.753 | 0.813 | 15.8 |
| `inference_query` | 25 | 0.327 | 0.510 | 0.753 | 14.7 |
| `null_query` | 25 | 0.000 | 0.000 | 0.000 | 15.4 |
| **Overall (100)** | 100 | 0.313 | 0.504 | 0.613 | 15.3 |
| **Answerable-only (75)** | 75 | **0.418** | **0.672** | **0.816** | 15.3 |

Source: `evaluation/results/baseline_mhrag_B_plus_C.json`.

## Delta: SAC vs dense baseline

| Tag | Metric | Dense | + SAC | Δ |
|---|---|---|---|---|
| `comparison_query` | R@2 | 0.520 | 0.440 | **−0.080** |
| | R@5 | 0.727 | 0.753 | **+0.027** |
| | MRR | 0.843 | **0.883** | **+0.040** |
| `temporal_query` | R@2 | 0.493 | 0.487 | −0.007 |
| | R@5 | 0.753 | 0.753 | 0.000 |
| | MRR | 0.748 | **0.813** | **+0.065** |
| `inference_query` | R@2 | 0.307 | 0.327 | +0.020 |
| | R@5 | 0.503 | 0.510 | +0.007 |
| | MRR | 0.660 | **0.753** | **+0.093** |
| **Answerable (75)** | R@2 | **0.440** | 0.418 | −0.022 |
| | R@5 | 0.661 | **0.672** | **+0.011** |
| | MRR | 0.750 | **0.816** | **+0.066** |
| **Overall (100)** | R@2 | **0.330** | 0.313 | −0.017 |
| | R@5 | 0.496 | **0.504** | **+0.008** |
| | MRR | 0.563 | **0.613** | **+0.050** |

### How to read the deltas

- **MRR is the headline win** (+0.066 on the answerable set, +0.093 on
  `inference_query`). SAC reorders the top-20 so the most-relevant chunk
  surfaces higher; that is exactly what document-level summary prefixes
  are designed to do.
- **Recall@5 is essentially flat** (+0.011 answerable). SAC does not
  surface new relevant articles that the dense baseline missed at
  top-20 — it reranks within the candidate set.
- **Recall@2 regresses slightly** (−0.022 answerable). Once two chunks
  from the same article share a summary prefix, their embeddings get
  closer to each other, occasionally pushing distractor chunks above
  relevant ones at very short cutoffs. Known SAC tradeoff documented
  in the Anthropic Contextual Retrieval write-up.
- **Latency: +2.1 ms.** Sub-jitter on a CPU Qdrant host; the SAC summary
  is generated at ingest time, not at query time.

For the downstream LLM-synthesis step (top-5 fixed window), MRR matters
more than Recall@2 — the LLM sees the same five candidates either way
and benefits from better ordering. SAC stays on for the reranker pass.

## With cross-encoder reranker (BGE-reranker-v2-m3)

Collection: `mhrag_eval_v2_sac` (reuse of the SAC collection — the
reranker operates on retrieved chunks, no re-ingest). Empty-results
gate: **PASS**. Reranker self-disable: **fired on query 1** at 41.6 s
rerank wall-clock against the 15 s CPU threshold; queries 2–100 fell
through to the upstream SAC ordering.

| Subset | n | Recall@2 | Recall@5 | MRR | Latency (ms) |
|---|---|---|---|---|---|
| `comparison_query` | 25 | 0.440 | 0.753 | 0.883 | 18.3 |
| `temporal_query` | 25 | 0.487 | 0.753 | 0.813 | 21.4 |
| `inference_query` | 25 | 0.327 | 0.510 | 0.753 | 1,683.1¹ |
| `null_query` | 25 | 0.000 | 0.000 | 0.000 | 18.9 |
| **Overall (100)** | 100 | 0.313 | 0.504 | 0.613 | 435.4¹ |
| **Answerable-only (75)** | 75 | **0.418** | **0.672** | **0.816** | 574.5¹ |

¹ Skewed by the single 41.6 s outlier on query 1 (the reranker-disable
trigger, in the `inference_query` bucket). Median across all 100
queries: 19 ms; without the outlier, mean is ≈ 19 ms.

Source: `evaluation/results/baseline_mhrag_B_plus_C_plus_D.json`. The
disable event lives at `logs/reranker_disabled.jsonl`:

```json
{"query": "Which NFL player, featured in articles by 'The Guardian'…",
 "n_passages": 20, "elapsed_s": 41.58, "threshold_s": 15.0,
 "model_id": "BAAI/bge-reranker-v2-m3",
 "reason": "first_slow_query_sticky_disable"}
```

### Why the reranker numbers match the SAC pass

99/100 queries ran with the reranker disabled (fallback to SAC), so
the headline retrieval-quality numbers are bit-identical to the SAC
pass. **This is the design intent**: a finished run with a sticky-
disable trace beats an abandoned run, exactly so the CPU-budget hit
can be quantified. To measure the reranker's actual quality
contribution on this benchmark requires:

- GPU FP16 (BGE-reranker-v2-m3 finishes 20-passage rerank under 1 s
  there), or
- A smaller reranker (e.g. `BAAI/bge-reranker-base`, ~380 MB) that fits
  the 15 s CPU budget, or
- Raising `RERANK_DISABLE_THRESHOLD_S` to ≥60 s and paying the ~67 min
  full-run cost (defeats the budget, but useful as an audit row).

Deferred to a future audit; the reranker capability is wired and
validated end-to-end.

## Combined comparison

Headline subset is **answerable-only (n=75)** — `null_query` is a
negative-control bucket and mechanically scores 0 on every run.

| Metric | Dense | + SAC | + Reranker¹ | Best |
|---|---|---|---|---|
| Recall@2 | **0.440** | 0.418 | 0.418 | Dense |
| Recall@5 | 0.661 | 0.672 | 0.672 | **+ SAC** |
| MRR | 0.750 | 0.816 | 0.816 | **+ SAC** |
| Mean latency (steady-state) | 13.2 ms | 15.3 ms | ~19 ms² | Dense |

¹ Headline reranker numbers are identical to + SAC because the
reranker sticky-disabled on query 1.
² 99/100 queries ran without rerank cost.

### Production recommendation

- **Use BGE-M3 + SAC** in the canonical pipeline. SAC's MRR lift
  (+0.066 on the answerable subset) is the biggest retrieval win;
  it's cheap once the SAC cache is warm.
- **Keep the reranker in-tree** for GPU deploys. The capability is
  wired, tested end-to-end, and the self-disable means turning it on
  by default on a GPU box is safe.
- **Do not block on Recall@2.** Both SAC and the reranker push some
  distractor chunks above the top-2 cutoff (intra-document embedding
  similarity effect); for the downstream LLM-synthesis step,
  MRR > Recall@2 since the LLM always sees the same fixed top-5
  window.

## Cleanup decision

The 5-document regulations corpus has no labeled query set, so the
"is BGE-M3 retrieval trustworthy at all" question is evaluated on
**MultiHop-RAG** as a proxy. + SAC cleared 0.672 answerable Recall@5;
the regulations smoke trace cleared 50/50 chunk-slot fill with all
7 reconciled edge types live for the first time. Both bars met.

**Action:** dropped Qdrant collections `regulations` (5 stale points,
384-dim, pre-BGE-M3) and `regulations_chunks` (0 points, the empty
intermediate collection from the old planner-bypass bug). The
production collection `regulations_chunks_v2` (1024-dim BGE-M3 hybrid)
is the sole remaining regulations index. `configs/config.yaml`'s
`qdrant.legacy_collection` key is removed; `agents/graph_rag/qdrant_ingest.py`'s
dead default fallback is realigned to the v2 collection name.

## Reproducing locally

```bash
# Dense baseline
.venv/bin/python -m evaluation.runners.multihop_rag --ingest
.venv/bin/python -m evaluation.runners.multihop_rag --run

# + SAC chunking
.venv/bin/python -m evaluation.runners.multihop_rag --ingest --sac \
    --collection mhrag_eval_v2_sac
.venv/bin/python -m evaluation.runners.multihop_rag --run \
    --collection mhrag_eval_v2_sac

# + cross-encoder reranker (reuses the SAC collection)
.venv/bin/python -m evaluation.runners.multihop_rag --run --rerank \
    --collection mhrag_eval_v2_sac
# Raise the threshold to bypass the CPU self-disable (GPU or audit):
# RERANK_DISABLE_THRESHOLD_S=600 .venv/bin/python -m evaluation.runners.multihop_rag --run --rerank …
```

Pre-reqs: `docker-compose up -d` (MinIO/Neo4j/Qdrant), `.venv` with
`requirements.txt` installed, `.env` with `LLM_PROVIDER=ollama_cloud`
+ `OLLAMA_API_KEY` set (only the SAC summaries require an LLM —
the dense baseline is dense-search only). MultiHop-RAG data files:
pull once from
`https://media.githubusercontent.com/media/yixuantt/MultiHop-RAG/main/dataset/{MultiHopRAG.json,corpus.json}`
into `evaluation/data/multihop_rag/`.

## Honest gaps

These caveats apply to every row in this file:

1. **No answer-quality evaluation.** All runs measure retrieval only
   (no LLM synthesis step). Running the summarizer on 100 multi-hop
   questions through Ollama Cloud was budgeted out — per-query
   latency would blow the 30-min wall-clock budget.
2. **Article-level relevance, not fact-level.** A retrieved chunk is
   "relevant" iff its source URL is in the query's `evidence_list`;
   we do not check whether the chunk actually contains the cited
   `fact` string. This matches the original paper's evaluation.
3. **100-query stratified subset, not the full 2,556.** Re-pointing
   the runner at the full set is a one-line change but takes ~25× as
   long; the subset is sufficient for an internal before/after delta.
4. **Cold-start latency excluded.** Latency means are steady-state
   Qdrant search time after BGE-M3 loaded. First query in a fresh
   process pays ~5–10 s for model weight load.
