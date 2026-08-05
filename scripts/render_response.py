#!/usr/bin/env python3
"""Render verified Reading Mirror materials into consistent output formats."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

from common import data_home, iter_record_blocks


FALLBACK = (
    "我没有在你现有的微信读书划线和笔记中找到足以回应这段困惑的内容。\n"
    "我不会为了完成格式而勉强引用关系很弱的句子。"
)


def blockquote_markdown(value: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in value.split("\n"))


def lines_html(value: str) -> str:
    """Render UTF-8 text as explicit Apple Notes-friendly div paragraphs."""
    return "".join(f"<div>{html.escape(line) if line else '<br>'}</div>" for line in value.split("\n"))


def blockquote_html(value: str) -> str:
    return f"<blockquote>{lines_html(value)}</blockquote>"


def citation_block_markdown(quote: str, source: str) -> str:
    """Keep the verified quotation and its source in one semantic quote block."""
    return blockquote_markdown(f"{quote}\n{source}")


def citation_block_html(quote: str, source: str) -> str:
    """Keep the verified quotation and its source in one Notes-formatting unit."""
    return blockquote_html(f"{quote}\n{source}")


def source_line(material: dict[str, Any]) -> str:
    book = str(material.get("book", "")).strip()
    if not book:
        raise ValueError("Every material requires a verified book title")
    parts = [f"——《{book}》"]
    author = str(material.get("author", "")).strip()
    chapter = str(material.get("chapter", "")).strip()
    if author:
        parts.append(author)
    if chapter:
        parts.append(f"〈{chapter}〉")
    return "，".join(parts)


def require_text(material: dict[str, Any], key: str, *, preserve: bool = False) -> str:
    value = material.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"material.{key} must be a non-empty string")
    return value if preserve else value.strip()


def load_record_index(books_dir: Path) -> dict[str, dict[str, Any]]:
    if not books_dir.is_dir():
        raise ValueError(f"Mirror books directory does not exist: {books_dir}")
    index: dict[str, dict[str, Any]] = {}
    for path in sorted(books_dir.glob("*.md")):
        for block in iter_record_blocks(path.read_text(encoding="utf-8")):
            record = block["record"]
            record_id = record.get("record_id")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"Mirror record in {path} is missing record_id")
            if record_id in index:
                raise ValueError(f"Duplicate mirror record_id: {record_id}")
            index[record_id] = record
    return index


def resolve_material(specification: dict[str, Any], record_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for forbidden in ("quote", "historical_note", "book", "author", "chapter"):
        if forbidden in specification:
            raise ValueError(f"material.{forbidden} must come from the mirror record, not input text")
    record_id = specification.get("record_id")
    if not isinstance(record_id, str) or not record_id:
        raise ValueError("Each material requires record_id")
    record = record_index.get(record_id)
    if record is None:
        raise ValueError(f"Mirror record was not found: {record_id}")

    explanation = require_text(specification, "explanation")
    book = record.get("title")
    if not isinstance(book, str) or not book.strip():
        raise ValueError(f"Mirror record {record_id} has no verified book title")
    record_type = record.get("record_type")
    material: dict[str, Any] = {
        "book": book,
        "author": record.get("author") if isinstance(record.get("author"), str) else "",
        "chapter": record.get("chapter") if isinstance(record.get("chapter"), str) else "",
        "explanation": explanation,
    }

    if record_type in {"highlight_only", "highlight_with_note"}:
        quote = record.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError(f"Mirror record {record_id} has no verified quotation")
        material["quote"] = quote
        notes = record.get("user_notes", [])
        if not isinstance(notes, list):
            raise ValueError(f"Mirror record {record_id} has invalid user_notes")
        requested_review_id = specification.get("review_id")
        selected_notes = [note for note in notes if isinstance(note, dict) and isinstance(note.get("content"), str)]
        if requested_review_id not in (None, ""):
            selected_notes = [
                note for note in selected_notes if str(note.get("review_id")) == str(requested_review_id)
            ]
            if len(selected_notes) != 1:
                raise ValueError(f"review_id is not uniquely linked to mirror record {record_id}")
        elif len(selected_notes) > 1:
            raise ValueError(f"Mirror record {record_id} has multiple annotations; specify review_id")
        if selected_notes:
            material["historical_note"] = selected_notes[0]["content"]
    elif record_type in {"chapter_comment", "book_review"}:
        note = record.get("user_note")
        if not isinstance(note, str) or not note.strip():
            raise ValueError(f"Mirror record {record_id} has no verified personal note")
        material["historical_note"] = note
    else:
        raise ValueError(f"Unsupported mirror record_type for {record_id}: {record_type}")
    return material


def render(payload: dict[str, Any], record_index: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    materials = payload.get("materials", [])
    if not isinstance(materials, list):
        raise ValueError("materials must be a list")
    if not materials:
        return {
            "markdown": FALLBACK,
            "html": lines_html(FALLBACK),
            "plaintext": FALLBACK,
            "quote_blocks": [],
        }
    if record_index is None:
        record_index = load_record_index(data_home() / "mirror" / "books")

    markdown_sections: list[str] = []
    html_sections: list[str] = []
    plaintext_sections: list[str] = []
    quote_blocks: list[dict[str, str]] = []

    seen_record_ids: set[str] = set()
    for specification in materials:
        if not isinstance(specification, dict):
            raise ValueError("Each material must be an object")
        record_id = specification.get("record_id")
        if isinstance(record_id, str) and record_id in seen_record_ids:
            raise ValueError(f"Duplicate material record_id: {record_id}")
        if isinstance(record_id, str):
            seen_record_ids.add(record_id)
        material = resolve_material(specification, record_index)
        explanation = require_text(material, "explanation")
        quote = material.get("quote")
        historical_note = material.get("historical_note")

        if isinstance(quote, str) and quote.strip():
            source = source_line(material)
            citation_plaintext = f"{quote}\n{source}"
            md = [citation_block_markdown(quote, source)]
            hs = [citation_block_html(quote, source)]
            ps = [quote, source]
            quote_blocks.append(
                {
                    "record_id": str(record_id),
                    "plaintext": citation_plaintext,
                }
            )
            if isinstance(historical_note, str) and historical_note.strip():
                note = historical_note
                md.extend(["**你当时的想法**", blockquote_markdown(note)])
                hs.extend(["<div><strong>你当时的想法</strong></div>", blockquote_html(note)])
                ps.extend(["你当时的想法", note])
            md.extend(["**我的解释**", explanation])
            hs.extend(
                ["<div><strong>我的解释</strong></div>", lines_html(explanation)]
            )
            ps.extend(["我的解释", explanation])
        else:
            note = require_text(material, "historical_note", preserve=True)
            book = str(material.get("book", "")).strip()
            if not book:
                raise ValueError("Unlinked historical notes require a verified book title")
            label = f"你当时在《{book}》中写下"
            md = [f"**{label}**", blockquote_markdown(note), "**我的解释**", explanation]
            hs = [
                f"<div><strong>{html.escape(label)}</strong></div>",
                blockquote_html(note),
                "<div><strong>我的解释</strong></div>",
                lines_html(explanation),
            ]
            ps = [label, note, "我的解释", explanation]

        markdown_sections.append("\n\n".join(md))
        html_sections.append("".join(hs))
        plaintext_sections.append("\n".join(ps))

    overall = payload.get("overall")
    if isinstance(overall, str) and overall.strip():
        overall = overall.strip()
        markdown_sections.append(f"**我的整体理解**\n\n{overall}")
        html_sections.append(
            "<div><strong>我的整体理解</strong></div>"
            f"{lines_html(overall)}"
        )
        plaintext_sections.append(f"我的整体理解\n{overall}")

    return {
        "markdown": "\n\n".join(markdown_sections),
        "html": "<br><br>".join(html_sections),
        "plaintext": "\n\n".join(plaintext_sections),
        "quote_blocks": quote_blocks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--books-dir", type=Path, default=None)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be one JSON object")
        record_index = None
        if payload.get("materials"):
            books_dir = (args.books_dir or (data_home() / "mirror" / "books")).expanduser().resolve()
            record_index = load_record_index(books_dir)
        print(json.dumps(render(payload, record_index), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
