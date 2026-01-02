import os
import hashlib
import yaml
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

    def _summarize(self, text: str) -> str:
        prompt = f"Summarize the following insurance regulation text in a concise paragraph:\n\n{text}"
        return self.llm.generate(prompt)

    def _extract_requirements(self, text: str) -> str:
        prompt = (
            "Extract any explicit requirements, obligations, or normative statements from the following text. "
            "Return as a JSON array of requirement strings.\n\n" + text
        )
        return self.llm.generate(prompt)

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

        points = []
        for c in chunks:
            text = c.page_content
            metadata = c.metadata

            summary = self._summarize(text)
            requirements = self._extract_requirements(text)
            embedding = self._embed(text)

            chunk_id = self._make_id(metadata, text)

            payload = {
                "summary": summary,
                "original_text": text,
                "requirements": requirements,
                "metadata": metadata,
            }

            # Upsert to Qdrant
            self._upsert_chunk(self.collection_name, chunk_id, embedding, payload)

        # Mark processed
        self.ingest.mark_as_processed(object_name)
        return {"status": "processed", "file": object_name, "chunks_indexed": len(chunks)}

    def process_new_files(self) -> List[dict]:
        new_files = self.ingest.get_new_files()
        results = []
        for f in new_files:
            results.append(self.process_file(f))
        return results


__all__ = ["AnalyzerPipeline"]
