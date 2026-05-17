"""Schema-aware Cypher validator for LLM-generated graph extraction.

Drawn from:
- Tiwari et al. (2024), SynthCypher (arxiv 2412.12612): deterministic
  pre-execution checks - markdown extraction, node-label / relationship-type
  whitelisting, destructive-clause blocking.
- Meher et al. (2025), CORE-KG (arxiv 2506.21607): pre-execution
  normalization of entity-name surface forms (title stripping, whitespace
  collapse, conservative title-casing) as a deterministic MVP. CORE-KG itself
  warns that pure deterministic dedup is insufficient for lexically dense
  legal text; we accept that and treat this layer as a structural-validity
  guard, not a semantic-equivalence solver.

The seven allowed edges are the reconciled Phase 1 taxonomy committed in the
paper manuscript. Of these, EQUIVALENT_TO and CONFLICTS_WITH are semantically
symmetric; APPLIES_TO, REQUIRES, REFERENCES, PART_OF, DEFINES are directed.
The validator does NOT enforce direction in Phase 1; Phase 5 query rewrites
will rely on this distinction.

All rejections are written to logs/cypher_rejections.jsonl with chunk_id and
source_document so a graph-construction-quality metric can be aggregated in
the paper's §2.4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from agents.shared.jsonl_logger import log_event

ALLOWED_NODES = frozenset({
    "Regulation", "Article", "Obligation", "Authority",
    "Entity", "Concept", "PolicyType", "Country", "Requirement",
})

ALLOWED_RELATIONSHIPS = frozenset({
    "APPLIES_TO", "REQUIRES", "REFERENCES",
    "EQUIVALENT_TO", "CONFLICTS_WITH",
    "PART_OF", "DEFINES",
})

SYMMETRIC_RELATIONSHIPS = frozenset({"EQUIVALENT_TO", "CONFLICTS_WITH"})
DIRECTED_RELATIONSHIPS = ALLOWED_RELATIONSHIPS - SYMMETRIC_RELATIONSHIPS

DESTRUCTIVE_KEYWORDS = (
    "DROP", "DELETE", "REMOVE", "DETACH DELETE",
    "CREATE INDEX", "CREATE CONSTRAINT",
    "CALL APOC.", "LOAD CSV",
)

_OPENING_KEYWORDS = frozenset({
    "MERGE", "MATCH", "CREATE", "RETURN", "WITH",
    "WHERE", "SET", "UNWIND", "OPTIONAL",
})

_TITLE_PREFIXES = (
    "the ", "an ", "a ",
    "article ", "art. ", "art ",
    "officer ", "defendant ", "mr. ", "mrs. ", "ms. ", "dr. ",
)

_LABEL_RE = re.compile(r"\(\s*\w*\s*:(\w+)")
_REL_RE = re.compile(r"\[\s*\w*\s*:(\w+)")
_NAME_RE = re.compile(r'(\{[^{}]*?name:\s*)(["\'])(.*?)\2', re.DOTALL)


@dataclass
class Rejection:
    statement: str
    reason: str
    rejected_token: Optional[str] = None


def _normalize_name(raw: str) -> str:
    """CORE-KG-inspired MVP normalization (deterministic, no LLM).

    Strips wrapping whitespace, collapses internal whitespace, removes
    leading article/title tokens, and applies a conservative title-case so
    'tunisia', 'TUNISIA', and 'Tunisia' all map to 'Tunisia' without erasing
    multi-word distinctions like 'Republic of Tunisia'.
    """
    if not raw:
        return raw
    s = raw.strip()
    s = re.sub(r"\s+", " ", s)
    lowered = s.lower()
    for prefix in _TITLE_PREFIXES:
        if lowered.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.title() if s else s


def _strip_markdown(raw: str) -> str:
    out = re.sub(r"```cypher\s*", "", raw, flags=re.IGNORECASE)
    out = re.sub(r"```\s*", "", out)
    return out


def _is_prose(stmt: str) -> bool:
    stripped = stmt.lstrip()
    return stripped.startswith(("This ", "The ", "Here ", "Note:", "**"))


def _has_destructive(stmt: str) -> Optional[str]:
    upper = stmt.upper()
    for kw in DESTRUCTIVE_KEYWORDS:
        if kw in upper:
            return kw
    return None


def _bad_node_label(stmt: str) -> Optional[str]:
    for label in _LABEL_RE.findall(stmt):
        if label not in ALLOWED_NODES:
            return label
    return None


def _bad_relationship(stmt: str) -> Optional[str]:
    for rel in _REL_RE.findall(stmt):
        if rel not in ALLOWED_RELATIONSHIPS:
            return rel
    return None


def _apply_name_normalization(stmt: str) -> str:
    def _sub(match: re.Match) -> str:
        prefix, quote, value = match.group(1), match.group(2), match.group(3)
        return f"{prefix}{quote}{_normalize_name(value)}{quote}"

    return _NAME_RE.sub(_sub, stmt)


def validate(
    raw_output: str,
    chunk_id: Optional[str] = None,
    source_document: Optional[str] = None,
) -> Tuple[List[str], List[Rejection]]:
    """Return (accepted_statements, rejections) for one LLM Cypher response.

    Rejections are written to logs/cypher_rejections.jsonl with chunk_id and
    source_document so per-corpus rejection rates can be aggregated in §2.4.
    The validator never raises; the caller decides what to do with rejections.
    """
    accepted: List[str] = []
    rejections: List[Rejection] = []

    cleaned = _strip_markdown(raw_output or "")
    parts = [p.strip() for p in cleaned.split(";") if p.strip()]

    for stmt in parts:
        first_token = stmt.split(None, 1)[0].upper() if stmt.split() else ""
        if first_token not in _OPENING_KEYWORDS or _is_prose(stmt):
            rejections.append(Rejection(stmt, "not_cypher_or_prose", first_token or None))
            continue

        destructive = _has_destructive(stmt)
        if destructive:
            rejections.append(Rejection(stmt, "destructive_keyword", destructive))
            continue

        bad_label = _bad_node_label(stmt)
        if bad_label:
            rejections.append(Rejection(stmt, "label_not_in_whitelist", bad_label))
            continue

        bad_rel = _bad_relationship(stmt)
        if bad_rel:
            rejections.append(Rejection(stmt, "relationship_not_in_whitelist", bad_rel))
            continue

        accepted.append(_apply_name_normalization(stmt))

    for r in rejections:
        log_event("cypher_rejections.jsonl", {
            "chunk_id": chunk_id,
            "source_document": source_document,
            "statement": r.statement[:500],
            "rejection_reason": r.reason,
            "rejected_token": r.rejected_token,
        })

    return accepted, rejections


class CypherValidator:
    """Static facade preserved for callers that import the class directly."""

    VALID_KEYWORDS = _OPENING_KEYWORDS

    @staticmethod
    def is_valid_cypher(query: str) -> bool:
        if not query or not query.strip():
            return False
        first = query.strip().split(None, 1)[0].upper()
        return first in _OPENING_KEYWORDS

    @staticmethod
    def extract_cypher_statements(raw_output: str) -> List[str]:
        """Backwards-compatible shim used by legacy callers.

        Forwards to validate() and discards the rejection list. New code
        should call validate() directly so the rejection log gets a
        chunk_id and source_document.
        """
        accepted, _ = validate(raw_output)
        return accepted

    @staticmethod
    def fix_common_errors(query: str) -> Optional[str]:
        if _is_prose(query):
            return None
        query = re.sub(r"MERGE\s+:(\w+)", r"MERGE (:\1)", query)
        query = re.sub(r"\)\s+:(\w+)\s*$", r")", query)
        if re.search(r"\}\s+:\w+\s+:", query):
            return None
        return query


def validate_and_execute(db, raw_cypher: str) -> tuple:
    """Legacy helper kept for callers outside the canonical builder path."""
    accepted, _ = validate(raw_cypher)
    success = 0
    errors: List[str] = []
    for stmt in accepted:
        try:
            db.execute_query(stmt)
            success += 1
        except Exception as e:
            errors.append(f"Query Error: {str(e)[:100]}")
    return success, len(errors), errors


__all__ = [
    "ALLOWED_NODES",
    "ALLOWED_RELATIONSHIPS",
    "SYMMETRIC_RELATIONSHIPS",
    "DIRECTED_RELATIONSHIPS",
    "DESTRUCTIVE_KEYWORDS",
    "Rejection",
    "validate",
    "CypherValidator",
    "validate_and_execute",
]
