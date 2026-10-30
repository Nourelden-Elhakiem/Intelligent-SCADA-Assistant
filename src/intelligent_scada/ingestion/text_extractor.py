"""Extract raw page-level text from PDF manuals."""

from __future__ import annotations

import logging
from pathlib import Path

import fitz

from intelligent_scada.artifacts import write_json
from intelligent_scada.contracts import RawPage

LOGGER = logging.getLogger(__name__)


def extract_page_text(pdf_path: Path, output_path: Path) -> list[RawPage]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages: list[RawPage] = []
    with fitz.open(pdf_path) as document:
        for index in range(document.page_count):
            text = document[index].get_text("text")
            pages.append(
                {
                    "page": index + 1,
                    "raw_text": text,
                    "raw_char_count": len(text),
                    "raw_word_count": len(text.split()),
                }
            )

    write_json(output_path, pages)
    LOGGER.info("Extracted raw text from %s pages", len(pages))
    return pages
