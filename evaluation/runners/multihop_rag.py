"""MultiHop-RAG regression runner (Phase 2 Subtask E.1+).

External corpus: yixuantt/MultiHop-RAG (news articles + multi-hop QA pairs,
Git LFS). We ingest the corpus ONCE into a dedicated Qdrant collection
(``mhrag_eval_v2``) so re-runs of E.1 / E.2 / E.3 only re-execute the
retrieval step, not the embed-and-upsert step.

Relevance is article-level: ``expected_chunks`` in the YAML query set is the
list of evidence-article URLs; ``retrieved_chunks`` returned by ``run_one``
is the list of source URLs (deduped by first-occurrence) of the top-k
Qdrant points. That keeps the QueryResult contract intact while matching
how the MultiHop-RAG paper evaluates retrieval.

The B-only run does NOT invoke the LLM (per the Phase 2 plan — LLM-per-query
across 100 multi-hop questions would blow the 30-min budget given Ollama
Cloud's per-call latency). ``generated_answer`` is therefore set to ``""``.

Amendment 2 gate (Phase 2 approval): before computing any Recall@5 number,
confirm all 100 queries return ≥1 result. If any return zero, surface the
empty queries and STOP.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from typing import List, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from agents.shared.embeddings import get_embedder
from evaluation.harness import Query, QueryResult, Runner, load_query_set
from evaluation.metrics.ranking import recall_at_k, reciprocal_rank


MHRAG_COLLECTION = "mhrag_eval_v2"
CORPUS_PATH = os.path.join("evaluation", "data", "multihop_rag", "corpus.json")
QUERIES_YAML = os.path.join("evaluation", "queries", "multihop_rag_100.yaml")
CHUNK_TARGET_CHARS = 768
CHUNK_MAX_CHARS = 1024


def _chunk_id_for(url: str, idx: int) -> str:
    base = f"mhrag::{url}::{idx}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, base))


def _hard_split(text: str, max_chars: int) -> List[str]:
    """Split text into <= max_chars pieces, preferring sentence boundaries."""
    out: List[str] = []
    remaining = text
    while len(remaining) > max_chars:
        cut = max_chars
        for sep in (". ", "! ", "? ", "\n"):
            idx = remaining.rfind(sep, 0, max_chars)
            if idx > max_chars // 2:
                cut = idx + len(sep)
                break
        out.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        out.append(remaining)
    return out


def _chunk_article_body(
    body: str,
    target_chars: int = CHUNK_TARGET_CHARS,
    max_chars: int = CHUNK_MAX_CHARS,
) -> List[str]:
    """Paragraph-aware chunker with a hard upper bound.

    Long paragraphs get hard-split at sentence boundaries so no chunk
    exceeds ``max_chars`` — BGE-M3's sparse head scales linearly with
    token count and chokes on 5000-char chunks (news articles often
    have a single multi-thousand-char paragraph).
    """
    if not body:
        return []
    paragraphs: List[str] = []
    for p in body.split("\n\n"):
        p = p.strip()
        if not p:
            continue
        if len(p) > max_chars:
            paragraphs.extend(_hard_split(p, max_chars))
        else:
            paragraphs.append(p)
    chunks: List[str] = []
    buf = ""
    for para in paragraphs:
        if not buf:
            buf = para
        elif len(buf) + 2 + len(para) <= target_chars:
            buf = buf + "\n\n" + para
        else:
            chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    return chunks


def _ensure_collection(client: QdrantClient, collection: str, dim: int, sparse_enabled: bool) -> None:
    try:
        _ = client.get_collection(collection)
        return
    except Exception:
        pass
    vectors_cfg = {"dense": qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE)}
    sparse_cfg = {"sparse": qmodels.SparseVectorParams()} if sparse_enabled else None
    try:
        client.create_collection(
            collection_name=collection,
            vectors_config=vectors_cfg,
            sparse_vectors_config=sparse_cfg,
        )
    except Exception:
        client.recreate_collection(
            collection_name=collection,
            vectors_config=vectors_cfg,
            sparse_vectors_config=sparse_cfg,
        )


def ingest_corpus(
    corpus_path: str = CORPUS_PATH,
    collection: str = MHRAG_COLLECTION,
    qdrant_url: Optional[str] = None,
    batch: int = 32,
    with_sparse: bool = False,
) -> dict:
    """Embed and upsert the MultiHop-RAG news corpus into Qdrant.

    ``with_sparse=False`` (default) skips BGE-M3's sparse / lexical-weights
    head: the retrieval path here is dense-only (``MhragRunner._dense_search``
    queries ``using="dense"``), so computing sparse vectors at ingest time
    is pure compute waste — roughly 2× slower for zero retrieval value. The
    canonical regulations stack keeps sparse on because of the planned
    hybrid-fusion roadmap; for the MultiHop-RAG eval corpus that roadmap
    does not apply.
    """
    if qdrant_url is None:
        qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    with open(corpus_path, "r", encoding="utf-8") as fh:
        articles = json.load(fh)
    embedder = get_embedder()
    original_sparse = embedder.sparse_enabled
    embedder.sparse_enabled = bool(with_sparse) and original_sparse
    client = QdrantClient(url=qdrant_url)
    _ensure_collection(client, collection, dim=embedder.dim, sparse_enabled=embedder.sparse_enabled)

    pending_texts: List[str] = []
    pending_meta: List[dict] = []
    total_points = 0
    skipped_articles = 0

    def _flush() -> None:
        nonlocal total_points
        if not pending_texts:
            return
        hybrid_batch = embedder.encode_hybrid(pending_texts)
        points: List[qmodels.PointStruct] = []
        for hybrid, meta in zip(hybrid_batch, pending_meta):
            vector_struct: dict = {"dense": hybrid["dense"]}
            if "sparse" in hybrid:
                vector_struct["sparse"] = qmodels.SparseVector(
                    indices=hybrid["sparse"]["indices"],
                    values=hybrid["sparse"]["values"],
                )
            points.append(qmodels.PointStruct(id=meta["chunk_id"], vector=vector_struct, payload=meta))
        client.upsert(collection_name=collection, points=points)
        total_points += len(points)
        pending_texts.clear()
        pending_meta.clear()

    for art in articles:
        url = art.get("url") or ""
        if not url:
            skipped_articles += 1
            continue
        body = art.get("body") or ""
        chunks = _chunk_article_body(body)
        if not chunks:
            skipped_articles += 1
            continue
        for idx, text in enumerate(chunks):
            pending_texts.append(text)
            pending_meta.append({
                "chunk_id": _chunk_id_for(url, idx),
                "source_url": url,
                "title": art.get("title") or "",
                "source": art.get("source") or "",
                "published_at": art.get("published_at") or "",
                "category": art.get("category") or "",
                "chunk_idx": idx,
                "text": text,
            })
            if len(pending_texts) >= batch:
                _flush()
    _flush()
    embedder.sparse_enabled = original_sparse

    info = client.get_collection(collection)
    return {
        "collection": collection,
        "articles_seen": len(articles),
        "articles_skipped": skipped_articles,
        "points_upserted": total_points,
        "qdrant_points_total": getattr(info, "points_count", None),
        "with_sparse": bool(with_sparse) and original_sparse,
    }


class MhragRunner(Runner):
    mode = "mhrag_b_only"

    def __init__(
        self,
        results_dir: str = "evaluation/results",
        collection: str = MHRAG_COLLECTION,
        qdrant_url: Optional[str] = None,
        top_k_qdrant: int = 20,
        top_k_eval: int = 5,
    ) -> None:
        super().__init__(results_dir=results_dir)
        if qdrant_url is None:
            qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
        self.collection = collection
        self.embedder = get_embedder()
        self.client = QdrantClient(url=qdrant_url)
        self.top_k_qdrant = top_k_qdrant
        self.top_k_eval = top_k_eval

    def _dense_search(self, vector: List[float]):
        try:
            return self.client.query_points(
                collection_name=self.collection,
                query=vector,
                using="dense",
                limit=self.top_k_qdrant,
                with_payload=True,
            ).points
        except Exception:
            return self.client.search(
                collection_name=self.collection,
                query_vector=("dense", vector),
                limit=self.top_k_qdrant,
            )

    def run_one(self, query: Query) -> QueryResult:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        vec = self.embedder.encode(query.query)
        t0 = time.perf_counter()
        hits = self._dense_search(vec)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        urls_in_order: List[str] = []
        scores_in_order: List[float] = []
        seen = set()
        for h in hits:
            payload = getattr(h, "payload", None) or {}
            url = payload.get("source_url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            urls_in_order.append(url)
            scores_in_order.append(float(getattr(h, "score", 0.0)))
            if len(urls_in_order) >= self.top_k_eval:
                break

        return QueryResult(
            query=query.query,
            mode=self.mode,
            retrieved_chunks=urls_in_order,
            ranks=list(range(1, len(urls_in_order) + 1)),
            scores=scores_in_order,
            generated_answer="",
            latency_ms=latency_ms,
            timestamp=ts,
        )


def verify_empty_gate(results_path: str) -> List[dict]:
    """Amendment 2 gate. Returns the list of zero-result queries; empty list means PASS."""
    empties: List[dict] = []
    with open(results_path, "r", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if not rec.get("retrieved_chunks"):
                empties.append({"query": rec.get("query"), "mode": rec.get("mode")})
    return empties


def compute_metrics(results_path: str, query_set_path: str) -> dict:
    queries = load_query_set(query_set_path)
    expected_by_query = {q.query: q.expected_chunks for q in queries}
    tags_by_query = {q.query: q.tags for q in queries}

    per_tag = defaultdict(list)
    r2_all, r5_all, mrr_all, lat_all = [], [], [], []

    with open(results_path, "r", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            q = rec.get("query") or ""
            retrieved = rec.get("retrieved_chunks") or []
            expected = expected_by_query.get(q) or []
            r2 = recall_at_k(retrieved, expected, 2)
            r5 = recall_at_k(retrieved, expected, 5)
            rr = reciprocal_rank(retrieved, expected)
            lat = rec.get("latency_ms") or 0
            r2_all.append(r2)
            r5_all.append(r5)
            mrr_all.append(rr)
            lat_all.append(lat)
            for tag in tags_by_query.get(q, []):
                per_tag[tag].append((r2, r5, rr, lat))

    def _avg(xs):
        return (sum(xs) / len(xs)) if xs else 0.0

    summary = {
        "overall": {
            "n_queries": len(r2_all),
            "recall_at_2": _avg(r2_all),
            "recall_at_5": _avg(r5_all),
            "mrr": _avg(mrr_all),
            "latency_ms_mean": _avg(lat_all),
        },
        "per_tag": {},
    }
    for tag, rows in sorted(per_tag.items()):
        r2s, r5s, rrs, lats = zip(*rows)
        summary["per_tag"][tag] = {
            "n_queries": len(rows),
            "recall_at_2": _avg(r2s),
            "recall_at_5": _avg(r5s),
            "mrr": _avg(rrs),
            "latency_ms_mean": _avg(lats),
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="MultiHop-RAG E.1 (B-only) runner")
    parser.add_argument("--ingest", action="store_true", help="Ingest the corpus into Qdrant before running")
    parser.add_argument("--run", action="store_true", help="Execute the retrieval pass over the 100-query set")
    parser.add_argument("--metrics", type=str, default="", help="Path to a JSONL results file to score (alt. to --run)")
    parser.add_argument("--queries", type=str, default=QUERIES_YAML)
    parser.add_argument("--corpus", type=str, default=CORPUS_PATH)
    parser.add_argument("--collection", type=str, default=MHRAG_COLLECTION)
    parser.add_argument("--with-sparse", action="store_true", help="Also compute BGE-M3 sparse vectors (default off — retrieval is dense-only)")
    args = parser.parse_args()

    if not (args.ingest or args.run or args.metrics):
        parser.print_help()
        return 2

    if args.ingest:
        print(f"[ingest] corpus={args.corpus} collection={args.collection} with_sparse={args.with_sparse}")
        result = ingest_corpus(corpus_path=args.corpus, collection=args.collection, with_sparse=args.with_sparse)
        print(json.dumps(result, indent=2))

    results_path = args.metrics or ""
    if args.run:
        runner = MhragRunner(collection=args.collection)
        print(f"[run] queries={args.queries} mode={runner.mode}")
        results_path = runner.run(args.queries)
        print(f"[run] wrote {results_path}")

    if results_path:
        empties = verify_empty_gate(results_path)
        if empties:
            print(f"[gate] FAIL — {len(empties)} queries returned zero results:")
            for e in empties[:20]:
                print(f"  - {e['query'][:120]}")
            return 3
        print(f"[gate] PASS — every query returned ≥1 result")
        summary = compute_metrics(results_path, args.queries)
        summary_path = results_path.replace(".jsonl", "_summary.json")
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"[metrics] wrote {summary_path}")
        print(json.dumps(summary["overall"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
