# WeRead synchronization and mirror model

## Required Skill dependency

Use the installed `$weread-skills` Skill for every WeRead operation. Read its current `SKILL.md` and `notes.md` before synchronization and treat them as authoritative for authentication, versioning, endpoint semantics, pagination, field meanings, upgrades, and errors.

Run `scripts/check_dependencies.py` before reading the target Apple Note. A filesystem match is necessary but not sufficient: the Skill must also be visible in the current runtime's Available Skills. If it is missing, prompt the user to install or enable `weread-skills`; do not begin a partial Reading Mirror run. The checker accepts the legacy frontmatter name `wereadskill` but prefers the canonical installed name `weread-skills`.

`sync_weread.py` is only a deterministic incremental-mirror orchestrator around that contract. It discovers the installed WeRead Skill version automatically. If the Skill is missing or unreadable, stop; do not fall back to this reference as an independent API definition.

## Source APIs

Use only personal-data endpoints:

- `/user/notebooks`: books with personal reading traces and change signals;
- `/book/bookmarklist`: the user's exact highlight text and chapter metadata;
- `/review/list/mine`: the user's highlight annotations, chapter comments, and whole-book notes.

Do not use popular highlights, public reviews, or other readers' annotations.

Under the current `$weread-skills` contract, every request goes to `POST https://i.weread.qq.com/api/agent/gateway`, uses `Authorization: Bearer $WEREAD_API_KEY`, flattens business parameters at the JSON top level, and includes the version discovered from the installed WeRead Skill. If the installed Skill changes this contract, follow the installed Skill and update this orchestrator before proceeding.

For `/user/notebooks`, paginate with the final book's `sort` as the next `lastSort`. Do not use offset/limit. For `/review/list/mine`, paginate with the returned `synckey` and stop on `hasMore = 0`. Reject repeated cursors to avoid infinite loops.

## Incremental decision

For each book compare:

- presence of `bookId`;
- `sort`;
- `noteCount` (highlight count);
- `reviewCount` (personal thought/comment count);
- `bookmarkCount`.

When any signal changes, fetch the complete highlight and personal-review lists for that book and regenerate its file. This intentionally performs per-book replacement rather than guessing single-record deltas, so edits, deletions, and association changes converge correctly.

Use `--full` periodically or manually to refetch all books and compare content hashes.

## Record types

- `highlight_only`: verified `markText`, no reliably linked annotation.
- `highlight_with_note`: verified `markText` plus one or more personal annotations linked by range/chapter or exact abstract/chapter.
- `chapter_comment`: personal content associated with a chapter but no reliable highlight link.
- `book_review`: personal whole-book content without a reliable highlight link.

Never create a link from semantic similarity alone.

## Storage

Each book is a Markdown file containing machine-readable JSON metadata and human-readable record blocks. Filenames derive from a hash of `bookId` to prevent path injection. `manifest.json` stores source signals, filenames, content hashes, and timestamps. `corpus.md` concatenates current book files for inspection.

Writes are staged and atomically replaced. File permissions are private. No embeddings or vector database are created.
