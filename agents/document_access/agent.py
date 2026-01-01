from core.mcp.handler import mcp_registry
from agents.document_access.minio import MinioHandler
from agents.document_access.metadata import MetadataManager
import pypdf

minio = MinioHandler()
metadata_mgr = MetadataManager()

# --- MCP Tools ---

async def list_available_documents() -> list:
    """
    List all regulatory documents available in MinIO.
    Returns a list of file metadata.
    """
    return minio.list_documents()

async def get_document_path(filename: str) -> str:
    """
    Download a specific document to a temp path and return it.
    """
    import os
    local_path = f"temp_{os.path.basename(filename)}"
    if minio.download_document(filename, local_path):
        return local_path
    return ""

async def sync_metadata() -> list:
    """Sync metadata with MinIO and return current list."""
    return metadata_mgr.sync_with_minio()

async def update_doc_metadata(doc_id: str, updates: dict) -> bool:
    """Update metadata for a specific document."""
    return metadata_mgr.update_document(doc_id, updates)

async def list_metadata() -> list:
    """List all document metadata."""
    return metadata_mgr.load_metadata()

async def read_document_text(file_path: str) -> str:
    """Read text content from a PDF file."""
    try:
        reader = pypdf.PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
        return ""

# Register tools
mcp_registry.register_tool("list_documents", list_available_documents)
mcp_registry.register_tool("get_document_content", get_document_path)
mcp_registry.register_tool("read_document_text", read_document_text) # New
mcp_registry.register_tool("sync_metadata", sync_metadata)
mcp_registry.register_tool("update_doc_metadata", update_doc_metadata)
mcp_registry.register_tool("list_metadata", list_metadata)

print("Document Access Agent initialized.")
