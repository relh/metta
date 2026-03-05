from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=256)
def _compiled_keyword_pattern(keyword: str) -> re.Pattern[str]:
    normalized_keyword = keyword.strip().lower()
    escaped_keyword = re.escape(normalized_keyword).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![a-z0-9_]){escaped_keyword}(?![a-z0-9_])")


def contains_keyword(text: str, keyword: str) -> bool:
    if not text or not keyword.strip():
        return False
    return _compiled_keyword_pattern(keyword).search(text.lower()) is not None


def count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if contains_keyword(text, keyword))


def matching_keywords(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if contains_keyword(text, keyword)]
