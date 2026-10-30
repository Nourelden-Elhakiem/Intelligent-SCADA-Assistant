"""Stable citation labels for retrieved manual sections."""

from __future__ import annotations

import re

from intelligent_scada.contracts import Citation, RetrievalResult


def page_label(page_start: int, page_end: int) -> str:
    return f"p. {page_start}" if page_start == page_end else f"pp. {page_start}-{page_end}"


def format_citation(result: RetrievalResult) -> str:
    path = " > ".join(result["section_path"]) or result["section_title"]
    return f"{path} — {page_label(result['page_start'], result['page_end'])}"


def build_citations(results: list[RetrievalResult]) -> list[Citation]:
    return [
        {
            "source_id": f"S{index}",
            "chunk_id": result["chunk_id"],
            "label": format_citation(result),
            "page_start": result["page_start"],
            "page_end": result["page_end"],
            "section_path": result["section_path"],
        }
        for index, result in enumerate(results, start=1)
    ]


class CitationValidationError(ValueError):
    """The answer cites a source marker outside its supplied evidence map."""


def used_citations(answer: str, results: list[RetrievalResult]) -> list[Citation]:
    groups = re.findall(r"\[((?:S\d+)(?:\s*,\s*S\d+)*)\]", answer)
    markers = {marker.strip() for group in groups for marker in group.split(",")}
    citations = build_citations(results)
    if markers - {citation["source_id"] for citation in citations}:
        raise CitationValidationError("Answer contains an unknown source marker")
    return [citation for citation in citations if citation["source_id"] in markers]
