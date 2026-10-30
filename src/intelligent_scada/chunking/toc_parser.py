"""Convert flat PDF TOC entries into hierarchical section records."""

from __future__ import annotations

from intelligent_scada.contracts import TocEntry, TocSection


def build_sections(toc: list[TocEntry], total_pages: int) -> list[TocSection]:
    """Build the same page-level section boundaries used by notebook 04."""
    if total_pages <= 0 or not toc:
        raise ValueError("PDF requires a usable table of contents (bookmarks); no-TOC PDFs are unsupported")
    sections: list[TocSection] = []
    path_stack: dict[int, str] = {}

    for index, entry in enumerate(toc):
        level = entry["level"]
        title = entry["title"].strip()
        if not title:
            raise ValueError(f"TOC title is empty at index {index}")
        start_page = entry["page"]
        if level < 1:
            raise ValueError(f"TOC level must be positive at index {index}")
        if start_page < 1 or start_page > total_pages:
            raise ValueError(f"TOC page out of range at index {index}: {start_page}")

        path_stack[level] = title
        path_stack = {key: value for key, value in path_stack.items() if key <= level}
        section_path = [path_stack[key] for key in sorted(path_stack)]

        if index + 1 < len(toc):
            end_page = toc[index + 1]["page"] - 1
            if end_page < start_page:
                end_page = start_page
        else:
            end_page = total_pages

        sections.append(
            {
                "toc_index": index,
                "toc_level": level,
                "section_title": title,
                "section_path": section_path,
                "section_start_page": start_page,
                "section_end_page": end_page,
            }
        )

    return sections
