"""PDF download + LangChain Document loading for the analyzer pipeline.

Phase 2 wrap-up: migrated out of the deprecated ``ingestion/`` namespace
directory. The previous file (``ingestion/pdf_loader.py``) used a local
duplicate ``MinioClient``; this version reuses the canonical
``agents.document_access.minio.MinioHandler`` so the path-guard from
Subtask F and any future MinIO-side changes flow through a single
handler.
"""

from __future__ import annotations

import json
import os
import tempfile

from langchain_community.document_loaders import PyPDFLoader

from agents.document_access.minio import MinioHandler


class IngestionPipeline:
    def __init__(self, processed_files_path: str = "processed_files.json") -> None:
        self.minio = MinioHandler()
        self.processed_files_path = processed_files_path
        self.processed_files = self._load_processed_files()

    def _load_processed_files(self) -> dict:
        if os.path.exists(self.processed_files_path):
            try:
                with open(self.processed_files_path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                return {}
        return {}

    def _save_processed_files(self) -> None:
        with open(self.processed_files_path, "w", encoding="utf-8") as fh:
            json.dump(self.processed_files, fh, indent=4)

    def get_new_files(self):
        docs = self.minio.list_documents() or []
        all_files = [d["filename"] for d in docs if d.get("filename", "").lower().endswith(".pdf")]
        return [f for f in all_files if f not in self.processed_files]

    def download_and_load(self, object_name: str):
        """Download `object_name` from MinIO to the system tempdir, load
        it via PyPDFLoader, enrich metadata, then delete the temp file.

        Returns the list of LangChain Documents on success, ``None`` on
        download failure. The local path lives under
        ``tempfile.gettempdir()`` so the path-guard in
        ``MinioHandler.download_document`` accepts the destination.
        """
        safe_name = object_name.replace("/", "_").replace("\\", "_").replace(":", "_")
        local_path = os.path.join(tempfile.gettempdir(), f"temp_{safe_name}")
        if not self.minio.download_document(object_name, local_path):
            return None

        try:
            loader = PyPDFLoader(local_path)
            docs = loader.load()
            for doc in docs:
                doc.metadata["source_path"] = object_name
                parts = object_name.split("/")
                if len(parts) > 1:
                    doc.metadata["country"] = parts[0]
                doc.metadata["filename"] = parts[-1]
            return docs
        finally:
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except OSError:
                pass

    def mark_as_processed(self, object_name: str) -> None:
        self.processed_files[object_name] = True
        self._save_processed_files()


__all__ = ["IngestionPipeline"]
