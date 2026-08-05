#!/usr/bin/env python3
"""Prepare a complete, last-to-first replacement of Reading Mirror markers."""

from __future__ import annotations

import json
import sys
from typing import Any

from marker_logic import DEFAULT_MARKER, analyze_markers


class MarkerReplacementError(ValueError):
    pass


def _positions(text: str, marker: str) -> list[int]:
    positions: list[int] = []
    cursor = 0
    while True:
        offset = text.find(marker, cursor)
        if offset < 0:
            return positions
        positions.append(offset)
        cursor = offset + len(marker)


def prepare_marker_replacement(
    *, body_html: str, plaintext: str, marker: str, replacements: list[dict[str, Any]]
) -> dict[str, Any]:
    """Validate every marker identity and replace all occurrences from the end."""
    if not marker:
        raise MarkerReplacementError("marker must be a non-empty string")
    markers = analyze_markers(plaintext, marker)
    if not markers:
        raise MarkerReplacementError("No exact markers remain in the Apple Note")
    if len(replacements) != len(markers):
        raise MarkerReplacementError("Every marker must have exactly one replacement")

    html_positions = _positions(body_html, marker)
    text_positions = _positions(plaintext, marker)
    if len(html_positions) != len(markers) or len(text_positions) != len(markers):
        raise MarkerReplacementError(
            "Marker positions cannot be represented safely in Notes HTML; use the UI fallback"
        )

    by_index: dict[int, dict[str, Any]] = {}
    for replacement in replacements:
        if not isinstance(replacement, dict) or not isinstance(replacement.get("marker_index"), int):
            raise MarkerReplacementError("Each replacement requires an integer marker_index")
        marker_index = replacement["marker_index"]
        if marker_index in by_index:
            raise MarkerReplacementError(f"Duplicate marker_index: {marker_index}")
        by_index[marker_index] = replacement
    if sorted(by_index) != list(range(1, len(markers) + 1)):
        raise MarkerReplacementError("Replacement marker indexes must cover every marker in order")

    validated: list[tuple[str, str]] = []
    for marker_info in markers:
        marker_index = marker_info["marker_index"]
        replacement = by_index[marker_index]
        if replacement.get("preceding_context_hash") != marker_info["preceding_context_hash"]:
            raise MarkerReplacementError(f"Marker {marker_index} preceding context changed")
        content_html = replacement.get("content_html")
        content_plaintext = replacement.get("content_plaintext")
        if not isinstance(content_html, str) or not content_html.strip():
            raise MarkerReplacementError(f"Marker {marker_index} requires non-empty content_html")
        if not isinstance(content_plaintext, str) or not content_plaintext.strip():
            raise MarkerReplacementError(f"Marker {marker_index} requires non-empty content_plaintext")
        if marker in content_html or marker in content_plaintext:
            raise MarkerReplacementError(f"Marker {marker_index} replacement must not contain the marker literal")
        validated.append((content_html, content_plaintext))

    new_body = body_html
    new_plaintext = plaintext
    for zero_index in range(len(markers) - 1, -1, -1):
        html_offset = html_positions[zero_index]
        text_offset = text_positions[zero_index]
        content_html, content_plaintext = validated[zero_index]
        new_body = new_body[:html_offset] + content_html + new_body[html_offset + len(marker) :]
        new_plaintext = (
            new_plaintext[:text_offset] + content_plaintext + new_plaintext[text_offset + len(marker) :]
        )

    if marker in new_body or marker in new_plaintext:
        raise MarkerReplacementError("At least one target marker remains after replacement")
    return {
        "body_html": new_body,
        "plaintext": new_plaintext,
        "verification_texts": [item[1] for item in validated],
        "marker_count": len(markers),
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise MarkerReplacementError("Input must be one JSON object")
        body_html = payload.get("body_html")
        plaintext = payload.get("plaintext")
        replacements = payload.get("replacements")
        marker = payload.get("marker", DEFAULT_MARKER)
        if not isinstance(body_html, str) or not isinstance(plaintext, str):
            raise MarkerReplacementError("body_html and plaintext must be strings")
        if not isinstance(replacements, list):
            raise MarkerReplacementError("replacements must be a list")
        if not isinstance(marker, str):
            raise MarkerReplacementError("marker must be a string")
        result = prepare_marker_replacement(
            body_html=body_html,
            plaintext=plaintext,
            marker=marker,
            replacements=replacements,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (MarkerReplacementError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
