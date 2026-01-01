import json
import re
from ingestion.minio_loader import MinioClient
from ingestion.pdf_loader import IngestionPipeline as PdfPipeline # Reusing existing logic
from ingestion.chonkie_chunker import ChonkieChunker
from ingestion.graph_builder import GraphBuilder
from models.hf_client import FHClient
from models.prompts import GraphPrompts # Assuming prompts stay in models
from ingestion.cleaner import TextCleaner

class Pipeline:
    def __init__(self):
        self.pdf_pipeline = PdfPipeline() # Use the existing PDF loader logic
        self.cleaner = TextCleaner()
        self.chunker = ChonkieChunker()
        self.hf_client = FHClient()
        self.graph_builder = GraphBuilder()

    def parse_json_from_llm(self, response: str):
        try:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)
        except Exception:
            pass
        return None

    def run(self):
        print("Starting Chonkie-GraphRAG Pipeline...")
        
        # 1. Ingestion: Check MinIO for new files
        new_files = self.pdf_pipeline.get_new_files()
        print(f"Found {len(new_files)} new files.")

        if not new_files:
            return

        for file_obj in new_files:
            print(f"Processing {file_obj}...")
            # Load PDF
            docs = self.pdf_pipeline.download_and_load(file_obj)
            
            if not docs:
                print(f"Failed to load {file_obj}")
                continue

            for doc in docs:
                # 2. Cleaning
                cleaned_text = self.cleaner.clean_text(doc.page_content)
                
                # 3. Chonkie Chunking
                # Chunk text and keep metadata
                chunks = self.chunker.chunk_text(cleaned_text, doc.metadata)
                print(f"Generated {len(chunks)} semantic chunks for a document page.")

                # 4. Graph Extraction & Ingestion
                for i, chunk_data in enumerate(chunks):
                    text_content = chunk_data["text"]
                    # Optionally use chunk_data['metadata'] in graph props if needed
                    
                    print(f"Extracting from chunk {i+1}/{len(chunks)}...")
                    prompt = GraphPrompts.get_extraction_prompt(text_content)
                    
                    response = self.hf_client.generate(prompt)
                    if response:
                        print("Cypher generated. Executing...")
                        self.graph_builder.build_graph_from_cypher(response)
                    else:
                        print("LLM returned empty response.")

            # Mark processed
            self.pdf_pipeline.mark_as_processed(file_obj)

        self.graph_builder.close()
        print("Pipeline Complete.")

if __name__ == "__main__":
    pipeline = Pipeline()
    pipeline.run()
