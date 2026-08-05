#!/usr/bin/env python3
"""List or emit bounded batches of complete Reading Mirror records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from common import data_home, iter_record_blocks


def collect_records(books_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(books_dir.glob("*.md")):
        for block in iter_record_blocks(path.read_text(encoding="utf-8")):
            records.append(
                {
                    "path": str(path),
                    "start_line": block["start_line"],
                    "end_line": block["end_line"],
                    "record": block["record"],
                    "record_markdown": block["markdown"],
                }
            )
    return records


def make_batches(records: list[dict[str, Any]], max_chars: int) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_size = 0
    for record in records:
        size = len(record["record_markdown"])
        if current and current_size + size > max_chars:
            batches.append(current)
            current = []
            current_size = 0
        current.append(record)
        current_size += size
    if current:
        batches.append(current)
    return batches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, help="Emit one one-based batch; omit to list batch metadata")
    parser.add_argument("--max-chars", type=int, default=24000)
    parser.add_argument("--books-dir", type=Path, default=None)
    args = parser.parse_args()

    if args.max_chars < 1000:
        print(json.dumps({"error": "--max-chars must be at least 1000"}), file=sys.stderr)
        return 2
    books_dir = (args.books_dir or (data_home() / "mirror" / "books")).expanduser().resolve()
    if not books_dir.is_dir():
        print(json.dumps({"error": f"Mirror books directory does not exist: {books_dir}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        records = collect_records(books_dir)
        batches = make_batches(records, args.max_chars)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    if args.batch is None:
        print(
            json.dumps(
                {
                    "record_count": len(records),
                    "batch_count": len(batches),
                    "batches": [
                        {
                            "batch": index,
                            "record_count": len(batch),
                            "characters": sum(len(item["record_markdown"]) for item in batch),
                        }
                        for index, batch in enumerate(batches, start=1)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.batch < 1 or args.batch > len(batches):
        print(json.dumps({"error": f"Batch must be between 1 and {len(batches)}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    selected = batches[args.batch - 1]
    print(
        json.dumps(
            {"batch": args.batch, "batch_count": len(batches), "record_count": len(selected), "records": selected},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
