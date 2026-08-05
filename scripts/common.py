#!/usr/bin/env python3
"""Shared helpers for Reading Mirror scripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterator


JSON_LINE_SEPARATOR_ESCAPES = str.maketrans(
    {
        "\u0085": "\\u0085",
        "\u2028": "\\u2028",
        "\u2029": "\\u2029",
    }
)


def data_home() -> Path:
    configured = os.environ.get("READING_MIRROR_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / "Library" / "Application Support" / "Codex" / "reading-mirror"


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def atomic_write_text(path: Path, value: str) -> None:
    ensure_private_dir(path.parent)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(0o600)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def json_dumps_single_line(value: Any) -> str:
    """Serialize UTF-8 JSON while escaping Unicode characters treated as line boundaries."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).translate(JSON_LINE_SEPARATOR_ESCAPES)


RECORD_START = re.compile(r"^<!-- record:start:([a-f0-9]{16}) -->$")


def iter_record_blocks(text: str) -> Iterator[dict[str, Any]]:
    """Yield parsed record blocks with their one-based line spans."""
    # Split only on the actual Markdown line delimiter. str.splitlines() also
    # splits valid JSON string characters such as U+0085/U+2028/U+2029.
    raw_lines = text.split("\n")
    lines = [line + "\n" for line in raw_lines[:-1]] + [raw_lines[-1]]
    index = 0
    while index < len(lines):
        start_match = RECORD_START.match(lines[index].rstrip("\r\n"))
        if not start_match:
            index += 1
            continue
        key = start_match.group(1)
        end_literal = f"<!-- record:end:{key} -->"
        end_index = index + 1
        record: dict[str, Any] | None = None
        while end_index < len(lines):
            stripped = lines[end_index].rstrip("\r\n")
            if stripped.startswith("record_json: "):
                payload = stripped[len("record_json: ") :]
                record = json.loads(payload)
            if stripped == end_literal:
                if record is None:
                    raise ValueError(f"Record {key} is missing record_json")
                yield {
                    "key": key,
                    "record": record,
                    "markdown": "".join(lines[index : end_index + 1]),
                    "start_line": index + 1,
                    "end_line": end_index + 1,
                }
                index = end_index + 1
                break
            end_index += 1
        else:
            raise ValueError(f"Record {key} is missing its end marker")


def record_key(record_id: str) -> str:
    return sha256_text(record_id)[:16]


def book_filename(book_id: str) -> str:
    return f"book-{sha256_text(book_id)[:24]}.md"
