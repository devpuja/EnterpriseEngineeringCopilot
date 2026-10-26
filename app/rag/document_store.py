from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.config.settings import settings


class DocumentStore(Protocol):
    def save(self, *, tenant_id: str, document_id: str, file_name: str, content: bytes) -> str: ...


class LocalDocumentStore:
    """Local-only document storage for development. Do not use as production storage."""

    def __init__(self, root: str | Path = "data/rag_documents") -> None:
        self._root = Path(root).resolve()

    def save(self, *, tenant_id: str, document_id: str, file_name: str, content: bytes) -> str:
        safe_name = Path(file_name).name
        if safe_name != file_name or safe_name in {"", ".", ".."}:
            raise ValueError("Invalid file name.")
        destination = (self._root / tenant_id / document_id / safe_name).resolve()
        if self._root not in destination.parents:
            raise ValueError("Invalid document storage path.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return str(destination)


class AzureBlobDocumentStore:
    def __init__(self) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        account_url = settings.azure_storage_account_url.strip()
        container_name = settings.azure_storage_container.strip()
        connection_string = settings.azure_storage_connection_string.strip()
        if connection_string:
            self._service = BlobServiceClient.from_connection_string(connection_string)
        elif account_url:
            self._service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
        else:
            raise RuntimeError(
                "Set AZURE_STORAGE_ACCOUNT_URL (recommended with managed identity) "
                "or AZURE_STORAGE_CONNECTION_STRING."
            )
        self._container = self._service.get_container_client(container_name)
        try:
            self._container.create_container()
        except Exception as exc:
            # ContainerAlreadyExists is expected on subsequent starts; avoid hiding other errors.
            if getattr(exc, "error_code", None) != "ContainerAlreadyExists":
                raise

    def save(self, *, tenant_id: str, document_id: str, file_name: str, content: bytes) -> str:
        safe_name = Path(file_name).name
        if safe_name != file_name or safe_name in {"", ".", ".."}:
            raise ValueError("Invalid file name.")
        blob_name = f"{tenant_id}/{document_id}/{safe_name}"
        self._container.upload_blob(name=blob_name, data=content, overwrite=True)
        return f"azure-blob://{self._container.container_name}/{blob_name}"
