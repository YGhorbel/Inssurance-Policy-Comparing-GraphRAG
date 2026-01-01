from chonkie import SemanticChunker
import yaml

class ChonkieHandler:
    def __init__(self, config_path="configs/config.yaml"):
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f).get("processing", {})
        except Exception:
            config = {}
        
        self.chunk_size = config.get("chunk_size", 800)
        self.chunk_overlap = config.get("chunk_overlap", 150)
        # Using CPU to avoid VRAM conflicts with LiquidAI
        self.device = "cpu"
        self.model_name = "sentence-transformers/all-MiniLM-L6-v2"

        print(f"Initializing Chonkie with model={self.model_name} on {self.device}...")
        self.chunker = SemanticChunker(
            chunk_size=self.chunk_size,
            overlap=self.chunk_overlap,
            model=self.model_name,
            device=self.device
        )

    def chunk_text(self, text, metadata):
        chunks = self.chunker(text)
        processed_chunks = []
        
        for i, chunk in enumerate(chunks):
            chunk_text = getattr(chunk, 'text', str(chunk))
            chunk_meta = metadata.copy()
            chunk_meta["chunk_id"] = i
            
            processed_chunks.append({
                "text": chunk_text,
                "metadata": chunk_meta
            })
            
        return processed_chunks
