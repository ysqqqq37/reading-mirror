#!/usr/bin/env python3
"""Build a private, per-book incremental Markdown mirror of personal WeRead traces."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from common import (
    atomic_write_json,
    atomic_write_text,
    book_filename,
    data_home,
    ensure_private_dir,
    json_dumps_single_line,
    load_json,
    normalize_text,
    record_key,
    sha256_text,
)
from check_dependencies import DependencyError, discover_weread_skill


DEFAULT_GATEWAY = "https://i.weread.qq.com/api/agent/gateway"


class SyncError(RuntimeError):
    pass


class UpgradeRequired(SyncError):
    pass


def discover_weread_skill_version() -> tuple[str, str]:
    try:
        skill = discover_weread_skill()
    except DependencyError as exc:
        raise SyncError(str(exc)) from exc
    return str(skill["version"]), str(skill["name"])


class GatewayClient:
    def __init__(self, url: str, api_key: str, skill_version: str, timeout: float) -> None:
        self.url = url
        self.api_key = api_key
        self.skill_version = skill_version
        self.timeout = timeout

    def post(self, api_name: str, **parameters: Any) -> dict[str, Any]:
        payload = {"api_name": api_name, "skill_version": self.skill_version, **parameters}
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise SyncError(f"WeRead HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SyncError(f"WeRead connection failed: {exc.reason}") from exc

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SyncError("WeRead returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise SyncError("WeRead response must be a JSON object")
        if result.get("upgrade_info"):
            upgrade = result["upgrade_info"]
            message = upgrade.get("message") if isinstance(upgrade, dict) else str(upgrade)
            raise UpgradeRequired(message or "The WeRead skill must be upgraded")
        errcode = result.get("errcode")
        if errcode not in (None, 0):
            message = result.get("errmsg") or result.get("message") or "unknown error"
            raise SyncError(f"WeRead API error {errcode}: {message}")
        return result


def fetch_notebooks(client: GatewayClient) -> list[dict[str, Any]]:
    books: list[dict[str, Any]] = []
    last_sort: Any = None
    seen_cursors: set[str] = set()
    while True:
        parameters: dict[str, Any] = {"count": 100}
        if last_sort is not None:
            parameters["lastSort"] = last_sort
        page = client.post("/user/notebooks", **parameters)
        page_books = page.get("books", [])
        if not isinstance(page_books, list):
            raise SyncError("/user/notebooks books is not a list")
        books.extend(item for item in page_books if isinstance(item, dict))
        if page.get("hasMore") not in (1, True):
            break
        if not page_books or page_books[-1].get("sort") is None:
            raise SyncError("/user/notebooks hasMore=1 without a usable lastSort")
        last_sort = page_books[-1]["sort"]
        cursor_key = str(last_sort)
        if cursor_key in seen_cursors:
            raise SyncError("/user/notebooks repeated lastSort cursor")
        seen_cursors.add(cursor_key)
    return books


def fetch_personal_reviews(client: GatewayClient, book_id: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    synckey: Any = 0
    seen_cursors: set[str] = set()
    while True:
        page = client.post("/review/list/mine", bookid=book_id, synckey=synckey, count=100)
        reviews = page.get("reviews", [])
        if not isinstance(reviews, list):
            raise SyncError("/review/list/mine reviews is not a list")
        for wrapper in reviews:
            if not isinstance(wrapper, dict):
                continue
            review = wrapper.get("review", wrapper)
            if isinstance(review, dict):
                results.append(review)
        if page.get("hasMore") not in (1, True):
            break
        next_cursor = page.get("synckey")
        if next_cursor is None:
            raise SyncError("/review/list/mine hasMore=1 without synckey")
        cursor_key = str(next_cursor)
        if cursor_key in seen_cursors or next_cursor == synckey:
            raise SyncError("/review/list/mine repeated synckey cursor")
        seen_cursors.add(cursor_key)
        synckey = next_cursor
    return results


def notebook_book_id(item: dict[str, Any]) -> str:
    value = item.get("bookId")
    if value is None and isinstance(item.get("book"), dict):
        value = item["book"].get("bookId")
    if value is None:
        raise SyncError("Notebook entry is missing bookId")
    return str(value)


def chapter_compatible(left: Any, right: Any) -> bool:
    return left in (None, "") or right in (None, "") or str(left) == str(right)


def unix_to_iso(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value)).astimezone().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def stable_highlight_id(book_id: str, highlight: dict[str, Any]) -> str:
    explicit = highlight.get("bookmarkId")
    if explicit not in (None, ""):
        return f"highlight:{explicit}"
    basis = json.dumps(
        [book_id, highlight.get("chapterUid"), highlight.get("range"), highlight.get("markText")],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"highlight:{sha256_text(basis)[:24]}"


def stable_review_id(book_id: str, review: dict[str, Any]) -> str:
    explicit = review.get("reviewId")
    if explicit not in (None, ""):
        return f"review:{explicit}"
    basis = json.dumps(
        [book_id, review.get("chapterUid"), review.get("range"), review.get("content")],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"review:{sha256_text(basis)[:24]}"


def build_records(
    notebook: dict[str, Any], bookmarks_response: dict[str, Any], reviews: list[dict[str, Any]]
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    book_id = notebook_book_id(notebook)
    book_info: dict[str, Any] = {}
    if isinstance(notebook.get("book"), dict):
        book_info.update(notebook["book"])
    if isinstance(bookmarks_response.get("book"), dict):
        for key, value in bookmarks_response["book"].items():
            book_info.setdefault(key, value)
    book = {
        "book_id": book_id,
        "title": str(book_info.get("title") or ""),
        "author": str(book_info.get("author") or ""),
    }

    chapters: dict[str, str] = {}
    for chapter in bookmarks_response.get("chapters", []) or []:
        if isinstance(chapter, dict) and chapter.get("chapterUid") is not None:
            chapters[str(chapter["chapterUid"])] = str(chapter.get("title") or "")

    highlights: list[dict[str, Any]] = []
    for item in bookmarks_response.get("updated", []) or []:
        if not isinstance(item, dict) or item.get("markText") is None:
            continue
        chapter_uid = item.get("chapterUid")
        highlights.append(
            {
                "record_id": stable_highlight_id(book_id, item),
                "record_type": "highlight_only",
                **book,
                "highlight_id": item.get("bookmarkId"),
                "chapter_uid": chapter_uid,
                "chapter": chapters.get(str(chapter_uid), "") if chapter_uid is not None else "",
                "range": item.get("range"),
                "created_at": item.get("createTime"),
                "created_at_iso": unix_to_iso(item.get("createTime")),
                "quote": item.get("markText"),
                "user_notes": [],
            }
        )

    used_review_indexes: set[int] = set()
    linked_by_highlight: dict[int, list[dict[str, Any]]] = {index: [] for index in range(len(highlights))}
    for review_index, review in enumerate(reviews):
        content = review.get("content")
        if not isinstance(content, str) or not content.strip():
            continue

        range_candidates = [
            index
            for index, highlight in enumerate(highlights)
            if highlight.get("range") not in (None, "")
            and review.get("range") not in (None, "")
            and str(highlight["range"]) == str(review["range"])
            and chapter_compatible(highlight.get("chapter_uid"), review.get("chapterUid"))
        ]
        candidate_indexes = range_candidates
        if len(candidate_indexes) != 1:
            abstract = review.get("abstract")
            if isinstance(abstract, str) and abstract.strip():
                abstract_normalized = normalize_text(abstract)
                search_space = range_candidates if range_candidates else list(range(len(highlights)))
                candidate_indexes = [
                    index
                    for index in search_space
                    if normalize_text(str(highlights[index].get("quote") or "")) == abstract_normalized
                    and chapter_compatible(highlights[index].get("chapter_uid"), review.get("chapterUid"))
                ]
        if len(candidate_indexes) != 1:
            continue

        target_index = candidate_indexes[0]
        linked_by_highlight[target_index].append(
            {
                "review_id": review.get("reviewId"),
                "content": content,
                "abstract": review.get("abstract"),
                "range": review.get("range"),
                "chapter_uid": review.get("chapterUid"),
                "created_at": review.get("createTime"),
                "created_at_iso": unix_to_iso(review.get("createTime")),
            }
        )
        used_review_indexes.add(review_index)

    for highlight_index, linked in linked_by_highlight.items():
        if linked:
            highlights[highlight_index]["record_type"] = "highlight_with_note"
            highlights[highlight_index]["user_notes"] = linked

    records = highlights
    for index, review in enumerate(reviews):
        if index in used_review_indexes:
            continue
        content = review.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        has_chapter = review.get("chapterUid") not in (None, "") or review.get("chapterName") not in (None, "")
        record_type = "chapter_comment" if has_chapter else "book_review"
        chapter_uid = review.get("chapterUid")
        records.append(
            {
                "record_id": stable_review_id(book_id, review),
                "record_type": record_type,
                **book,
                "review_id": review.get("reviewId"),
                "chapter_uid": chapter_uid,
                "chapter": str(review.get("chapterName") or chapters.get(str(chapter_uid), "")),
                "range": review.get("range"),
                "created_at": review.get("createTime"),
                "created_at_iso": unix_to_iso(review.get("createTime")),
                "user_note": content,
                "abstract": review.get("abstract"),
            }
        )

    return book, records


def markdown_quote(value: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in value.splitlines())


def render_record(record: dict[str, Any]) -> str:
    key = record_key(str(record["record_id"]))
    serialized = json_dumps_single_line(record)
    lines = [
        f"<!-- record:start:{key} -->",
        f"record_json: {serialized}",
        f"record_id: {record['record_id']}",
        f"record_type: {record['record_type']}",
        f"chapter: {record.get('chapter') or ''}",
    ]
    quote = record.get("quote")
    if isinstance(quote, str):
        lines.extend(["quote:", markdown_quote(quote)])
    notes = record.get("user_notes")
    if isinstance(notes, list):
        for note in notes:
            if isinstance(note, dict) and isinstance(note.get("content"), str):
                lines.extend(["user_note:", markdown_quote(note["content"])])
    note = record.get("user_note")
    if isinstance(note, str):
        lines.extend(["user_note:", markdown_quote(note)])
    lines.append(f"<!-- record:end:{key} -->")
    return "\n".join(lines)


def render_book(book: dict[str, str], records: list[dict[str, Any]]) -> str:
    display_title = book["title"] or "（书名未提供）"
    header = [
        f"# {display_title}",
        "",
        f"- book_id: {book['book_id']}",
        f"- author: {book['author']}",
        f"- record_count: {len(records)}",
        "",
    ]
    blocks = [render_record(record) for record in records]
    return "\n".join(header) + "\n\n".join(blocks) + ("\n" if blocks else "")


def source_signals(notebook: dict[str, Any]) -> dict[str, Any]:
    return {
        "sort": notebook.get("sort"),
        "note_count": notebook.get("noteCount"),
        "review_count": notebook.get("reviewCount"),
        "bookmark_count": notebook.get("bookmarkCount"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Refetch every notebook book")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and compare without writing")
    parser.add_argument("--gateway", default=DEFAULT_GATEWAY)
    parser.add_argument("--allow-test-gateway", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skill-version", default=os.environ.get("WEREAD_SKILL_VERSION"))
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    if args.gateway != DEFAULT_GATEWAY:
        from urllib.parse import urlparse

        hostname = urlparse(args.gateway).hostname
        if not args.allow_test_gateway or hostname not in {"127.0.0.1", "localhost", "::1"}:
            print(
                json.dumps({"error": "Refusing to send WEREAD_API_KEY to a non-official gateway"}, ensure_ascii=False),
                file=sys.stderr,
            )
            return 2

    api_key = os.environ.get("WEREAD_API_KEY")
    if not api_key:
        print(json.dumps({"error": "WEREAD_API_KEY is not set"}, ensure_ascii=False), file=sys.stderr)
        return 2

    root = data_home()
    mirror_dir = root / "mirror"
    books_dir = mirror_dir / "books"
    manifest_path = mirror_dir / "manifest.json"
    try:
        discovered_version, weread_skill_name = discover_weread_skill_version()
        skill_version = args.skill_version or discovered_version
        manifest = load_json(manifest_path, {"version": 1, "books": {}})
        if not isinstance(manifest, dict) or not isinstance(manifest.get("books"), dict):
            raise SyncError("manifest.json is invalid")

        client = GatewayClient(args.gateway, api_key, skill_version, args.timeout)
        notebooks = fetch_notebooks(client)
        current: dict[str, dict[str, Any]] = {notebook_book_id(item): item for item in notebooks}
        old_books: dict[str, Any] = manifest["books"]

        changed: list[str] = []
        skill_version_changed = manifest.get("skill_version") not in (None, skill_version)
        for book_id, notebook in current.items():
            old = old_books.get(book_id)
            expected_file = old.get("filename") if isinstance(old, dict) else None
            signals_changed = not isinstance(old, dict) or old.get("source") != source_signals(notebook)
            expected_path = books_dir / str(expected_file) if expected_file else None
            file_missing = expected_path is None or not expected_path.is_file()
            file_corrupt = False
            if not file_missing and isinstance(old, dict):
                expected_hash = old.get("content_hash")
                file_corrupt = not isinstance(expected_hash, str) or sha256_text(
                    expected_path.read_text(encoding="utf-8")
                ) != expected_hash
            if args.full or skill_version_changed or signals_changed or file_missing or file_corrupt:
                changed.append(book_id)
        removed = sorted(set(old_books) - set(current))

        generated: dict[str, tuple[str, dict[str, Any]]] = {}
        for book_id in changed:
            bookmarks = client.post("/book/bookmarklist", bookId=book_id)
            reviews = fetch_personal_reviews(client, book_id)
            book, records = build_records(current[book_id], bookmarks, reviews)
            content = render_book(book, records)
            generated[book_id] = (
                content,
                {
                    "book_id": book_id,
                    "title": book["title"],
                    "author": book["author"],
                    "filename": book_filename(book_id),
                    "source": source_signals(current[book_id]),
                    "record_count": len(records),
                    "content_hash": sha256_text(content),
                    "last_synced_at": datetime.now().astimezone().isoformat(),
                },
            )

        if args.dry_run:
            print(
                json.dumps(
                    {"status": "dry_run", "book_count": len(current), "changed": changed, "removed": removed},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        ensure_private_dir(root)
        ensure_private_dir(books_dir)
        new_entries: dict[str, Any] = {key: value for key, value in old_books.items() if key in current}
        for book_id, (content, entry) in generated.items():
            atomic_write_text(books_dir / entry["filename"], content)
            new_entries[book_id] = entry
        for book_id in removed:
            old = old_books.get(book_id)
            filename = old.get("filename") if isinstance(old, dict) else None
            if isinstance(filename, str) and filename == book_filename(book_id):
                candidate = books_dir / filename
                if candidate.is_file():
                    candidate.unlink()

        new_manifest = {
            "version": 1,
            "skill_version": skill_version,
            "weread_skill_name": weread_skill_name,
            "last_synced_at": datetime.now().astimezone().isoformat(),
            "books": new_entries,
        }
        atomic_write_json(manifest_path, new_manifest)

        corpus_parts = ["# Reading Mirror corpus\n"]
        ordered_entries = sorted(new_entries.values(), key=lambda item: (str(item.get("title", "")), str(item.get("book_id", ""))))
        for entry in ordered_entries:
            path = books_dir / entry["filename"]
            if not path.is_file():
                raise SyncError(f"Mirror file is missing after sync: {entry['filename']}")
            corpus_parts.append(path.read_text(encoding="utf-8").rstrip() + "\n")
        corpus = "\n".join(corpus_parts)
        atomic_write_text(mirror_dir / "corpus.md", corpus)

        print(
            json.dumps(
                {
                    "status": "ok",
                    "book_count": len(new_entries),
                    "changed_count": len(changed),
                    "removed_count": len(removed),
                    "mirror_path": str(mirror_dir),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except UpgradeRequired as exc:
        print(json.dumps({"error": "upgrade_required", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 3
    except (SyncError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
