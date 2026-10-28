import sqlite3
import threading
from pathlib import Path
from typing import Any


class DocumentRepository:
    def __init__(self, database_path: str) -> None:
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._database_path = str(path)
        self._lock = threading.Lock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def upsert(self, record: dict[str, Any]) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO documents
                    (document_id, filename, media_type, size_bytes, chunk_count,
                     status, error, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(document_id) DO UPDATE SET
                        filename=excluded.filename,
                        media_type=excluded.media_type,
                        size_bytes=excluded.size_bytes,
                        chunk_count=excluded.chunk_count,
                        status=excluded.status,
                        error=excluded.error,
                        updated_at=excluded.updated_at
                    """,
                    (
                        record["document_id"], record["filename"], record["media_type"],
                        record["size_bytes"], record["chunk_count"], record["status"],
                        record.get("error"), record["created_at"], record["updated_at"],
                    ),
                )

    def get(self, document_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
            return dict(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM documents ORDER BY updated_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def delete(self, document_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM documents WHERE document_id = ?", (document_id,)
            )
            return cursor.rowcount > 0
