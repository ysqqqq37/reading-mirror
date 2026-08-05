# Apple Notes safety

## Scope

Resolve only the Note ID, exact title, or substantial exact visible passage the user supplies. When a passage is supplied without a title, `apple_notes.py resolve-text` may compare that literal text against note plaintext locally, but returns metadata only. Never convert the passage into keywords or use semantic/fuzzy body search. If multiple matches exist, ask the user to choose by folder, modification time, and ID; do not generate the answer body first.

One exact candidate authorizes immediate Reading Mirror write-back when the user's request is to answer or fill the note. Do not preview the full response in chat. Explicit chat-only/preview requests override this default, and shared notes still require action-time confirmation.

Never delete, move, rename, or modify another note.

The vendored `scripts/apple-notes/notes.sh` is the basic search/read/create/append substrate. Reading Mirror wraps it with `apple_notes.py` because the upstream CLI does not expose every attachment/shared/plaintext guard required for whole-body marker replacement. Never downgrade to a raw append or body assignment merely because it is shorter.

## Before writing

Require all of the following:

- the note is not password protected;
- the note has no attachments when using the HTML bridge;
- a shared note has explicit action-time confirmation;
- the current HTML-body and plaintext hashes equal the inspected hashes;
- marker count, order, and preceding-context hashes still match;
- marker mode includes one replacement for every marker;
- the original-text date is derived from the fresh pre-write Notes modification timestamp in the user's local timezone;
- every generated response receives the local write date, and neither date is supplied by model-authored content;
- the exact fresh pre-write note title is captured for restoration after body assignment;
- the title still equals that captured value inside the guarded write transaction;
- `replace_markers.py` succeeds against the original HTML/plaintext snapshot before the guarded writer repeats the same validation on its fresh snapshot.

If any check fails, perform no write.

## Attachments

Setting the Notes `body` property replaces the HTML representation and can damage attachments. `apple_notes.py write` therefore refuses every note with one or more attachments.

For an attachment-bearing note:

- read the `cua-driver` Skill before native UI automation;
- use Notes.app UI to insert at the marker or append without replacing the full body;
- snapshot before and after every action and verify placement;
- if a reliable UI insertion cannot be performed, stop and explain the safety block.

Never bypass this guard with a raw AppleScript/JXA body assignment.

## Concurrency and verification

Use both `body_sha256` and `plaintext_sha256` from the original inspection. The bridge compares the complete expected body again inside the same Notes scripting write transaction. A mismatch is a conflict, not a retry signal.

After writing, re-read by Note ID and verify:

- every target marker is gone;
- an effective original body begins with exactly one `YYYY年MM月DD号` date boundary;
- each new Reading Mirror response begins with the current local `YYYY年MM月DD号` date boundary;
- the Apple Note title is exactly unchanged from the fresh pre-write snapshot;
- generated plaintext is present in the expected order;
- no unrelated content disappeared;
- the post-write hashes are recorded only after verification.

Apple Notes may derive `name` from the first body line when `body` is assigned. Treat the title and body as separate invariants: keep the original-text date as the first visible body paragraph, then restore the captured `name` and verify it. Never move the date beneath the former first line to make the sidebar title look correct.

Automation-permission errors may require the user to allow the calling app to control Notes in System Settings. Report that concrete requirement; do not pretend the write succeeded.
