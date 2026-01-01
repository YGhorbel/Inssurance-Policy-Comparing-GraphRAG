import yaml
try:
    from chonkie import SemanticChunker
except ImportError:
    # Fallback or mock for environment without chonkie installed yet
    class SemanticChunker:
        def __init__(self, **kwargs): pass
        def __call__(self, text): return []

class DocumentChunker:
    def __init__(self, config_path="configs/config.yaml"):
        # We can still load config if we want to make it configurable, 
        # but for now we hardcode the user's requested Chonkie setup 
        # or load from config.
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)["processing"]
        
        # User requested specific model and params
        # "sentence-transformers/all-MiniLM-L6-v2"
        # chunk_size=800, overlap=150
        
        self.chunk_size = config.get("chunk_size", 800)
        self.chunk_overlap = config.get("chunk_overlap", 150)
        self.model_name = "sentence-transformers/all-MiniLM-L6-v2"

        print(f"Initializing Chonkie SemanticChunker with model={self.model_name}...")
        self.chunker = SemanticChunker(
            chunk_size=self.chunk_size,
            overlap=self.chunk_overlap,
            model=self.model_name
        )

    def chunk_documents(self, documents):
        """
        Split a list of LangChain Document objects into chunks using Chonkie.
        Returns a list of LangChain Document objects (or similar dictionaries) 
        compatible with the next step.
        """
        chunked_docs = []
        
        for doc in documents:
            text = doc.page_content
            metadata = doc.metadata
            
            # Chonkie usually returns list of Chunk objects
            # Check chonkie docs or user provided snippet. 
            # User snippet: chunker(text) -> chunks. chunk.text, chunk.id
            
            chunks = self.chunker(text)
            
            for chunk in chunks:
                # We wrap it back into a structure compatible with our pipeline
                # The pipeline expects objects with .page_content and .metadata
                # We can reuse LangChain's Document class or a simple object
                
                # Note: Chonkie might return objects with .text attribute
                content = getattr(chunk, 'text', str(chunk))
                
                new_doc = type('Document', (), {})()
                new_doc.page_content = content
                new_doc.metadata = metadata.copy()
                # Optional: add chunk id if available
                if hasattr(chunk, 'id'):
                    new_doc.metadata['chunk_id'] = chunk.id
                
                chunked_docs.append(new_doc)
                
        return chunked_docs
