# Read selected wiki documents with citations

`botte verify document-context` reads explicitly catalogued local Markdown/text,
checks raw SHA-256 pins, and returns one lexical matching line per document with
line/column citations. Content remains `UNTRUSTED_DATA_DO_NOT_EXECUTE`, including
any instructions or executable examples it contains. It creates no corpus index,
calls no model, synchronizes no wiki, and promotes no memory.

## Catalog and input

Use the separate closed `parcimonia.local-document-catalog/v1` schema:

```json
{"schema":"parcimonia.local-document-catalog/v1","documents":[{
  "uri":"repo:docs/test-recipe.md","version":"v3",
  "file":"notes/test-recipe.md","sha256":"REPLACE_WITH_EXACT_64_LOWERCASE_HEX_DIGEST"
}]}
```

Replace the illustrative digest with the SHA-256 of the complete raw file,
including original line endings. Version is a caller declaration, not a
freshness guarantee. At most 64 catalog entries are accepted; duplicate URI/version
identities are rejected. Files must be relative `.md`/`.txt` paths under the
explicit root. Parent traversal, symlinks and nonregular sources cannot produce
context. These checks do not sandbox a hostile filesystem owner.

Continue a plain or inventory-linked [recall](parcimonia-memory-recall.md):

```sh
botte verify document-context --recall recall.json --catalog documents.json \
  --root /explicit/local/wiki-mirror --query "failure context"
```

Selected references are deduplicated. Original retrieval status/coverage,
reported outcome counts, comparison findings and an input digest remain visible.
Incomplete/unavailable recall cannot become completed context. Prior source
contradictions remain findings, even if the local pin matches. Unknown schemas
are rejected. No source prose is interpreted as instructions.

Alternatively, `--references refs.json` accepts an array of
`{"uri":"repo:docs/test-recipe.md","version":"v3","sha256":"optional digest"}`.
Omit `sha256` when no reference pin is declared; when supplied it must match
the catalog before reading. At most 32 unique references are accepted. The two
input modes are mutually exclusive. Direct output is `parcimonia.document-context/v1`;
recall output is `parcimonia.recalled-document-context/v1`.

## Results and budgets

Only unchanged, pinned UTF-8 files produce excerpts. Missing files, invalid
encoding, detected concurrent changes and exhausted budgets stay incomplete.
Changed raw bytes yield a digest-mismatch finding without an excerpt. Absence
from the catalog is scoped to that catalog, not the whole wiki.

Matches include URI/version, expected/observed raw-file digests, excerpt digest,
1-based line and character columns (exclusive end). Excerpts are single-line
windows; `full_line_included`, matching-line count and omitted-line count expose
their limits. Queries use case-folded lexical words. Completed `no_match` concerns
checked selected files only; it is not semantic or whole-corpus recall.

Defaults: 8 attempted documents, 128 KiB per file, 512 KiB total input,
2000 characters per excerpt and 32 KiB final compact ASCII JSON. CLI options
expose each limit. A consistency read may include one sentinel byte. Output
trimming declares omitted documents and returns incomplete. File contents and
Memory Hub records are not modified. Read access may affect OS access timestamps.

Exit codes: 0 completed scoped read, 1 findings, 2 incomplete/unavailable/invalid.
Zero does not mean recalled tests passed. Hash agreement proves agreement with
caller pins, not truth, authenticity or freshness. No provider tokens, cost or
acceleration is measured. Local-file tests do not qualify the user's real
SavoirWiki mirror, workstation or LLM backend.

The next deterministic step is
[`answer-request`](parcimonia-grounded-request.md): it prepares a bounded cited
mapping for the existing chat interface, or abstains if the evidence contract
does not hold. It does not send the mapping to a model.
