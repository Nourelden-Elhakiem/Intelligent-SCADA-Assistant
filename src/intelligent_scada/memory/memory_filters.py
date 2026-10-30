"""Small deterministic filters for optional conversation context."""

from __future__ import annotations

import re

IGNORE_CONTEXT_PATTERNS = (
    r"\bignore (?:the )?(?:previous|earlier) context\b",
    r"\bdo not use (?:the )?(?:previous|earlier) (?:messages|context)\b",
    r"\bstart (?:over|fresh)\b",
)


def requests_fresh_context(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in IGNORE_CONTEXT_PATTERNS)


def is_context_useful(text: str) -> bool:
    normalized = re.sub(r"[^\w ]", "", text.casefold(), flags=re.UNICODE).strip()
    if not normalized:
        return False
    trivial = {
        "hi",
        "hello",
        "hey",
        "thanks",
        "thank you",
        "ok",
        "okay",
        "bye",
    }
    return normalized not in trivial
