from typing import Optional

from agents.graph_rag.db import Neo4jHandler
from agents.graph_rag.prompts import GraphPrompts
from agents.graph_rag.validator import Rejection, validate
from agents.shared.jsonl_logger import log_event
from core.llm.client import get_llm_client


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
        success = 0
        for stmt in statements:
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
        print(f"    > Executed {success}/{len(statements)} statements.")
        return success > 0
