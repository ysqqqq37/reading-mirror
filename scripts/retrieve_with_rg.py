#!/usr/bin/env python3
"""Run fixed-string rg queries and return complete matching mirror records."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import data_home, iter_record_blocks


def split_physical_lines(value: str) -> list[str]:
    """Split only on CR/LF delimiters, preserving Unicode separators inside text."""
    return value.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def clean_queries(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for line in split_physical_lines(value):
            query = line.strip()
            if query and query not in seen:
                seen.add(query)
                result.append(query)
    return result


def load_blocks(path: Path) -> list[dict[str, Any]]:
    return list(iter_record_blocks(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", default=[], help="Exact original sentence, clause, or continuous phrase")
    parser.add_argument("--max-records", type=int, default=100)
    parser.add_argument("--books-dir", type=Path, default=None)
    args = parser.parse_args()

    queries = clean_queries(args.query)
    if not queries:
        print(json.dumps({"error": "At least one non-empty --query is required"}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.max_records < 1:
        print(json.dumps({"error": "--max-records must be positive"}), file=sys.stderr)
        return 2
    rg = shutil.which("rg")
    if not rg:
        print(json.dumps({"error": "ripgrep (rg) is not installed"}), file=sys.stderr)
        return 2

    books_dir = (args.books_dir or (data_home() / "mirror" / "books")).expanduser().resolve()
    if not books_dir.is_dir():
        print(json.dumps({"error": f"Mirror books directory does not exist: {books_dir}"}, ensure_ascii=False), file=sys.stderr)
        return 2

    command = [rg, "--json", "-n", "-F"]
    for query in queries:
        command.extend(["-e", query])
    command.append(str(books_dir))
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if completed.returncode not in (0, 1):
        print(json.dumps({"error": completed.stderr.strip() or "rg failed"}, ensure_ascii=False), file=sys.stderr)
        return 2

    line_hits: dict[Path, set[int]] = {}
    matched_queries: dict[tuple[Path, int], set[str]] = {}
    # rg emits one JSON event per physical line. str.splitlines() would also
    # split valid text at U+0085/U+2028/U+2029 and corrupt the event.
    for line in split_physical_lines(completed.stdout):
        if not line:
            continue
        event = json.loads(line)
        if event.get("type") != "match":
            continue
        data = event.get("data", {})
        path_text = data.get("path", {}).get("text")
        line_number = data.get("line_number")
        if not isinstance(path_text, str) or not isinstance(line_number, int):
            continue
        path = Path(path_text).resolve()
        line_hits.setdefault(path, set()).add(line_number)
        rendered_line = data.get("lines", {}).get("text", "")
        for query in queries:
            if query in rendered_line:
                matched_queries.setdefault((path, line_number), set()).add(query)

    results: list[dict[str, Any]] = []
    seen_records: set[str] = set()
    truncated = False
    for path in sorted(line_hits, key=str):
        blocks = load_blocks(path)
        for block in blocks:
            relevant_lines = [line for line in line_hits[path] if block["start_line"] <= line <= block["end_line"]]
            if not relevant_lines:
                continue
            record_id = str(block["record"].get("record_id"))
            if record_id in seen_records:
                continue
            if len(results) >= args.max_records:
                truncated = True
                break
            seen_records.add(record_id)
            query_set: set[str] = set()
            for line_number in relevant_lines:
                query_set.update(matched_queries.get((path, line_number), set()))
            results.append(
                {
                    "path": str(path),
                    "start_line": block["start_line"],
                    "end_line": block["end_line"],
                    "matched_queries": sorted(query_set),
                    "record": block["record"],
                    "record_markdown": block["markdown"],
                }
            )
        if truncated:
            break

    print(
        json.dumps(
            {"queries": queries, "record_count": len(results), "truncated": truncated, "records": results},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
