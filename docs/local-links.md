# Supplied Markdown local-link checks

`check_local_links` compares supplied Markdown documents with supplied repository
paths. It never reads target files, accesses a network, calls a model or modifies
content. This permits deterministic checks using filenames from a Git tree and
documents fetched at the same commit, without downloading the entire repository.

The result is evidence about those inputs. It does not establish the state of
the user's live filesystem. The caller must retain the source revision,
pagination/truncation state and provenance of the supplied inventory.

## Python and MCP

```python
from skills.fallow_like.local_links import check_local_links

report = check_local_links(
    documents=[{"path": "README.md", "text": "[Guide](docs/guide.md)"}],
    available_paths=["README.md", "docs/guide.md"],
    inventory_complete=True,
)
```

The lazy Python MCP server exposes the same `check_local_links` arguments. Find
its schema with `find_tool` first. Its addition here does not update the
independently hosted cloud deployment or activate a routing hook.

`inventory_complete` defaults to `False`. An absent target then has status
`unresolved` and coverage is partial. Setting it to `True` permits `missing`
findings relative to the supplied complete inventory; it does not verify that
the caller's completeness declaration is correct. A target explicitly supplied
as a document is also known. Parent directories are inferred from known paths.

Paths are case-sensitive repository-relative POSIX paths. Source and inventory
paths must be normalized, without absolute paths, backslashes, drive names,
control characters, empty components or `.`/`..` components. Link destinations
may use relative `..` within the inventory root. URL percent encoding and Markdown
escapes are decoded; fragments and query strings are excluded from file lookup.
Absolute, non-POSIX and root-escaping destinations remain explicitly unchecked.

## Syntax and coverage

The parser supports a documented single-line Markdown subset: inline links and
images, angle destinations, optional titles, balanced or escaped parentheses,
and single-line reference definitions with explicit, collapsed or shortcut uses.
Code fences, inline code and comments are excluded. It is not a CommonMark
renderer. Ambiguous or unsupported constructs yield coverage issues rather than
an invented result. Blockquotes, list continuation, raw HTML and multiline
constructs may be conservatively skipped with partial coverage. Consult
`coverage.reasons` and unsupported findings.

External URL schemes and protocol-relative URLs are counted but never fetched.
Anchor-only links are counted but not validated. For `guide.md#section`, only the
file path is checked. Similar filenames, equivalent content and heading validity
are outside this contract.

The report uses `parcimonia.local-links/v1`. It includes counts, source paths and
line numbers for findings, resolved relative paths, missing/unresolved status,
coverage reasons, omitted detail counts and explicit execution boundaries.
`status: complete` means the supported checks finished on the supplied documents;
it does not mean that all Markdown files in a repository were inspected or that
no missing targets were found. Read `counts.missing` separately.

## Bounds and CLI

Inputs allow 1–200 unique `.md` document paths, each text at most 1 MiB UTF-8,
with at most 8 MiB of text in total. The unique inventory allows at most 50,000
paths and 8 MiB of path text. Each path is at most 4096 UTF-8 bytes. Invalid
types, additional document fields and invalid Unicode are rejected.

`max_links` defaults to 10,000 and allows integers from 1 through 50,000.
External and anchor links count against that limit. Findings retain at most
50 details, with an omitted count. Coverage limits and report truncation are
separate; either prevents a complete overall status.

```sh
python -m skills.fallow_like.links_cli input.json
python -m skills.fallow_like.links_cli - < input.json
```

The JSON file contains the Python/MCP arguments. The CLI reads at most 32 MiB of
UTF-8 JSON and rejects duplicate object keys. It returns JSON on stdout, with
exit 0 for complete checks without missing targets, 1 for complete checks with
missing targets, 3 for partial coverage or omitted findings, and 2 for invalid
input. A partial report may still contain confirmed missing targets relative to
the supplied inventory.

The existing `scripts/check_docs_links.py` keeps its explicit/default filesystem
paths and readable output, sharing the parser. This legacy entry point reads
local files and checks path existence; the pure API and MCP tool do not.
Its default exit behavior remains compatible: known missing targets return 1,
otherwise 0; incomplete checks print an explicit partial summary. Pass
`--strict-coverage` to return 3 whenever coverage is partial. The structured CLI
above always reports partial coverage with exit 3.

For task assessment, request explicit local Markdown link checking and provide
an actually available tool inventory. The `local_links` intent is a lexical
proposal only. Recognized negations, remote scope and supported mixed workflows
cause abstention. Other wording may escape this lexical heuristic; the host must
still interpret the entire task and verify the proposed route.

No token, price or speed reduction is inferred from the absence of a model call.
