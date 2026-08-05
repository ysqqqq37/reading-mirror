#!/usr/bin/env python3
"""Inspect one exact Apple Note and perform guarded, attachment-free write-back."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

from common import normalize_text, sha256_text
from marker_logic import DEFAULT_MARKER, analyze_markers
from replace_markers import MarkerReplacementError, prepare_marker_replacement


READ_JXA = r'''
ObjC.import("Foundation");
function readStdin() {
  const data = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
  return ObjC.unwrap($.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding));
}
function safe(callable, fallback) {
  try { return callable(); } catch (error) { return fallback; }
}
function isoDate(value) {
  return safe(() => value.toISOString(), String(value));
}
const request = JSON.parse(readStdin());
const Notes = Application("Notes");
let matches;
if (request.note_id) {
  matches = Notes.notes.whose({id: request.note_id})();
} else if (request.exact_text) {
  const canonicalText = (value) => String(value)
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/\u00a0/g, " ");
  const query = canonicalText(request.exact_text);
  matches = Notes.notes().filter((note) => safe(
    () => canonicalText(note.plaintext()).includes(query),
    false
  ));
} else {
  matches = Notes.notes.whose({name: request.title})();
}
const items = matches.map((note) => {
  const item = {
    note_id: String(note.id()),
    title: String(note.name()),
    folder: safe(() => String(note.container().name()), ""),
    modification_date: isoDate(note.modificationDate()),
    password_protected: Boolean(note.passwordProtected()),
    shared: Boolean(note.shared()),
    attachment_count: safe(() => note.attachments().length, null)
  };
  if (request.include_content) {
    item.body = String(note.body());
    item.plaintext = String(note.plaintext());
  }
  return item;
});
JSON.stringify({matches: items});
'''


WRITE_JXA = r'''
ObjC.import("Foundation");
function readStdin() {
  const data = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
  return ObjC.unwrap($.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding));
}
function safe(callable, fallback) {
  try { return callable(); } catch (error) { return fallback; }
}
function isoDate(value) {
  return safe(() => value.toISOString(), String(value));
}
function serialize(note) {
  return {
    note_id: String(note.id()),
    title: String(note.name()),
    folder: safe(() => String(note.container().name()), ""),
    modification_date: isoDate(note.modificationDate()),
    password_protected: Boolean(note.passwordProtected()),
    shared: Boolean(note.shared()),
    attachment_count: safe(() => note.attachments().length, null),
    body: String(note.body()),
    plaintext: String(note.plaintext())
  };
}
const request = JSON.parse(readStdin());
const Notes = Application("Notes");
const matches = Notes.notes.whose({id: request.note_id})();
if (matches.length !== 1) {
  JSON.stringify({status: "not_unique", match_count: matches.length});
} else {
  const note = matches[0];
  const before = serialize(note);
  if (before.body !== request.expected_body) {
    JSON.stringify({status: "conflict"});
  } else if (before.password_protected) {
    JSON.stringify({status: "password_protected"});
  } else if (before.attachment_count === null) {
    JSON.stringify({status: "attachment_check_failed"});
  } else if (before.attachment_count > 0) {
    JSON.stringify({status: "attachments_present", attachment_count: before.attachment_count});
  } else if (before.shared && !request.allow_shared) {
    JSON.stringify({status: "shared_confirmation_required"});
  } else {
    note.body = request.new_body;
    const after = serialize(note);
    JSON.stringify({status: "ok", note: after});
  }
}
'''


class NotesError(RuntimeError):
    pass


def canonical_plaintext(value: str) -> str:
    """Normalize only platform line endings; preserve paragraph and spacing structure."""
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")


def logical_plaintext(value: str) -> str:
    """Compare text content while tolerating Notes-owned paragraph spacing."""
    return normalize_text(canonical_plaintext(value))


def run_jxa(script: str, payload: dict[str, Any]) -> dict[str, Any]:
    completed = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        if "-1743" in detail or "not authorized" in detail.lower() or "不允许" in detail:
            raise NotesError(
                "Apple Notes automation permission is missing. Allow the calling app to control Notes in "
                "System Settings → Privacy & Security → Automation, then retry."
            )
        raise NotesError(f"Apple Notes scripting failed: {detail or 'unknown error'}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise NotesError("Apple Notes scripting returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise NotesError("Apple Notes scripting returned an unexpected value")
    return value


def read_matches(
    *,
    title: str | None = None,
    note_id: str | None = None,
    exact_text: str | None = None,
    include_content: bool,
) -> list[dict[str, Any]]:
    response = run_jxa(
        READ_JXA,
        {
            "title": title,
            "note_id": note_id,
            "exact_text": exact_text,
            "include_content": include_content,
        },
    )
    matches = response.get("matches")
    if not isinstance(matches, list):
        raise NotesError("Apple Notes response is missing matches")
    return [item for item in matches if isinstance(item, dict)]


def one_note(*, title: str | None = None, note_id: str | None = None) -> dict[str, Any]:
    if title is not None:
        metadata = read_matches(title=title, include_content=False)
        if not metadata:
            raise NotesError(f"No Apple Note has the exact title: {title}")
        if len(metadata) > 1:
            error = NotesError(f"Multiple Apple Notes have the exact title: {title}")
            error.matches = metadata  # type: ignore[attr-defined]
            raise error
        note_id = str(metadata[0]["note_id"])
    matches = read_matches(note_id=note_id, include_content=True)
    if not matches:
        raise NotesError(f"Apple Note ID was not found: {note_id}")
    if len(matches) != 1:
        raise NotesError(f"Apple Note ID is not unique: {note_id}")
    return matches[0]


def enrich(note: dict[str, Any], marker: str) -> dict[str, Any]:
    body = note.get("body")
    plaintext = note.get("plaintext")
    if not isinstance(body, str) or not isinstance(plaintext, str):
        raise NotesError("Apple Notes did not return body and plaintext")
    return {
        **note,
        "body_sha256": sha256_text(body),
        "plaintext_sha256": sha256_text(plaintext),
        "plaintext_length": len(plaintext),
        "marker": marker,
        "markers": analyze_markers(plaintext, marker),
    }


def validate_write_request(request: dict[str, Any], note: dict[str, Any]) -> tuple[str, str, list[str]]:
    for key in ("note_id", "expected_body_sha256", "expected_plaintext_sha256", "action"):
        if not isinstance(request.get(key), str) or not request[key]:
            raise NotesError(f"{key} is required")
    if request["note_id"] != note.get("note_id"):
        raise NotesError("Resolved Note ID does not match write request")
    if request["expected_body_sha256"] != note["body_sha256"]:
        raise NotesError("conflict: Apple Note HTML body changed after inspection")
    if request["expected_plaintext_sha256"] != note["plaintext_sha256"]:
        raise NotesError("conflict: Apple Note plaintext changed after inspection")
    if note.get("password_protected"):
        raise NotesError("Refusing to write a password-protected Apple Note")
    attachment_count = note.get("attachment_count")
    if not isinstance(attachment_count, int):
        raise NotesError("Refusing write-back because Apple Notes attachments could not be verified")
    if attachment_count > 0:
        raise NotesError("Refusing HTML write-back because the Apple Note contains attachments")
    if note.get("shared") and request.get("allow_shared") is not True:
        raise NotesError("Shared Apple Note requires explicit action-time confirmation and allow_shared=true")

    body = note["body"]
    plaintext = note["plaintext"]
    action = request["action"]
    verification_texts: list[str] = []

    if action == "append":
        content_html = request.get("content_html")
        content_plaintext = request.get("content_plaintext")
        if not isinstance(content_html, str) or not content_html.strip():
            raise NotesError("append requires non-empty content_html")
        if not isinstance(content_plaintext, str) or not content_plaintext.strip():
            raise NotesError("append requires non-empty content_plaintext")
        verification_texts.append(content_plaintext)
        separator = "" if not body.strip() else "<br><br>"
        plaintext_separator = "" if not plaintext else "\n\n"
        return body + separator + content_html, plaintext + plaintext_separator + content_plaintext, verification_texts

    if action != "replace_markers":
        raise NotesError("action must be append or replace_markers")
    marker = request.get("marker", DEFAULT_MARKER)
    if not isinstance(marker, str) or not marker:
        raise NotesError("marker must be a non-empty string")
    replacements = request.get("replacements")
    if not isinstance(replacements, list):
        raise NotesError("replace_markers requires replacements")
    try:
        prepared = prepare_marker_replacement(
            body_html=body,
            plaintext=plaintext,
            marker=marker,
            replacements=replacements,
        )
    except MarkerReplacementError as exc:
        raise NotesError(str(exc)) from exc
    return prepared["body_html"], prepared["plaintext"], prepared["verification_texts"]


def compact_snapshot(note: dict[str, Any], marker: str) -> dict[str, Any]:
    enriched = enrich(note, marker)
    return {
        key: value
        for key, value in enriched.items()
        if key not in {"body", "plaintext"}
    }


def command_write(request: dict[str, Any]) -> dict[str, Any]:
    note_id = request.get("note_id")
    if not isinstance(note_id, str) or not note_id:
        raise NotesError("note_id is required")
    marker = request.get("marker", DEFAULT_MARKER)
    if not isinstance(marker, str) or not marker:
        raise NotesError("marker must be a non-empty string")
    current = enrich(one_note(note_id=note_id), marker)
    new_body, expected_after_plaintext, verification_texts = validate_write_request(request, current)

    response = run_jxa(
        WRITE_JXA,
        {
            "note_id": note_id,
            "expected_body": current["body"],
            "new_body": new_body,
            "allow_shared": request.get("allow_shared") is True,
        },
    )
    status = response.get("status")
    if status != "ok":
        messages = {
            "conflict": "conflict: Apple Note changed during the guarded write",
            "not_unique": "Apple Note ID was not resolved uniquely during write",
            "password_protected": "Refusing to write a password-protected Apple Note",
            "attachments_present": "Refusing HTML write-back because attachments appeared before write",
            "attachment_check_failed": "Refusing write-back because Apple Notes attachments could not be verified",
            "shared_confirmation_required": "Shared Apple Note requires explicit action-time confirmation",
        }
        raise NotesError(messages.get(str(status), f"Apple Notes write failed: {status}"))
    written = response.get("note")
    if not isinstance(written, dict):
        raise NotesError("Apple Notes write did not return a verification snapshot")
    after = enrich(written, marker)
    after_plaintext = after["plaintext"]
    # Notes may rewrite HTML paragraph boundaries into extra blank lines or
    # Unicode separators. Require the complete logical text and order to match,
    # while allowing those Notes-owned whitespace-only serialization changes.
    if logical_plaintext(after_plaintext) != logical_plaintext(expected_after_plaintext):
        raise NotesError(
            "Write completed but the full Apple Note plaintext does not match the intended result; "
            "inspect the note before any further action"
        )
    for expected in verification_texts:
        if normalize_text(expected) not in normalize_text(after_plaintext):
            raise NotesError("Write completed but generated plaintext could not be verified; inspect the note manually")
    if request["action"] == "replace_markers" and after["markers"]:
        raise NotesError("Write completed but at least one target marker remains")
    return {"status": "ok", "note": compact_snapshot(written, marker)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve", help="Resolve exact-title metadata without reading note bodies")
    resolve.add_argument("--title", required=True)

    resolve_text = subparsers.add_parser(
        "resolve-text",
        help="Read an exact visible-text query from stdin and return matching note metadata only",
    )
    resolve_text.add_argument(
        "--min-chars",
        type=int,
        default=12,
        help="Minimum normalized query length required for body matching",
    )

    inspect = subparsers.add_parser("inspect", help="Read one exact note and compute hashes/markers")
    target = inspect.add_mutually_exclusive_group(required=True)
    target.add_argument("--title")
    target.add_argument("--id", dest="note_id")
    inspect.add_argument("--marker", default=DEFAULT_MARKER)

    subparsers.add_parser("write", help="Read a guarded write request from stdin")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "resolve":
            matches = read_matches(title=args.title, include_content=False)
            result = {"status": "unique" if len(matches) == 1 else "ambiguous" if matches else "not_found", "matches": matches}
        elif args.command == "resolve-text":
            query = canonical_plaintext(sys.stdin.read()).strip()
            if len(normalize_text(query)) < args.min_chars:
                raise NotesError(
                    f"Exact-text resolution requires at least {args.min_chars} normalized characters"
                )
            matches = read_matches(exact_text=query, include_content=False)
            result = {
                "status": "unique" if len(matches) == 1 else "ambiguous" if matches else "not_found",
                "matches": matches,
            }
        elif args.command == "inspect":
            result = enrich(one_note(title=args.title, note_id=args.note_id), args.marker)
        else:
            payload = json.load(sys.stdin)
            if not isinstance(payload, dict):
                raise NotesError("Write input must be one JSON object")
            result = command_write(payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except NotesError as exc:
        error: dict[str, Any] = {"error": str(exc)}
        matches = getattr(exc, "matches", None)
        if matches is not None:
            error["matches"] = matches
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        return 4 if matches is not None else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
