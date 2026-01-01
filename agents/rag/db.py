from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
import uuid

class QdrantHandler:
    def __init__(self, collection_name="regulations"):
        self.client = QdrantClient("localhost", port=6333)
        self.collection_name = collection_name
        # Use same model as Chonkie for consistency
        self.encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            self.client.get_collection(self.collection_name)
        except Exception:
            print(f"Creating Qdrant collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )

    def ingest_chunks(self, chunks, batch_size=50):
        """Ingest chunks in batches to avoid connection timeout."""
        points = []
        for chunk in chunks:
            text = chunk["text"]
            meta = chunk["metadata"]
            vector = self.encoder.encode(text).tolist()
            
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={ "text": text, **meta }
            ))
        
        if not points:
            return False
        
        # Upload in batches to avoid timeout
        total = len(points)
        for i in range(0, total, batch_size):
            batch = points[i:i + batch_size]
            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
                print(f"    > Qdrant: Uploaded batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size}")
            except Exception as e:
                print(f"    > Qdrant batch upload error: {e}")
                return False
        
        return True

    def search(self, query: str, top_k=5):
        vector = self.encoder.encode(query).tolist()
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=top_k
        )
        return [
            {"text": hit.payload["text"], "score": hit.score, "metadata": hit.payload}
            for hit in results
        ]
