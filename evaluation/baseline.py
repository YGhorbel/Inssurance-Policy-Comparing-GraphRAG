"""Phase 2 pre-change baseline capture.

Runs once before the BGE-M3 swap. Hits the live MCP /mcp endpoint, drives a
real ingestion through MinIO -> Qdrant -> Neo4j, then runs a fixed 10-query
trace and aggregates Phase 1 metrics. Output: evaluation/results/baseline_phase2_pre.json.

This closes the Amendment-7 gap from Phase 1 (where the live ingestion smoke
could not be executed because project deps were not installed).

Run from repo root with the project venv:
  .venv/bin/python evaluation/baseline.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_URL = os.environ.get("MCP_API_URL", "http://localhost:8001")
OUT_PATH = os.path.join("evaluation", "results", "baseline_phase2_pre.json")

BASELINE_QUERIES = [
    "What does Tunisian regulation require for motor-vehicle liability cover?",
    "List the obligations for health insurance providers in Tunisia.",
    "How does the Tunisian Insurance Code define third-party coverage?",
    "What are the exclusions under Tunisian auto insurance?",
    "Compare auto-insurance obligations between Tunisia and France.",
    "What requirements does EU directive impose on cross-border motor cover?",
    "Where do Tunisian and EU regulations diverge on coverage exclusions?",
    "What references does the Tunisian Insurance Code make to EU directives?",
    "Define the concept of comprehensive coverage in Tunisian law.",
    "What policy types apply specifically to Tunisia?",
]


def _post_mcp(method: str, params: dict | None = None) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": method,
    }
    if params is not None:
        payload["params"] = params
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL}/mcp",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path: str) -> Any:
    with urllib.request.urlopen(f"{API_URL}{path}", timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(path: str, payload: dict) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _qdrant_collection_stats() -> dict:
    """Direct Qdrant probe (avoids re-loading the embedder via api.server)."""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"))
        out = {}
        try:
            cols = client.get_collections().collections
        except Exception as exc:
            return {"error": str(exc)}
        for c in cols:
            try:
                info = client.get_collection(c.name)
                out[c.name] = {
                    "points_count": getattr(info, "points_count", None),
                    "vectors_count": getattr(info, "vectors_count", None),
                }
            except Exception as exc:
                out[c.name] = {"error": str(exc)}
        return out
    except Exception as exc:
        return {"error": str(exc)}


def _neo4j_stats() -> dict:
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            auth=("neo4j", os.environ.get("NEO4J_PASSWORD", "password")),
        )
        with driver.session() as session:
            nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            edge_hist = {
                row["t"]: row["c"]
                for row in session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY c DESC"
                )
            }
        driver.close()
        return {"nodes": nodes, "rels": rels, "edge_histogram": edge_hist}
    except Exception as exc:
        return {"error": str(exc)}


def _read_jsonl(path: str) -> list:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _phase1_metrics(log_dir: str = "logs") -> dict:
    cypher_rejections = _read_jsonl(os.path.join(log_dir, "cypher_rejections.jsonl"))
    rej_by_reason: dict[str, int] = {}
    for r in cypher_rejections:
        rej_by_reason[r.get("rejection_reason", "?")] = rej_by_reason.get(r.get("rejection_reason", "?"), 0) + 1

    analyzer_failures = _read_jsonl(os.path.join(log_dir, "analyzer_failures.jsonl"))
    analyzer_totals = _read_jsonl(os.path.join(log_dir, "analyzer_totals.jsonl"))
    total_calls = sum(int(t.get("total_calls", 0)) for t in analyzer_totals)
    extract_rate = None
    if total_calls > 0:
        extract_rate = max(0.0, min(1.0, (total_calls - len(analyzer_failures)) / total_calls))

    return {
        "cypher_rejections_total": len(cypher_rejections),
        "cypher_rejections_by_reason": rej_by_reason,
        "analyzer_total_calls": total_calls,
        "analyzer_failures": len(analyzer_failures),
        "analyzer_extraction_success_rate": extract_rate,
    }


def _ensure_corpus() -> list[str]:
    """If MinIO has fewer than 2 PDFs, generate synthetic regulatory PDFs.

    Returns a list of object names visible in MinIO after this step.
    """
    from minio import Minio
    client = Minio(
        os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        secure=False,
    )
    bucket = os.environ.get("MINIO_BUCKET", "regulations")
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    existing = [obj.object_name for obj in client.list_objects(bucket, recursive=True)]
    if len(existing) >= 2:
        return existing

    synthetic = [
        ("Tunisia/auto_liability_2024.pdf",
         "Tunisian Insurance Code Article 1. All motor vehicles registered in Tunisia must carry "
         "third-party liability cover meeting the minimum sums set by the Insurance Council. "
         "Article 2. Coverage must extend to bodily injury and property damage to third parties. "
         "Article 5. Exclusions include intentional damage and driving under the influence."),
        ("Tunisia/health_obligations_2024.pdf",
         "Tunisian Health Insurance Regulation Article 1. Insurance providers shall offer baseline "
         "cover for hospitalisation, surgical procedures, and emergency care. Article 3. Waiting "
         "periods may not exceed ninety days for any required service. Article 7. Premium "
         "adjustments require advance notice and Insurance Council approval."),
        ("France/code_assurances_excerpt.pdf",
         "French Code des Assurances Article L211-1. Tous les vehicules terrestres a moteur "
         "doivent etre couverts par une assurance de responsabilite civile. Article L211-4. "
         "L'assurance obligatoire garantit la responsabilite civile du conducteur. Article R211-7. "
         "Les exclusions doivent etre clairement enoncees dans le contrat."),
        ("EU/directive_motor_insurance.pdf",
         "EU Motor Insurance Directive 2009/103/EC Article 3. Each Member State shall ensure that "
         "civil liability for motor vehicles is covered by insurance. Article 9. Minimum amounts of "
         "cover are EUR 1 000 000 per victim for personal injury. Article 14. Cross-border claims "
         "shall be settled through national compensation bodies."),
    ]
    written = []
    for name, body in synthetic:
        pdf_bytes = _tiny_pdf(body)
        tmp = f"/tmp/baseline_{os.path.basename(name)}"
        with open(tmp, "wb") as fh:
            fh.write(pdf_bytes)
        client.fput_object(bucket, name, tmp, content_type="application/pdf")
        written.append(name)
    return existing + written


def _tiny_pdf(text: str) -> bytes:
    """Minimal single-page PDF embedding the given text. ASCII only.

    Not pretty, but PyPDFLoader can extract the text. Avoids reportlab.
    """
    text = (text or "").replace("(", "[").replace(")", "]")
    lines = []
    cursor = ""
    for word in text.split():
        if len(cursor) + len(word) + 1 > 80:
            lines.append(cursor.strip())
            cursor = word
        else:
            cursor = (cursor + " " + word).strip()
    if cursor:
        lines.append(cursor)
    stream_ops = ["BT", "/F1 11 Tf", "72 740 Td", "14 TL"]
    for i, line in enumerate(lines):
        if i == 0:
            stream_ops.append(f"({line}) Tj")
        else:
            stream_ops.append("T*")
            stream_ops.append(f"({line}) Tj")
    stream_ops.append("ET")
    stream = "\n".join(stream_ops)
    stream_bytes = stream.encode("ascii", errors="replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream_bytes)).encode() + b" >>\nstream\n" + stream_bytes + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode()
        out += body
        out += b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    return bytes(out)


def _query_trace() -> list[dict]:
    trace = []
    for q in BASELINE_QUERIES:
        t0 = time.perf_counter_ns()
        try:
            res = _post_json("/graph/retrieve", {"query": q, "top_k": 5})
            elapsed_ms = (time.perf_counter_ns() - t0) // 1_000_000
            payloads = ((res or {}).get("result") or {}).get("vector_hits") or []
            chunk_ids = [(p or {}).get("chunk_id") for p in payloads]
            synthesis = ((res or {}).get("result") or {}).get("synthesis") or ""
            trace.append({
                "query": q,
                "latency_ms": elapsed_ms,
                "retrieved_chunk_ids": chunk_ids,
                "synthesis_excerpt": (synthesis or "")[:300],
                "ok": True,
            })
        except Exception as exc:
            trace.append({"query": q, "error": str(exc), "ok": False})
    return trace


def main() -> int:
    health = _get("/health")
    print(f"/health: {health.get('status')}, {len(health.get('tools', []))} tools registered")

    print("ensuring corpus in MinIO...")
    docs = _ensure_corpus()
    print(f"  MinIO objects: {len(docs)}")

    print("/mcp sync_metadata...")
    sync = _post_mcp("sync_metadata")
    sync_count = len(sync.get("result", []) if isinstance(sync.get("result"), list) else [])
    print(f"  metadata synced: {sync_count} entries")

    print("/mcp ingest_documents (this takes a while on CPU LFM2)...")
    t0 = time.perf_counter_ns()
    ingest = _post_mcp("ingest_documents")
    ingest_ms = (time.perf_counter_ns() - t0) // 1_000_000
    print(f"  ingest complete in {ingest_ms / 1000:.1f}s; result: {str(ingest.get('result'))[:200]}")

    print("/graph/ingest (project Qdrant -> Neo4j)...")
    t0 = time.perf_counter_ns()
    graph = _post_json("/graph/ingest", {})
    graph_ms = (time.perf_counter_ns() - t0) // 1_000_000
    print(f"  graph projection complete in {graph_ms / 1000:.1f}s; result: {str(graph.get('result'))[:200]}")

    print(f"running 10-query baseline trace...")
    trace = _query_trace()
    ok_count = sum(1 for q in trace if q.get("ok"))
    print(f"  {ok_count}/{len(trace)} queries returned without error")

    baseline = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "phase2_pre",
        "synthetic_corpus_used": any("auto_liability_2024" in d for d in docs),
        "minio_objects": docs,
        "mcp_tools_registered": len(health.get("tools", [])),
        "ingest_ms": ingest_ms,
        "graph_projection_ms": graph_ms,
        "qdrant": _qdrant_collection_stats(),
        "neo4j": _neo4j_stats(),
        "phase1_metrics": _phase1_metrics(),
        "query_trace": trace,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, ensure_ascii=False, indent=2)
    print(f"baseline written to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
