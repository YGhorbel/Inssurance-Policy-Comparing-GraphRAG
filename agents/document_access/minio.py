from minio import Minio
from minio.error import S3Error
import os
import yaml
from urllib.parse import urlparse

class MinioHandler:
    def __init__(self, config_path="configs/config.yaml"):
        # Load config
        try:
            with open(config_path, "r") as f:
                self.config = yaml.safe_load(f).get("minio", {})
        except Exception:
            self.config = {}

        # Allow environment variable overrides (useful when console runs on 9001 but API on 9000
        # or when docker remaps ports). Order of precedence: env var -> config file -> defaults.
        raw_endpoint = os.environ.get("MINIO_ENDPOINT") or self.config.get("endpoint", "localhost:9000")
        # Normalize endpoint: accept values like
        # - "localhost:9000"
        # - "http://localhost:9000"
        # - "https://example.com:9000/some/path"
        # and strip any path components (e.g. /browser/regulations) so Minio client receives host[:port].
        try:
            if isinstance(raw_endpoint, str) and raw_endpoint.startswith(("http://", "https://")):
                parsed = urlparse(raw_endpoint)
            else:
                # urlparse treats 'host:port' as path, so prepend '//' to parse netloc
                parsed = urlparse("//" + str(raw_endpoint))
            netloc = parsed.netloc or parsed.path
            # If there are leftover path pieces in netloc, split them off
            if "/" in netloc:
                netloc = netloc.split("/")[0]
            endpoint = netloc if netloc else "localhost:9000"
        except Exception:
            endpoint = "localhost:9000"
        self.endpoint = endpoint
        self.access_key = os.environ.get("MINIO_ACCESS_KEY") or self.config.get("access_key", "minioadmin")
        self.secret_key = os.environ.get("MINIO_SECRET_KEY") or self.config.get("secret_key", "minioadmin")
        self.bucket_name = os.environ.get("MINIO_BUCKET") or self.config.get("bucket_name", "regulations")
        # allow env var values like 'true'/'false' or '1'/'0'
        env_secure = os.environ.get("MINIO_SECURE")
        if env_secure is not None:
            self.secure = str(env_secure).lower() in ("1", "true", "yes")
        else:
            # If endpoint was provided with https scheme infer secure unless config explicitly sets it
            if isinstance(raw_endpoint, str) and raw_endpoint.lower().startswith("https://"):
                self.secure = True
            else:
                self.secure = self.config.get("secure", False)

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )
        # If user accidentally provided a console URL (e.g. containing '/browser'), warn once
        if isinstance(raw_endpoint, str) and "/browser" in raw_endpoint:
            print("Warning: MINIO endpoint appears to contain '/browser' (MinIO console URL). Using sanitized API endpoint:", self.endpoint)
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
            # Print error and return None so callers can keep existing metadata instead of
            # overwriting it with an empty list on transient failures.
            print(f"MinIO list_documents error: {e}")
            return None

    def download_document(self, object_name, local_path):
        try:
            self.client.fget_object(self.bucket_name, object_name, local_path)
            return True
        except Exception as e:
            print(f"Download Error: {e}")
            return False
