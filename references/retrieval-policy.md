# Retrieval policy

## Query construction

1. For marker mode, determine the logical question inside the marker's candidate window. Use the nearest heading, divider, previous marker/response, or clear topic change as the boundary; when structure remains ambiguous, read the nearby paragraphs and keep the smallest complete difficulty.
2. Split the resulting present context by paragraph and complete sentence.
3. Start with exact complete clauses and meaningful continuous phrases copied from that context.
4. Prefer phrases that preserve causal structure, contrast, and emotional emphasis.
5. Do not begin with abstract labels invented by the agent.
6. After a hit, allow new searches only from exact wording found in a real retrieved quotation or personal annotation.

`retrieve_with_rg.py` uses fixed-string `rg` searches and returns complete record blocks, not isolated matching lines.

## Expansion sequence

1. Read every initial hit as a complete record.
2. Read adjacent records and book/chapter metadata.
3. Search again using distinctive wording found in those real records.
4. When one book contains multiple relevant records, read that book's full mirror file.
5. If lexical recall remains weak, use `scan_corpus.py` to read bounded batches with the original note context present in reasoning.
6. De-duplicate records by `record_id` and substantive viewpoint.

## Relevance test

Include a record when it does at least one of the following without a strained analogy:

- directly responds to the present difficulty;
- explains its psychological or cognitive structure;
- has the same underlying causal structure;
- challenges a premise in the present wording;
- contributes a distinct supporting or conflicting view;
- supplies a realistic direction for action.

Exclude records that merely share a few words, require overinterpretation, repeat an existing viewpoint, lack verifiable provenance, or come from other readers/public sources.

## Stopping conditions

Stop only when all applicable conditions hold:

- another exact-text round produces no new candidates;
- all high-relevance book files have been read;
- corpus batches produce no new substantive viewpoint;
- remaining candidates only repeat already represented ideas.

Finding an arbitrary number of quotations is not a stopping condition.
