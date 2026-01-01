from minio import Minio
from minio.error import S3Error
import os
import yaml

class MinioClient:
    def __init__(self, config_path="configs/config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)["minio"]
        
        self.client = Minio(
            self.config["endpoint"],
            access_key=self.config["access_key"],
            secret_key=self.config["secret_key"],
            secure=self.config["secure"]
        )
        self.bucket_name = self.config["bucket_name"]
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)

    def list_pdf_files(self):
        """List all PDF files in the bucket recursively."""
        pdf_files = []
        objects = self.client.list_objects(self.bucket_name, recursive=True)
        for obj in objects:
            if obj.object_name.endswith('.pdf'):
                pdf_files.append(obj.object_name)
        return pdf_files

    def download_file(self, object_name, file_path):
        """Download a file from MinIO to local path."""
        try:
            self.client.fget_object(self.bucket_name, object_name, file_path)
            return True
        except S3Error as e:
            print(f"Error downloading {object_name}: {e}")
            return False
