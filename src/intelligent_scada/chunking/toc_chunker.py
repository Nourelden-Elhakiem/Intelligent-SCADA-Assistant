"""TOC-aware text chunk construction."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from intelligent_scada.artifacts import write_json
from intelligent_scada.chunking.toc_parser import build_sections
from intelligent_scada.contracts import CleanPage, PdfStructure, TextChunk, TocSection

LOGGER = logging.getLogger(__name__)


def collect_section_text(
    section: TocSection, page_lookup: dict[int, str]
) -> tuple[str, list[int]]:
    pages_text: list[str] = []
    source_pages: list[int] = []
    for page_number in range(section["section_start_page"], section["section_end_page"] + 1):
        text = page_lookup.get(page_number, "").strip()
        if text:
            pages_text.append(text)
            source_pages.append(page_number)
    return "\n\n".join(pages_text), source_pages


@dataclass(frozen=True)
class _Part:
    text: str
    spans: list[tuple[int, int, int]]

    def cut(self, start: int, stop: int | None = None) -> _Part:
        left, right, _ = slice(start, stop).indices(len(self.text))
        return _Part(self.text[left:right], [
            (max(a, left) - left, min(b, right) - left, page)
            for a, b, page in self.spans if a < right and b > left
        ])

    def stripped(self) -> _Part:
        left = len(self.text) - len(self.text.lstrip())
        return self.cut(left, left + len(self.text.strip()))

    def split(self, separator: str) -> list[_Part]:
        offset = 0
        result = []
        for text in self.text.split(separator):
            result.append(self.cut(offset, offset + len(text)))
            offset += len(text) + len(separator)
        return result


def _join(left: _Part, right: _Part, separator: str = "\n\n") -> _Part:
    offset = len(left.text) + len(separator)
    return _Part(left.text + separator + right.text,
                 left.spans + [(a + offset, b + offset, p) for a, b, p in right.spans]).stripped()


def _legacy_split(source: _Part, maximum: int, overlap: int) -> list[_Part]:
    """Preserve the historical notebook splitting behavior exactly."""
    if len(source.text) <= maximum:
        return [source]

    paragraphs = source.split("\n\n")
    chunks: list[_Part] = []
    current = _Part("", [])
    for paragraph in paragraphs:
        if len(current.text) + len(paragraph.text) + 2 <= maximum:
            current = _join(current, paragraph)
        elif current.text:
            chunks.append(current)
            tail = current.cut(-overlap) if overlap else _Part("", [])
            current = _join(tail, paragraph) if tail.text else paragraph
        else:
            for line in paragraph.split("\n"):
                if len(current.text) + len(line.text) + 1 <= maximum:
                    current = _join(current, line, "\n")
                else:
                    if current.text:
                        chunks.append(current)
                    current = line
    if current.text.strip():
        chunks.append(current.stripped())
    return chunks


def _bounded_units(source: _Part, maximum: int, overlap: int) -> list[_Part]:
    if len(source.text) <= maximum:
        return [source]
    step = maximum - overlap
    return [source.cut(start, start + maximum) for start in range(0, len(source.text), step)]


def _targeted_split(source: _Part, target: int, maximum: int, overlap: int) -> list[_Part]:
    """Prefer paragraph boundaries near target while enforcing the maximum."""
    if len(source.text) <= maximum:
        return [source]

    units: list[_Part] = []
    for paragraph in source.split("\n\n"):
        units.extend(_bounded_units(paragraph, maximum, overlap))

    chunks: list[_Part] = []
    current = _Part("", [])
    for unit in units:
        candidate = _join(current, unit) if current.text else unit
        if current.text and (len(candidate.text) > maximum or len(current.text) >= target):
            chunks.append(current)
            tail = current.cut(-overlap) if overlap else _Part("", [])
            candidate = _join(tail, unit) if tail.text else unit
            if len(candidate.text) > maximum:
                # The unit is already bounded; drop overlap rather than exceed max.
                candidate = unit
        current = candidate
    if current.text:
        chunks.append(current)
    return chunks


def split_section_text(
    text: str,
    *,
    target: int = 2500,
    maximum: int = 3500,
    overlap: int = 200,
    strategy: Literal["legacy", "targeted"] = "legacy",
) -> list[str]:
    return [part.text for part in _split_parts(_Part(text, []), target, maximum, overlap, strategy)]


def _split_parts(
    source: _Part, target: int, maximum: int, overlap: int, strategy: str
) -> list[_Part]:
    if maximum <= 0 or target <= 0:
        raise ValueError("Chunk sizes must be positive")
    if target > maximum:
        raise ValueError("target cannot exceed maximum")
    if overlap < 0 or overlap >= maximum:
        raise ValueError("overlap must be between 0 and maximum")
    if strategy == "legacy":
        return _legacy_split(source, maximum, overlap)
    if strategy == "targeted":
        return _targeted_split(source, target, maximum, overlap)
    raise ValueError(f"Unknown chunking strategy: {strategy}")


def create_chunks(
    structure: PdfStructure,
    clean_pages: list[CleanPage],
    output_path: Path | None = None,
    *,
    target: int = 2500,
    maximum: int = 3500,
    overlap: int = 200,
    strategy: Literal["legacy", "targeted"] = "legacy",
    skip_sections: tuple[str, ...] = ("Contents",),
) -> list[TextChunk]:
    page_lookup = {page["page"]: page["clean_text"] for page in clean_pages}
    sections = build_sections(structure["toc"], structure["total_pages"])
    split_sections: list[dict[str, Any]] = []

    for section in sections:
        if section["section_title"] in skip_sections:
            continue
        text, source_pages = collect_section_text(section, page_lookup)
        if not text.strip():
            continue
        spans = []
        offset = 0
        for page in source_pages:
            end = offset + len(page_lookup[page].strip())
            spans.append((offset, end, page))
            offset = end + 2
        parts = _split_parts(_Part(text, spans), target, maximum, overlap, strategy)
        for part_index, part in enumerate(parts, start=1):
            split_sections.append(
                {
                    **section,
                    "text": part.text,
                    "source_pages": sorted({page for _, _, page in part.spans}),
                    "part_index": part_index,
                    "part_count": len(parts),
                }
            )

    chunks: list[TextChunk] = []
    for chunk_index, split_section in enumerate(split_sections):
        source_pages = split_section["source_pages"]
        section_prefix = " > ".join(split_section["section_path"])
        full_text = f"Section: {section_prefix}\n\n{split_section['text']}"
        chunks.append(
            {
                "chunk_id": f"chunk_{chunk_index:06d}",
                "chunk_index": chunk_index,
                "text": full_text,
                "char_count": len(full_text),
                "word_count": len(full_text.split()),
                "page_start": source_pages[0]
                if source_pages
                else split_section["section_start_page"],
                "page_end": source_pages[-1]
                if source_pages
                else split_section["section_end_page"],
                "source_pages": source_pages,
                "toc_level": split_section["toc_level"],
                "section_title": split_section["section_title"],
                "section_path": split_section["section_path"],
                "section_start_page": split_section["section_start_page"],
                "section_end_page": split_section["section_end_page"],
                "part_index": split_section["part_index"],
                "part_count": split_section["part_count"],
            }
        )

    if not chunks:
        raise ValueError("PDF contains no supported extractable text chunks; OCR is not supported")
    if output_path is not None:
        write_json(output_path, chunks)
    LOGGER.info("Created %s chunks with %s strategy", len(chunks), strategy)
    return chunks
