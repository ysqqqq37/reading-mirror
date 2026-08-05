#!/usr/bin/env python3
"""Deterministic marker discovery and preceding-context identities."""

from __future__ import annotations

import re
from typing import Any

from common import normalize_text, sha256_text


DEFAULT_MARKER = "（用我读过的书回答）"
BOUNDARY_LINE = re.compile(r"(?m)^(?:#{1,6}\s+.+|\s*(?:-{3,}|\*{3,}|_{3,})\s*)$")


def analyze_markers(text: str, marker: str = DEFAULT_MARKER) -> list[dict[str, Any]]:
    if not marker:
        raise ValueError("marker cannot be empty")

    offsets: list[int] = []
    cursor = 0
    while True:
        offset = text.find(marker, cursor)
        if offset < 0:
            break
        offsets.append(offset)
        cursor = offset + len(marker)

    results: list[dict[str, Any]] = []
    previous_marker_end = 0
    for marker_index, offset in enumerate(offsets, start=1):
        search_region = text[previous_marker_end:offset]
        context_start = previous_marker_end
        for match in BOUNDARY_LINE.finditer(search_region):
            candidate = previous_marker_end + match.start()
            context_start = candidate

        context = text[context_start:offset].strip()
        normalized = normalize_text(context)
        results.append(
            {
                "marker_index": marker_index,
                "character_offset": offset,
                "preceding_context_start": context_start,
                "preceding_context": context,
                "preceding_context_hash": sha256_text(normalized),
            }
        )
        previous_marker_end = offset + len(marker)
    return results
