from __future__ import annotations


def chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    """Split text into deterministic character windows with overlap.

    This baseline is deliberately simple and testable. Phase 3.4 can replace it
    with layout/semantic-aware chunking while preserving the chunk interface.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    normalized = "\n".join(line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    normalized = normalized.strip()
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    length = len(normalized)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            # Prefer a paragraph/newline/space boundary if it is reasonably close.
            boundary = max(normalized.rfind("\n", start, end), normalized.rfind(" ", start, end))
            if boundary > start + int(chunk_size * 0.6):
                end = boundary
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks
