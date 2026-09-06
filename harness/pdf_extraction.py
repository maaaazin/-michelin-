"""Deterministic PDF-to-text extraction via PyMuPDF. No LLM calls - just
pulls raw text for the Contract Analyst agent to read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pymupdf


def extract_text_from_pdf(path: Union[str, Path]) -> str:
    """Extract all text from a PDF, page by page, in reading order."""
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)
