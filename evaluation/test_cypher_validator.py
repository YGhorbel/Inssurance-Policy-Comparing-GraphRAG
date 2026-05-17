"""Deterministic tests for the schema-aware Cypher validator.

Run from repo root:  python3 evaluation/test_cypher_validator.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _isolate_logs() -> str:
    tmp = tempfile.mkdtemp(prefix="rrf_logs_")
    os.environ["AGENT_LOG_DIR"] = tmp
    return tmp


_isolate_logs()

from agents.graph_rag.validator import (
    ALLOWED_NODES,
    ALLOWED_RELATIONSHIPS,
    SYMMETRIC_RELATIONSHIPS,
    DIRECTED_RELATIONSHIPS,
    validate,
)


def test_seven_edges_and_nine_nodes() -> None:
    assert ALLOWED_RELATIONSHIPS == frozenset({
        "APPLIES_TO", "REQUIRES", "REFERENCES",
        "EQUIVALENT_TO", "CONFLICTS_WITH",
        "PART_OF", "DEFINES",
    })
    assert len(ALLOWED_RELATIONSHIPS) == 7
    assert len(ALLOWED_NODES) == 9
    assert SYMMETRIC_RELATIONSHIPS == frozenset({"EQUIVALENT_TO", "CONFLICTS_WITH"})
    assert DIRECTED_RELATIONSHIPS | SYMMETRIC_RELATIONSHIPS == ALLOWED_RELATIONSHIPS
    assert DIRECTED_RELATIONSHIPS & SYMMETRIC_RELATIONSHIPS == frozenset()


def test_clean_statement_accepted_and_name_normalized() -> None:
    raw = 'MERGE (c:Country {name: "the republic of tunisia"})'
    accepted, rejections = validate(raw, chunk_id="c1", source_document="t.pdf")
    assert rejections == []
    assert len(accepted) == 1
    assert '"Republic Of Tunisia"' in accepted[0]


def test_bad_label_rejected() -> None:
    raw = 'MERGE (x:Vehicle {name: "Car"})'
    accepted, rejections = validate(raw, chunk_id="c2", source_document="t.pdf")
    assert accepted == []
    assert len(rejections) == 1
    assert rejections[0].reason == "label_not_in_whitelist"
    assert rejections[0].rejected_token == "Vehicle"


def test_legacy_relationship_rejected() -> None:
    raw = 'MERGE (a:Regulation {name: "X"})-[:HAS_POLICY]->(b:PolicyType {name: "Auto"})'
    accepted, rejections = validate(raw, chunk_id="c3", source_document="t.pdf")
    assert accepted == []
    assert rejections[0].reason == "relationship_not_in_whitelist"
    assert rejections[0].rejected_token == "HAS_POLICY"


def test_destructive_keyword_rejected() -> None:
    raw = "MATCH (n:Regulation) DETACH DELETE n"
    accepted, rejections = validate(raw, chunk_id="c4", source_document="t.pdf")
    assert accepted == []
    assert rejections[0].reason == "destructive_keyword"


def test_prose_and_markdown_handled() -> None:
    raw = (
        "```cypher\n"
        'MERGE (r:Regulation {name: "Insurance Code"});\n'
        "Here is some explanation that should be dropped;\n"
        'MERGE (a:Article {id: "Art. 1"})-[:PART_OF]->(r);\n'
        "```"
    )
    accepted, rejections = validate(raw, chunk_id="c5", source_document="t.pdf")
    assert len(accepted) == 2
    assert any(r.reason == "not_cypher_or_prose" for r in rejections)


def test_paper_taxonomy_examples_round_trip() -> None:
    raw = (
        'MERGE (a:Requirement {name: "Third-party liability"});'
        'MERGE (b:Requirement {name: "Compulsory motor insurance"});'
        'MERGE (a)-[:EQUIVALENT_TO]->(b);'
        'MERGE (c:Requirement {name: "Driver intoxication exclusion"});'
        'MERGE (a)-[:CONFLICTS_WITH]->(c);'
    )
    accepted, rejections = validate(raw, chunk_id="c6", source_document="t.pdf")
    assert rejections == []
    assert len(accepted) == 5


if __name__ == "__main__":
    test_seven_edges_and_nine_nodes()
    test_clean_statement_accepted_and_name_normalized()
    test_bad_label_rejected()
    test_legacy_relationship_rejected()
    test_destructive_keyword_rejected()
    test_prose_and_markdown_handled()
    test_paper_taxonomy_examples_round_trip()
    print("OK: all 7 Cypher validator tests passed.")
