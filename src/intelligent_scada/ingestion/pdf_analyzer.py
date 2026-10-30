"""Explore and serialize the structural properties of a PDF manual."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import fitz

from intelligent_scada.artifacts import write_json
from intelligent_scada.contracts import PageStats, PdfStructure, TocEntry

LOGGER = logging.getLogger(__name__)

DEFAULT_HEADING_PATTERN = re.compile(
    r"^(?:\d+[\.\d]*\s+[A-Z]|Chapter\s+\d+|CHAPTER\s+\d+|[A-Z][A-Z\s]{4,}$)"
)


def analyze_pdf(
    pdf_path: Path,
    output_path: Path,
    *,
    heading_pattern: re.Pattern[str] = DEFAULT_HEADING_PATTERN,
) -> PdfStructure:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    page_stats: list[PageStats] = []
    heading_candidates_count = 0

    with fitz.open(pdf_path) as document:
        toc: list[TocEntry] = [
            {"level": level, "title": title, "page": page}
            for level, title, page in document.get_toc(simple=True)
        ]
        for index in range(document.page_count):
            text = document[index].get_text("text")
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            heading_candidates_count += sum(
                bool(heading_pattern.match(line)) for line in lines[:10]
            )
            page_stats.append(
                {
                    "page": index + 1,
                    "char_count": len(text),
                    "line_count": len(lines),
                    "first_line": lines[0] if lines else "",
                    "last_line": lines[-1] if lines else "",
                    "is_empty": not text.strip(),
                }
            )

        structure: PdfStructure = {
            "total_pages": document.page_count,
            "toc_entries": len(toc),
            "toc": toc,
            "empty_pages": [item["page"] for item in page_stats if item["is_empty"]],
            "page_stats": page_stats,
            "heading_candidates_count": heading_candidates_count,
        }

    write_json(output_path, structure)
    LOGGER.info(
        "Analyzed %s pages with %s TOC entries",
        structure["total_pages"],
        structure["toc_entries"],
    )
    return structure
