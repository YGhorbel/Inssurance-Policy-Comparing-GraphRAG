import atexit
import hashlib
import json
import os
import re
import uuid
from collections import Counter
from typing import List, Optional

import yaml

from agents.shared.embeddings import get_embedder
from agents.shared.jsonl_logger import log_event
from core.llm.client import get_llm_client
from ingestion.pdf_loader import IngestionPipeline
from processing.chunker import DocumentChunker

_ANALYZER_TOTALS: "Counter[tuple]" = Counter()
_TOTALS_FLUSHED = False


def _flush_analyzer_totals() -> None:
    """atexit handler: persist the in-memory total-call counter to JSONL.

    Without this, a mid-document crash would silently inflate apparent
    success rates because failure events are written immediately but the
    denominator (total calls) only lands on process exit.
    """
    global _TOTALS_FLUSHED
    if _TOTALS_FLUSHED or not _ANALYZER_TOTALS:
        return
    _TOTALS_FLUSHED = True
    for (extractor, source_document), count in _ANALYZER_TOTALS.items():
        log_event("analyzer_totals.jsonl", {
            "extractor": extractor,
            "source_document": source_document,
            "total_calls": count,
        })


atexit.register(_flush_analyzer_totals)

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

DEFAULT_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_COLLECTION = "regulations_chunks_v2"


