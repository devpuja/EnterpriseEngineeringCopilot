import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


SUPPORTED_MEDIA_TYPES = {"application/pdf", "text/plain"}


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    page_number: int | None = None


class DocumentIngestionError(ValueError):
    pass


class UnsupportedFileError(DocumentIngestionError):
    pass


class FileTooLargeError(DocumentIngestionError):
    pass


def safe_filename(filename: str) -> str:
    if not filename or filename.strip() == "":
        raise DocumentIngestionError("Filename is required.")
    name = Path(filename).name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    if not name or name in {".", ".."}:
        raise DocumentIngestionError("Filename is unsafe.")
    return name[:255]


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def split_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    if chunk_size < 100:
        raise ValueError("Chunk size must be at least 100.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunk overlap must be non-negative and smaller than chunk size.")
    text = normalize_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        requested_end = min(start + chunk_size, len(text))
        end = requested_end
        if requested_end < len(text):
            newline_positions = [
                position
                for position in range(max(start, requested_end - 200), requested_end)
                if text[position] == "\n"
            ]
            if newline_positions:
                end = newline_positions[-1]
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def stable_document_id(filename: str, content: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(filename.encode("utf-8", errors="replace"))
    digest.update(b"\0")
    digest.update(content)
    return digest.hexdigest()


def stable_chunk_id(document_id: str, chunk_index: int) -> str:
    return hashlib.sha256(f"{document_id}:{chunk_index}".encode()).hexdigest()


def extract_pdf(content: bytes) -> list[tuple[int, str]]:
    from io import BytesIO
    try:
        reader = PdfReader(BytesIO(content))
        pages: list[tuple[int, str]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                raise DocumentIngestionError(
                    f"Could not extract PDF page {page_number}: {exc}"
                ) from exc
            normalized = normalize_text(page_text)
            if normalized:
                pages.append((page_number, normalized))
        if not pages:
            raise DocumentIngestionError("The PDF contains no extractable text.")
        return pages
    except PdfReadError as exc:
        raise DocumentIngestionError("The file is not a valid readable PDF.") from exc


def extract_txt(content: bytes) -> list[tuple[int | None, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentIngestionError("The TXT file must use UTF-8 encoding.") from exc
    normalized = normalize_text(text)
    if not normalized:
        raise DocumentIngestionError("The TXT file contains no readable text.")
    return [(None, normalized)]


def ingest_document(
    filename: str,
    media_type: str,
    content: bytes,
    chunk_size: int,
    overlap: int,
) -> tuple[str, list[DocumentChunk]]:
    filename = safe_filename(filename)
    if media_type == "application/pdf" or filename.lower().endswith(".pdf"):
        extracted = extract_pdf(content)
    elif media_type == "text/plain" or filename.lower().endswith(".txt"):
        extracted = extract_txt(content)
    else:
        raise DocumentIngestionError("Unsupported file type. Upload a PDF or TXT file.")

    document_id = stable_document_id(filename, content)
    chunks: list[DocumentChunk] = []
    for page_number, page_text in extracted:
        for page_chunk in split_text(page_text, chunk_size, overlap):
            index = len(chunks)
            chunks.append(
                DocumentChunk(
                    chunk_id=stable_chunk_id(document_id, index),
                    document_id=document_id,
                    filename=filename,
                    chunk_index=index,
                    text=page_chunk,
                    page_number=page_number,
                )
            )
    if not chunks:
        raise DocumentIngestionError("Document extraction produced no usable chunks.")
    return document_id, chunks
