#!/usr/bin/env python3
"""Track append-mode boundaries without storing Apple Note content."""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from common import atomic_write_json, data_home, ensure_private_dir, load_json, sha256_text


def state_path() -> Path:
    return ensure_private_dir(data_home()) / "state" / "notes-state.json"


def load_state_unlocked() -> dict[str, Any]:
    state = load_json(state_path(), {"version": 1, "notes": {}})
    if not isinstance(state, dict) or not isinstance(state.get("notes"), dict):
        raise ValueError("notes-state.json is invalid")
    return state


@contextmanager
def state_lock(*, exclusive: bool):
    path = state_path().with_suffix(".lock")
    ensure_private_dir(path.parent)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            path.chmod(0o600)
        except OSError:
            pass
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def command_get(note_id: str) -> dict[str, Any]:
    with state_lock(exclusive=False):
        return load_state_unlocked()["notes"].get(note_id, {"status": "missing", "note_id": note_id})


def command_extract(note_id: str, plaintext: str) -> dict[str, Any]:
    with state_lock(exclusive=False):
        entry = load_state_unlocked()["notes"].get(note_id)
    if not entry:
        return {"status": "first_run", "note_id": note_id, "text": plaintext}

    previous_length = entry.get("post_write_plaintext_length")
    previous_hash = entry.get("post_write_plaintext_sha256")
    if not isinstance(previous_length, int) or previous_length < 0 or not isinstance(previous_hash, str):
        return {"status": "diverged", "note_id": note_id, "reason": "stored state is incomplete"}
    if len(plaintext) < previous_length:
        return {"status": "diverged", "note_id": note_id, "reason": "note is shorter than the verified prior version"}

    prefix = plaintext[:previous_length]
    if sha256_text(prefix) != previous_hash:
        return {"status": "diverged", "note_id": note_id, "reason": "previous note content was edited"}
    if len(plaintext) == previous_length:
        return {"status": "no_changes", "note_id": note_id, "text": ""}

    return {"status": "new_content", "note_id": note_id, "text": plaintext[previous_length:].lstrip("\r\n")}


def command_record(payload: dict[str, Any]) -> dict[str, Any]:
    note_id = payload.get("note_id")
    digest = payload.get("post_write_plaintext_sha256")
    length = payload.get("post_write_plaintext_length")
    if not isinstance(note_id, str) or not note_id:
        raise ValueError("note_id is required")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("post_write_plaintext_sha256 must be a SHA-256 hex digest")
    if not isinstance(length, int) or length < 0:
        raise ValueError("post_write_plaintext_length must be a non-negative integer")

    with state_lock(exclusive=True):
        state = load_state_unlocked()
        state["notes"][note_id] = {
            "note_id": note_id,
            "title": payload.get("title"),
            "post_write_plaintext_sha256": digest,
            "post_write_plaintext_length": length,
            "last_processed_user_hash": payload.get("last_processed_user_hash"),
            "last_run_at": payload.get("last_run_at") or datetime.now().astimezone().isoformat(),
        }
        atomic_write_json(state_path(), state)
    return {"status": "recorded", "note_id": note_id, "state_path": str(state_path())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("get", "extract"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--note-id", required=True)
    subparsers.add_parser("record")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "get":
            result = command_get(args.note_id)
        elif args.command == "extract":
            result = command_extract(args.note_id, sys.stdin.read())
        else:
            payload = json.load(sys.stdin)
            if not isinstance(payload, dict):
                raise ValueError("record input must be one JSON object")
            result = command_record(payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
