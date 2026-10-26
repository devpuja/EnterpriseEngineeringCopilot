from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader


def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, int]:
    """Extract selectable text from a PDF. OCR is intentionally handled later."""
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[Page {page_number}]\n{text}")
    except Exception as exc:
        raise ValueError("The uploaded file is not a readable PDF.") from exc

    full_text = "\n\n".join(pages).strip()
    if not full_text:
        raise ValueError(
            "No selectable text was found in this PDF. Scanned PDFs require OCR; "
            "OCR integration is planned for Phase 3.4."
        )
    return full_text, len(reader.pages)
