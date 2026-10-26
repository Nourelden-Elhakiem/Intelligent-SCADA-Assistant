"""Typed definitions for stable JSON and service contracts.

The field names intentionally match the original notebook artifacts.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class ImageRecord(TypedDict):
    filename: str
    page: int
    img_index: int
    xref: int
    width: int
    height: int
    source_ext: str
    file_size_bytes: int
    md5: str


class FilteredImageRecord(ImageRecord):
    decision: Literal["keep", "discard", "missing"]
    reasons: NotRequired[list[str]]
    source: NotRequired[str]


class TocEntry(TypedDict):
    level: int
    title: str
    page: int


class PageStats(TypedDict):
    page: int
    char_count: int
    line_count: int
    first_line: str
    last_line: str
    is_empty: bool


class PdfStructure(TypedDict):
    total_pages: int
    toc_entries: int
    toc: list[TocEntry]
    empty_pages: list[int]
    page_stats: list[PageStats]
    heading_candidates_count: int


class RawPage(TypedDict):
    page: int
    raw_text: str
    raw_char_count: int
    raw_word_count: int


class CleanPage(RawPage):
    clean_text: str
    clean_char_count: int
    clean_word_count: int
    removed_lines: list[str]
    has_text: bool


class TocSection(TypedDict):
    toc_index: int
    toc_level: int
    section_title: str
    section_path: list[str]
    section_start_page: int
    section_end_page: int


class TextChunk(TypedDict):
    chunk_id: str
    chunk_index: int
    text: str
    char_count: int
    word_count: int
    page_start: int
    page_end: int
    source_pages: list[int]
    toc_level: int
    section_title: str
    section_path: list[str]
    section_start_page: int
    section_end_page: int
    part_index: int
    part_count: int


class LinkedImage(TypedDict):
    filename: str
    page: int
    width: int
    height: int
    file_size_bytes: int


class ChunkImageLink(TypedDict):
    chunk_id: str
    section_title: str
    section_path: list[str]
    page_start: int
    page_end: int
    source_pages: list[int]
    image_count: int
    images: list[LinkedImage]


class EmbeddingMetadata(TypedDict):
    chunk_id: str
    chunk_index: int
    char_count: int
    word_count: int
    page_start: int
    page_end: int
    source_pages: list[int]
    toc_level: int
    section_title: str
    section_path: list[str]
    part_index: int
    part_count: int


class RetrievalResult(TypedDict):
    chunk_id: str
    text: str
    page_start: int
    page_end: int
    source_pages: list[int]
    section_title: str
    section_path: list[str]
    score: float


class Citation(TypedDict):
    source_id: str
    chunk_id: str
    label: str
    page_start: int
    page_end: int
    section_path: list[str]


class AnswerResponse(TypedDict):
    answer: str
    citations: list[Citation]
    sources: list[RetrievalResult]
    related_images: list[LinkedImage]
    session_id: str | None
    routing: dict[str, object]