class AnalyzerPipeline:
    # Enrichment configuration constants
    MAX_KEYWORDS = 10
    MAX_QUESTIONS = 5
    
    def __init__(self, config_path="configs/config.yaml"):
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        self.config = cfg
        self.ingest = IngestionPipeline()
        self.chunker = DocumentChunker(config_path=config_path)
        self.llm = get_llm_client()

        self.embedder = get_embedder(config_path=config_path)
        self.qdrant_url = cfg.get("qdrant", {}).get("url", DEFAULT_QDRANT_URL)
        self.q_client = QdrantClient(url=self.qdrant_url)
        self.collection_name = cfg.get("qdrant", {}).get("collection", DEFAULT_COLLECTION)
        self.sparse_enabled = bool(cfg.get("embeddings", {}).get("sparse_enabled", True))

        dim = self.embedder.dim

        try:
            exists = False
            try:
                collections = self.q_client.get_collections()
                cols = getattr(collections, 'collections', [])
                for c in cols:
                    name = getattr(c, 'name', None) or c.get('name') if isinstance(c, dict) else None
                    if name == self.collection_name:
                        exists = True
                        break
            except Exception:
                try:
                    _ = self.q_client.get_collection(self.collection_name)
                    exists = True
                except Exception:
                    exists = False

            if not exists:
                vectors_cfg = {"dense": qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE)}
                sparse_cfg = {"sparse": qmodels.SparseVectorParams()} if self.sparse_enabled else None
                try:
                    self.q_client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=vectors_cfg,
                        sparse_vectors_config=sparse_cfg,
                    )
                except Exception:
                    try:
                        self.q_client.recreate_collection(
                            collection_name=self.collection_name,
                            vectors_config=vectors_cfg,
                            sparse_vectors_config=sparse_cfg,
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    def _make_id(self, metadata: dict, text: str) -> str:
        base = f"{metadata.get('filename','')}-{metadata.get('chunk_id','')}-{text[:64]}"
        # Qdrant requires either ints or UUID-formatted strings as point IDs;
        # a deterministic uuid5 keeps the (filename, chunk_id) -> id mapping
        # stable across reingests so the rejection JSONL traces remain valid.
        return str(uuid.uuid5(uuid.NAMESPACE_OID, base))

    def _parse_json_from_llm(
        self,
        result: str,
        expect_array: bool = True,
        extractor: str = "unknown",
        chunk_id: Optional[str] = None,
        source_document: Optional[str] = None,
    ):
        """Extract a JSON array/object from an LLM response.

        Returns the parsed value or None. On a parse miss, a structured
        event is appended to logs/analyzer_failures.jsonl so the
        downstream extraction-success-rate metric can be computed in §2.4
        of the paper. Callers always handle None gracefully (the silent
        fallback contract is unchanged); the only behavioural difference
        is that misses are now visible.
        """
        _ANALYZER_TOTALS[(extractor, source_document)] += 1

        if expect_array:
            match = re.search(r'\[.*\]', result, re.DOTALL)
        else:
            match = re.search(r'\{.*\}', result, re.DOTALL)

        if match is None:
            log_event("analyzer_failures.jsonl", {
                "chunk_id": chunk_id,
                "source_document": source_document,
                "extractor": extractor,
                "expect_array": expect_array,
                "llm_output_excerpt": (result or "")[:200],
                "error_type": "no_json_match",
                "error_message": "",
            })
            return None

        try:
            return json.loads(match.group(0))
        except Exception as exc:
            log_event("analyzer_failures.jsonl", {
                "chunk_id": chunk_id,
                "source_document": source_document,
                "extractor": extractor,
                "expect_array": expect_array,
                "llm_output_excerpt": (result or "")[:200],
                "error_type": "json_decode_error",
                "error_message": str(exc)[:200],
            })
            return None

    def _summarize(self, text: str) -> str:
        prompt = f"Summarize the following insurance regulation text in a concise paragraph:\n\n{text}"
        return self.llm.generate(prompt)

    def _extract_keywords(
        self, text: str, chunk_id: Optional[str] = None, source_document: Optional[str] = None,
    ) -> list:
        prompt = (
            "Extract 5-10 key insurance terms and concepts from the following text. "
            "Return ONLY a JSON array of keyword strings.\n\n" + text
        )
        result = self.llm.generate(prompt)
        parsed = self._parse_json_from_llm(
            result, expect_array=True,
            extractor="keywords", chunk_id=chunk_id, source_document=source_document,
        )
        if parsed:
            return parsed
        return [k.strip() for k in result.split(',') if k.strip()][:self.MAX_KEYWORDS]

    def _generate_questions(
        self, text: str, chunk_id: Optional[str] = None, source_document: Optional[str] = None,
    ) -> list:
        prompt = (
            "Generate 3-5 hypothetical questions that the following insurance regulation text could answer. "
            "Return ONLY a JSON array of question strings.\n\n" + text
        )
        result = self.llm.generate(prompt)
        parsed = self._parse_json_from_llm(
            result, expect_array=True,
            extractor="questions", chunk_id=chunk_id, source_document=source_document,
        )
        if parsed:
            return parsed
        return [q.strip() for q in result.split('\n') if q.strip() and '?' in q][:self.MAX_QUESTIONS]

    def _extract_requirements(
        self, text: str, chunk_id: Optional[str] = None, source_document: Optional[str] = None,
    ) -> list:
        prompt = (
            "Extract any explicit requirements, obligations, or normative statements from the following text. "
            "Return as a JSON array of requirement strings.\n\n" + text
        )
        result = self.llm.generate(prompt)
        parsed = self._parse_json_from_llm(
            result, expect_array=True,
            extractor="requirements", chunk_id=chunk_id, source_document=source_document,
        )
        if parsed:
            return parsed
        return [result] if result else []

    def _classify_metadata(
        self,
        text: str,
        existing_metadata: dict,
        chunk_id: Optional[str] = None,
        source_document: Optional[str] = None,
    ) -> dict:
        prompt = (
            "Analyze the following insurance text and classify it:\n"
            "1. Policy Type: Auto, Health, Life, Property, or General\n"
            "2. Clause Type: Requirement, Coverage, Exclusion, Procedure, or Definition\n\n"
            "Text: " + text[:500] + "\n\n"
            "Return ONLY a JSON object with 'policy_type' and 'clause_type' keys."
        )
        result = self.llm.generate(prompt)

        classification = {
            "policy_type": existing_metadata.get("policy_type", "General"),
            "clause_type": "Requirement",
        }

        parsed = self._parse_json_from_llm(
            result, expect_array=False,
            extractor="classification", chunk_id=chunk_id, source_document=source_document,
        )
        if parsed:
            classification.update(parsed)

        return classification

    def _embed_hybrid(self, text: str) -> dict:
        """Returns {dense: [float], sparse: {indices, values}?}."""
        return self.embedder.encode_hybrid([text])[0]

    def _upsert_chunk(self, collection: str, chunk_id: str, hybrid: dict, payload: dict):
        vector_struct: dict = {"dense": hybrid["dense"]}
        if "sparse" in hybrid:
            vector_struct["sparse"] = qmodels.SparseVector(
                indices=hybrid["sparse"]["indices"],
                values=hybrid["sparse"]["values"],
            )
        try:
            point = qmodels.PointStruct(id=chunk_id, vector=vector_struct, payload=payload)
            self.q_client.upsert(collection_name=collection, points=[point])
        except Exception as exc:
            print(f"    > Qdrant upsert error: {str(exc)[:120]}")

    def process_file(self, object_name: str):
        docs = self.ingest.download_and_load(object_name)
        if not docs:
            return {"status": "no_docs"}

        # Chunk
        chunks = self.chunker.chunk_documents(docs)

        enriched_chunks = []
        for c in chunks:
            text = c.page_content
            metadata = c.metadata
            source_document = metadata.get("filename", object_name)
            chunk_id = self._make_id(metadata, text)

            summary = self._summarize(text)
            keywords = self._extract_keywords(text, chunk_id=chunk_id, source_document=source_document)
            questions = self._generate_questions(text, chunk_id=chunk_id, source_document=source_document)
            requirements = self._extract_requirements(text, chunk_id=chunk_id, source_document=source_document)
            classification = self._classify_metadata(text, metadata, chunk_id=chunk_id, source_document=source_document)

            hybrid = self._embed_hybrid(text)

            # Build enriched chunk structure matching the spec
            enriched_chunk = {
                "chunk_id": chunk_id,
                "text": text,
                "summary": summary,
                "keywords": keywords,
                "questions": questions,
                "country": metadata.get("country", "Unknown"),
                "policy_type": classification.get("policy_type", "General"),
                "clause_type": classification.get("clause_type", "Requirement"),
                "extracted_requirements": requirements,
                "source": {
                    "document": metadata.get("filename", object_name),
                    "page": metadata.get("page", 0),
                    "section": metadata.get("section", "")
                },
                "embedding": hybrid["dense"],
                "metadata": metadata,
            }

            self._upsert_chunk(self.collection_name, chunk_id, hybrid, enriched_chunk)
            enriched_chunks.append(enriched_chunk)

        # Mark processed
        self.ingest.mark_as_processed(object_name)
        return {
            "status": "processed", 
            "file": object_name, 
            "chunks_indexed": len(chunks),
            "enriched_chunks": enriched_chunks
        }

    def process_new_files(self) -> List[dict]:
        new_files = self.ingest.get_new_files()
        results = []
        for f in new_files:
            results.append(self.process_file(f))
        return results


__all__ = ["AnalyzerPipeline"]
