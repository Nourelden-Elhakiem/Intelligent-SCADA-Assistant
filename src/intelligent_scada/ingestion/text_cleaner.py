"""Light page-text cleaning based on the original notebook rules."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from intelligent_scada.artifacts import write_json
from intelligent_scada.contracts import CleanPage, RawPage


def is_header_footer(
    line: str,
    header_footer_patterns: Iterable[str],
    page_number_pattern: re.Pattern[str],
) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return stripped in header_footer_patterns or bool(page_number_pattern.match(stripped))


def clean_page_text(
    raw_text: str,
    *,
    header_footer_patterns: Iterable[str] = ("System Guide", "7EN02-0440-03"),
    page_number_pattern: str = r"^Page\s+\d+\s+of\s+\d+$",
) -> tuple[str, list[str]]:
    compiled_page_pattern = re.compile(page_number_pattern, re.IGNORECASE)
    kept: list[str] = []
    removed: list[str] = []

    for line in raw_text.split("\n"):
        if is_header_footer(line, header_footer_patterns, compiled_page_pattern):
            removed.append(line.strip())
        else:
            kept.append(line)

    clean_text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return clean_text, removed


def clean_pages(
    raw_pages: list[RawPage],
    output_path: Path,
    *,
    header_footer_patterns: Iterable[str] = ("System Guide", "7EN02-0440-03"),
    page_number_pattern: str = r"^Page\s+\d+\s+of\s+\d+$",
) -> list[CleanPage]:
    cleaned: list[CleanPage] = []
    for page in raw_pages:
        clean_text, removed_lines = clean_page_text(
            page["raw_text"],
            header_footer_patterns=header_footer_patterns,
            page_number_pattern=page_number_pattern,
        )
        cleaned.append(
            {
                **page,
                "clean_text": clean_text,
                "clean_char_count": len(clean_text),
                "clean_word_count": len(clean_text.split()),
                "removed_lines": removed_lines,
                "has_text": bool(clean_text.strip()),
            }
        )

    write_json(output_path, cleaned)
    return cleaned
