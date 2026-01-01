import json
import os
from langchain_community.document_loaders import PyPDFLoader
from ingestion.minio_loader import MinioClient

class IngestionPipeline:
    def __init__(self, processed_files_path="processed_files.json"):
        self.minio_client = MinioClient()
        self.processed_files_path = processed_files_path
        self.processed_files = self._load_processed_files()

    def _load_processed_files(self):
        if os.path.exists(self.processed_files_path):
            with open(self.processed_files_path, "r") as f:
                return json.load(f)
        return {}

    def _save_processed_files(self):
        with open(self.processed_files_path, "w") as f:
            json.dump(self.processed_files, f, indent=4)

    def get_new_files(self):
        """Get list of files that haven't been processed yet."""
        all_files = self.minio_client.list_pdf_files()
        new_files = [f for f in all_files if f not in self.processed_files]
        return new_files

    def download_and_load(self, object_name):
        """Download file and load text with metadata."""
        local_path = f"temp_{object_name.replace('/', '_')}"
        
        # Ensure temp download works even if nested
        if not self.minio_client.download_file(object_name, local_path):
            return None

        try:
            loader = PyPDFLoader(local_path)
            docs = loader.load()
            
            # Enrich metadata
            for doc in docs:
                doc.metadata["source_path"] = object_name
                # Naive country extraction from folder structure: country/file.pdf
                parts = object_name.split('/')
                if len(parts) > 1:
                    doc.metadata["country"] = parts[0]
                doc.metadata["filename"] = parts[-1]

            return docs
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    def mark_as_processed(self, object_name):
        self.processed_files[object_name] = True
        self._save_processed_files()
