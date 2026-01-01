from minio import Minio
from minio.error import S3Error
import os
import yaml

class MinioHandler:
    def __init__(self, config_path="configs/config.yaml"):
        # Load config
        try:
            with open(config_path, "r") as f:
                self.config = yaml.safe_load(f).get("minio", {})
        except Exception:
            self.config = {}

        self.endpoint = self.config.get("endpoint", "localhost:9000")
        self.access_key = self.config.get("access_key", "minioadmin")
        self.secret_key = self.config.get("secret_key", "minioadmin")
        self.bucket_name = self.config.get("bucket_name", "regulations")
        self.secure = self.config.get("secure", False)

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
        except Exception as e:
            print(f"MinIO Connection Error: {e}")

    def list_documents(self):
        """List all documents in the bucket with metadata."""
        try:
            objects = self.client.list_objects(self.bucket_name, recursive=True)
            docs = []
            for obj in objects:
                docs.append({
                    "filename": obj.object_name,
                    "size": obj.size,
                    "last_modified": str(obj.last_modified)
                })
            return docs
        except Exception as e:
            return {"error": str(e)}

    def download_document(self, object_name, local_path):
        try:
            self.client.fget_object(self.bucket_name, object_name, local_path)
            return True
        except Exception as e:
            print(f"Download Error: {e}")
            return False
