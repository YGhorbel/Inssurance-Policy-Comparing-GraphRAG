import json
import os
import uuid
from datetime import datetime
from agents.document_access.minio import MinioHandler

METADATA_FILE = "data/documents_metadata.json"
MINIO_CONNECTION_ERROR = "Failed to connect to MinIO or list documents. Please check MinIO connection settings and ensure the service is running."

class MetadataManager:
    def __init__(self):
        self.minio = MinioHandler()
        self.db_path = METADATA_FILE
        self._ensure_db()

    def _ensure_db(self):
        # Ensure the directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        # Create the file if it doesn't exist
        if not os.path.exists(self.db_path):
            with open(self.db_path, "w") as f:
                json.dump([], f)

    def load_metadata(self):
        try:
            with open(self.db_path, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def save_metadata(self, data):
        with open(self.db_path, "w") as f:
            json.dump(data, f, indent=4)

    def sync_with_minio(self):
        """
        Syncs local metadata DB with actual files in MinIO.
        Adds new files, marks missing ones? (Optional: keep history)
        """
        minio_files = self.minio.list_documents()
        current_data = self.load_metadata()
        # If MinIO listing failed (None), raise an error instead of silently returning existing data
        if minio_files is None:
            print(MINIO_CONNECTION_ERROR)
            raise Exception(MINIO_CONNECTION_ERROR)
        current_filenames = {item["filename"]: item for item in current_data}
        
        updated_data = []
        
        # 1. Update/Add existing files
        for f in minio_files:
            fname = f["filename"]
            if fname in current_filenames:
                # Update existing (keep ID and manual edits)
                entry = current_filenames[fname]
                entry["size"] = f["size"]
                entry["last_modified_minio"] = f["last_modified"]
                updated_data.append(entry)
            else:
                # Add new
                # Auto-detect country from folder path
                country = "Unknown"
                dirname = os.path.dirname(fname)
                if dirname:
                    # Get the top-level folder name
                    folder = dirname.split('/')[0].lower()
                    if folder == "tunisia":
                        country = "Tunisia"
                    elif folder == "france":
                        country = "France"
                    elif folder == "europe":
                        country = "Europe"
                
                new_entry = {
                    "id": str(uuid.uuid4()),
                    "filename": fname,
                    "country": country,
                    "doc_type": "Regulation", # Default
                    "visibility": "visible",
                    "status": "pending", # pending, processing, processed, error
                    "size": f["size"],
                    "last_modified_minio": f["last_modified"],
                    "added_at": datetime.now().isoformat()
                }
                updated_data.append(new_entry)
        
        # 2. (Optional) Handle deleted files? 
        # For now, let's keep them but maybe mark as 'deleted_in_source' if we wanted strictly sync.
        # But to match the list, we only replace with what's in MinIO + persisted metadata.
        # If a file is removed from MinIO, it won't be in `minio_files`, so it won't be in `updated_data`.
        # This implies "hard sync".
        
        self.save_metadata(updated_data)
        return updated_data

    def update_document(self, doc_id, updates: dict):
        data = self.load_metadata()
        for item in data:
            if item["id"] == doc_id:
                item.update(updates)
                item["last_updated"] = datetime.now().isoformat()
                self.save_metadata(data)
                return True
        return False

    def get_pending_documents(self):
        data = self.load_metadata()
        return [d for d in data if d["status"] == "pending"]
