"""Deterministic PDF-to-text extraction via PyMuPDF. No LLM calls - just
pulls raw text for the Contract Analyst agent to read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pymupdf


def extract_text_from_pdf(source: Union[str, Path, bytes]) -> str:
    """Extract all text from a PDF, page by page, in reading order.

    Accepts a file path, or raw PDF bytes (e.g. Streamlit's
    UploadedFile.getvalue()) opened via PyMuPDF's in-memory stream API -
    this avoids any temp-file round-trip for uploads, and with it the
    Windows-specific file-locking issues that come from writing a temp
    file and reopening it through a second handle.
    """
    if isinstance(source, (bytes, bytearray)):
        with pymupdf.open(stream=source, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)
    with pymupdf.open(source) as doc:
        return "\n".join(page.get_text() for page in doc)
