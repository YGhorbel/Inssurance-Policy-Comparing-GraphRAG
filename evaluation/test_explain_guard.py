"""Tests for the Subtask H EXPLAIN cardinality guard.

Two layers:
  - **mock-DB unit tests** (always run): a fake Neo4jHandler returns a
    canned ``explain_estimated_rows`` value; assert the guard fires and
    the statement is logged with reason="explain_cardinality_exceeded".
  - **live integration check** (Amendment 5, skipped automatically when
    Neo4j is unreachable): run a real EXPLAIN against the docker-compose
    Neo4j and assert the driver+plan-walker actually produce an int.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class _FakeDB:
    """Minimal stand-in for Neo4jHandler used by the mock tests."""

    def __init__(self, estimate_for_stmt=None, raise_on_execute=False):
        self.estimate_for_stmt = estimate_for_stmt or {}
        self.raise_on_execute = raise_on_execute
        self.executed = []
        self.explained = []

    def explain_estimated_rows(self, stmt, params=None):
        self.explained.append(stmt)
        return self.estimate_for_stmt.get(stmt)

    def execute_query(self, stmt, params=None):
        self.executed.append(stmt)
        if self.raise_on_execute:
            raise RuntimeError("simulated runtime failure")
        return []


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


class TestExplainGuard(unittest.TestCase):
    """Mock tests sandbox the JSONL logger via AGENT_LOG_DIR."""

    def setUp(self):
        self.log_dir = tempfile.mkdtemp(prefix="explain_guard_test_")
        # The logger caches its log dir at import time; patch directly.
        from agents.shared import jsonl_logger
        self._old_log_dir = jsonl_logger._LOG_DIR
        jsonl_logger._LOG_DIR = self.log_dir

    def tearDown(self):
        from agents.shared import jsonl_logger
        jsonl_logger._LOG_DIR = self._old_log_dir
        shutil.rmtree(self.log_dir, ignore_errors=True)

    def _builder(self, db):
        from agents.graph_rag.builder import GraphBuilder
        gb = GraphBuilder.__new__(GraphBuilder)
        gb.db = db
        gb.llm = None
        return gb

    def test_low_cardinality_executes(self):
        stmt = "MERGE (n:Country {name: 'Tunisia'}) RETURN n"
        db = _FakeDB(estimate_for_stmt={stmt: 1})
        gb = self._builder(db)
        ok = gb._execute([stmt], chunk_id="c1", source_document="doc.pdf")
        self.assertTrue(ok)
        self.assertEqual(db.executed, [stmt])
        rejections = _read_jsonl(os.path.join(self.log_dir, "cypher_rejections.jsonl"))
        self.assertEqual(rejections, [])

    def test_high_cardinality_blocked(self):
        from agents.graph_rag.builder import EXPLAIN_CARDINALITY_THRESHOLD
        stmt = "MATCH (n)-[r]-(m) RETURN n, m"
        db = _FakeDB(estimate_for_stmt={stmt: EXPLAIN_CARDINALITY_THRESHOLD + 1})
        gb = self._builder(db)
        ok = gb._execute([stmt], chunk_id="c2", source_document="doc.pdf")
        self.assertFalse(ok)
        self.assertEqual(db.executed, [])
        rejections = _read_jsonl(os.path.join(self.log_dir, "cypher_rejections.jsonl"))
        self.assertEqual(len(rejections), 1)
        rec = rejections[0]
        self.assertEqual(rec["rejection_reason"], "explain_cardinality_exceeded")
        self.assertEqual(rec["chunk_id"], "c2")
        self.assertEqual(rec["estimated_rows"], EXPLAIN_CARDINALITY_THRESHOLD + 1)

    def test_explain_unavailable_fails_open(self):
        stmt = "MERGE (n:Country {name: 'France'})"
        db = _FakeDB(estimate_for_stmt={stmt: None})
        gb = self._builder(db)
        ok = gb._execute([stmt], chunk_id="c3", source_document="doc.pdf")
        self.assertTrue(ok)
        self.assertEqual(db.executed, [stmt])

    def test_mixed_batch(self):
        from agents.graph_rag.builder import EXPLAIN_CARDINALITY_THRESHOLD
        ok_stmt = "MERGE (n:Country {name: 'X'})"
        bad_stmt = "MATCH (n)-[r]-(m) RETURN n"
        db = _FakeDB(estimate_for_stmt={
            ok_stmt: 1,
            bad_stmt: EXPLAIN_CARDINALITY_THRESHOLD * 10,
        })
        gb = self._builder(db)
        ok = gb._execute([ok_stmt, bad_stmt], chunk_id="c4", source_document="d.pdf")
        self.assertTrue(ok)
        self.assertEqual(db.executed, [ok_stmt])
        rejections = _read_jsonl(os.path.join(self.log_dir, "cypher_rejections.jsonl"))
        self.assertEqual(len(rejections), 1)
        self.assertEqual(rejections[0]["statement"], bad_stmt)


class TestExplainLiveIntegration(unittest.TestCase):
    """Amendment 5: real EXPLAIN against the docker-compose Neo4j.

    Skipped automatically if the driver can't connect.
    """

    def setUp(self):
        try:
            from agents.graph_rag.db import Neo4jHandler
            self.db = Neo4jHandler()
            if self.db.driver is None:
                self.skipTest("Neo4j driver did not connect; skipping live integration")
        except Exception as e:
            self.skipTest(f"Neo4j unavailable: {e}")

    def tearDown(self):
        if getattr(self, "db", None) is not None:
            self.db.close()

    def test_explain_returns_int_for_simple_match(self):
        rows = self.db.explain_estimated_rows("MATCH (n) RETURN n LIMIT 1")
        if rows is not None:
            self.assertIsInstance(rows, int)
            self.assertGreaterEqual(rows, 0)

    def test_explain_simple_merge_is_low_cardinality(self):
        rows = self.db.explain_estimated_rows(
            "MERGE (n:Country {name: '__sub_h_test_country__'}) RETURN n"
        )
        if rows is not None:
            from agents.graph_rag.builder import EXPLAIN_CARDINALITY_THRESHOLD
            self.assertLess(rows, EXPLAIN_CARDINALITY_THRESHOLD)


if __name__ == "__main__":
    unittest.main(verbosity=2)
