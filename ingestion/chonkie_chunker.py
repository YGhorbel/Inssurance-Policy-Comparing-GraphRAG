from chonkie import SemanticChunker
import yaml

class ChonkieChunker:
    def __init__(self, config_path="configs/config.yaml"):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)["processing"]
        
        self.chunk_size = config.get("chunk_size", 800)
        self.chunk_overlap = config.get("chunk_overlap", 150)
        self.model_name = "sentence-transformers/all-MiniLM-L6-v2"

        print(f"Initializing Chonkie SemanticChunker with model={self.model_name}...")
        self.chunker = SemanticChunker(
            chunk_size=self.chunk_size,
            overlap=self.chunk_overlap,
            model=self.model_name,
            device="cuda" 
        )

    def chunk_text(self, text, metadata):
        """
        Chunk text and return list of dicts with text and metadata.
        """
        chunks = self.chunker(text)
        processed_chunks = []
        
        for chunk in chunks:
            # Check attribute access based on Chonkie version, assuming .text and .id or similar
            # If chunk is a string (older versions or simple chunkers), handle that
            chunk_text = getattr(chunk, 'text', str(chunk))
            chunk_id = getattr(chunk, 'id', None) # ID might be None if not provided by library

            chunk_meta = metadata.copy()
            if chunk_id:
                chunk_meta["chunk_id"] = chunk_id
            
            processed_chunks.append({
                "text": chunk_text,
                "metadata": chunk_meta
            })
            
        return processed_chunks
