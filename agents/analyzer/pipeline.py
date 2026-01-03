import os
import hashlib
import yaml
import json
import re
from typing import List

from ingestion.pdf_loader import IngestionPipeline
from processing.chunker import DocumentChunker
from core.llm.client import get_llm_client

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

DEFAULT_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_COLLECTION = "regulations_chunks"


class AnalyzerPipeline:
    def __init__(self, config_path="configs/config.yaml"):
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        self.config = cfg
        self.ingest = IngestionPipeline()
        self.chunker = DocumentChunker(config_path=config_path)
        self.llm = get_llm_client()

        # Embedding model (HF all-MiniLM-L6-v2)
        self.embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        self.qdrant_url = cfg.get("qdrant", {}).get("url", DEFAULT_QDRANT_URL)
        self.q_client = QdrantClient(url=self.qdrant_url)
        self.collection_name = cfg.get("qdrant", {}).get("collection", DEFAULT_COLLECTION)

        # Ensure collection exists (create with appropriate vector size)
        try:
            dim = self.embedder.get_sentence_embedding_dimension()
        except Exception:
            # Fallback to known dim
            dim = 384

        # Create collection safely: check existing collections first
        try:
            exists = False
            try:
                collections = self.q_client.get_collections()
                cols = getattr(collections, 'collections', [])
                for c in cols:
                    # c may be namedtuple/object or dict
                    name = getattr(c, 'name', None) or c.get('name') if isinstance(c, dict) else None
                    if name == self.collection_name:
                        exists = True
                        break
            except Exception:
                # Fallback to try to get collection directly
                try:
                    _ = self.q_client.get_collection(self.collection_name)
                    exists = True
                except Exception:
                    exists = False

            if not exists:
                params = qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE)
                try:
                    self.q_client.create_collection(collection_name=self.collection_name, vectors_config=params)
                except Exception:
                    # If create_collection not available, try recreate_collection as last resort
                    try:
                        self.q_client.recreate_collection(collection_name=self.collection_name, vectors_config=params)
                    except Exception:
                        pass
        except Exception:
            # ignore collection creation errors here; operations will fail later if needed
            pass

    def _make_id(self, metadata: dict, text: str) -> str:
        base = f"{metadata.get('filename','')}-{metadata.get('chunk_id','')}-{text[:64]}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()

    def _parse_json_from_llm(self, result: str, expect_array: bool = True):
        """Helper method to extract JSON from LLM response."""
        try:
            # Try to extract JSON array or object from response
            if expect_array:
                match = re.search(r'\[.*\]', result, re.DOTALL)
            else:
                match = re.search(r'\{.*\}', result, re.DOTALL)
            
            if match:
                return json.loads(match.group(0))
        except Exception:
            pass
        return None

    def _summarize(self, text: str) -> str:
        prompt = f"Summarize the following insurance regulation text in a concise paragraph:\n\n{text}"
        return self.llm.generate(prompt)

    def _extract_keywords(self, text: str) -> list:
        prompt = (
            "Extract 5-10 key insurance terms and concepts from the following text. "
            "Return ONLY a JSON array of keyword strings.\n\n" + text
        )
        result = self.llm.generate(prompt)
        parsed = self._parse_json_from_llm(result, expect_array=True)
        if parsed:
            return parsed
        # Fallback: split by commas if not valid JSON
        return [k.strip() for k in result.split(',') if k.strip()][:10]

    def _generate_questions(self, text: str) -> list:
        prompt = (
            "Generate 3-5 hypothetical questions that the following insurance regulation text could answer. "
            "Return ONLY a JSON array of question strings.\n\n" + text
        )
        result = self.llm.generate(prompt)
        parsed = self._parse_json_from_llm(result, expect_array=True)
        if parsed:
            return parsed
        # Fallback: split by newlines
        return [q.strip() for q in result.split('\n') if q.strip() and '?' in q][:5]

    def _extract_requirements(self, text: str) -> list:
        prompt = (
            "Extract any explicit requirements, obligations, or normative statements from the following text. "
            "Return as a JSON array of requirement strings.\n\n" + text
        )
        result = self.llm.generate(prompt)
        parsed = self._parse_json_from_llm(result, expect_array=True)
        if parsed:
            return parsed
        # Fallback: return as single-item list
        return [result] if result else []

    def _classify_metadata(self, text: str, existing_metadata: dict) -> dict:
        """Extract or infer policy_type and clause_type from text and metadata."""
        # Use LLM to classify if not already in metadata
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
            "clause_type": "Requirement"  # Default
        }
        
        parsed = self._parse_json_from_llm(result, expect_array=False)
        if parsed:
            classification.update(parsed)
        
        return classification

    def _embed(self, text: str):
        vec = self.embedder.encode(text)
        return vec

    def _upsert_chunk(self, collection: str, chunk_id: str, vector, payload: dict):
        # Use qdrant PointStruct
        try:
            point = qmodels.PointStruct(id=chunk_id, vector=vector.tolist() if hasattr(vector, 'tolist') else vector, payload=payload)
            self.q_client.upsert(collection_name=collection, points=[point])
        except Exception:
            # best-effort: some qdrant versions use different method names
            try:
                self.q_client.upsert(collection_name=collection, points=[point])
            except Exception:
                pass

    def process_file(self, object_name: str):
        docs = self.ingest.download_and_load(object_name)
        if not docs:
            return {"status": "no_docs"}

        # Chunk
        chunks = self.chunker.chunk_documents(docs)

        enriched_chunks = []
        for idx, c in enumerate(chunks):
            text = c.page_content
            metadata = c.metadata

            # Enrich chunk with all required fields
            summary = self._summarize(text)
            keywords = self._extract_keywords(text)
            questions = self._generate_questions(text)
            requirements = self._extract_requirements(text)
            
            # Classify policy and clause type
            classification = self._classify_metadata(text, metadata)
            
            # Generate embedding
            embedding = self._embed(text)

            # Create unique chunk ID
            chunk_id = self._make_id(metadata, text)

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
                "embedding": embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
                "metadata": metadata  # Keep original metadata for compatibility
            }

            # Upsert to Qdrant
            self._upsert_chunk(self.collection_name, chunk_id, embedding, enriched_chunk)
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
