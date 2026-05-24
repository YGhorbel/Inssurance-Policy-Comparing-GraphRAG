import os
from typing import Optional

from agents.graph_rag.db import Neo4jHandler
from agents.graph_rag.prompts import GraphPrompts
from agents.graph_rag.validator import Rejection, validate
from agents.shared.jsonl_logger import log_event
from core.llm.client import get_llm_client

# Subtask H + Amendment 5: any LLM-generated MERGE/MATCH whose EXPLAIN plan
# estimates more rows than this gets rejected before execution. Catches the
# class of unbounded `MATCH (n)-[r]-(m)` clauses that slipped past the
# structure-only validator. Override at runtime via the env var for audit
# rows that want to characterise extreme plans.
EXPLAIN_CARDINALITY_THRESHOLD = int(os.getenv("EXPLAIN_CARDINALITY_THRESHOLD", "100000"))


class GraphBuilder:
    def __init__(self, db_handler: Neo4jHandler):
        self.llm = get_llm_client()
        self.db = db_handler

    def process_text_chunk(self, text: str, metadata: Optional[dict] = None) -> bool:
        meta = metadata or {}
        chunk_id = meta.get("chunk_id") or None
        source_document = (
            meta.get("filename")
            or (meta.get("source") or {}).get("document")
            or None
        )

        prompt = GraphPrompts.get_extraction_prompt(text, meta)
        response = self.llm.generate(prompt)
        if not response:
            return False

        accepted, rejections = validate(
            response,
            chunk_id=chunk_id,
            source_document=source_document,
        )

        if not accepted:
            print(f"    > No valid Cypher extracted ({len(rejections)} rejected).")
            return False

        return self._execute(accepted, chunk_id, source_document)

    def _execute(self, statements, chunk_id, source_document) -> bool:
        """Execute each accepted Cypher statement, guarded by an EXPLAIN
        cardinality precheck (Subtask H + Amendment 5).

        A statement whose EXPLAIN plan estimates more rows than
        EXPLAIN_CARDINALITY_THRESHOLD is rejected before execution and
        appended to logs/cypher_rejections.jsonl with
        reason="explain_cardinality_exceeded". Statements where EXPLAIN
        returns None (older Neo4j, transient driver issue) fail-open —
        we execute and let the runtime catch trouble downstream.
        """
        success = 0
        skipped_cardinality = 0
        for stmt in statements:
            estimated = self.db.explain_estimated_rows(stmt)
            if estimated is not None and estimated > EXPLAIN_CARDINALITY_THRESHOLD:
                skipped_cardinality += 1
                log_event("cypher_rejections.jsonl", {
                    "chunk_id": chunk_id,
                    "source_document": source_document,
                    "statement": stmt[:500],
                    "rejection_reason": "explain_cardinality_exceeded",
                    "estimated_rows": estimated,
                    "threshold": EXPLAIN_CARDINALITY_THRESHOLD,
                })
                print(f"    > EXPLAIN guard blocked: {estimated} > {EXPLAIN_CARDINALITY_THRESHOLD} rows")
                continue
            try:
                self.db.execute_query(stmt)
                success += 1
            except Exception as e:
                log_event("cypher_rejections.jsonl", {
                    "chunk_id": chunk_id,
                    "source_document": source_document,
                    "statement": stmt[:500],
                    "rejection_reason": "neo4j_execution_failed",
                    "rejected_token": str(e)[:200],
                })
                print(f"    > Query Error: {str(e)[:80]}")
        print(f"    > Executed {success}/{len(statements)} statements"
              + (f" (EXPLAIN-blocked {skipped_cardinality})" if skipped_cardinality else "")
              + ".")
        return success > 0
