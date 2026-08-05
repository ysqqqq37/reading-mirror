# Quotation and provenance policy

## Verified quotation

A displayed book quotation must come verbatim from `markText` in the user's `/book/bookmarklist` data. Preserve characters, punctuation, and wording exactly. Do not repair truncation or add missing context from memory or the internet.

Always retain the record's book title, author, chapter, book ID, highlight ID, range, and chapter UID when available. If source metadata is missing, omit the missing display component rather than inventing it.

## Verified personal annotation

Show “你当时的想法” only for content returned by `/review/list/mine` for this user.

Associate it with a quotation only through reliable fields, in this order:

1. matching `range` and compatible `chapterUid`;
2. exact normalized `abstract` plus compatible `chapterUid`;
3. an explicit original-record identifier when the API supplies one.

Semantic similarity is never sufficient for association.

If a personal annotation has no reliable quotation link, keep it as `chapter_comment` or `book_review`. Never fabricate a quotation to make the format uniform.

## Interpretation limits

- A highlight records attention, not necessarily agreement.
- A historical annotation supports only what it actually says.
- Do not state that the user “already knew”, “had realized”, or “always believed” something unless the annotation expresses it.
- Do not use public reviews, comments from other readers, popular highlights, or internet excerpts.
- Do not force a weak record into the answer for aesthetic completeness.
