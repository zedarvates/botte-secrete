# Exact file duplicate reports

The local Python runtime provides `find_file_duplicates` as a read-only task.
It inspects one explicit directory, groups eligible files by size and full
SHA-256, then compares bytes before reporting `exact_bytes` groups. Hard links
to one file identity are reported separately from independent copies.

```python
from skills.fallow_like.file_duplicates import find_file_duplicates

report = find_file_duplicates("/explicit/project")
```

```bash
python -m skills.fallow_like.duplicates_cli /explicit/project
```

The standalone CLI uses only the standard library and does not load the optional
full code analyzers. It emits JSON on stdout and exits with 0 for a complete
report, 3 for a partial report, and 2 for invalid inspection inputs. Missing CLI
arguments are handled by argparse. Finding a duplicate does not make the command
fail. The Python API and MCP tool share the same arguments and engine.

Discover `find_file_duplicates` through the existing MCP `find_tool`; it stays
outside the always-listed core. `root` is required. The host must resolve the
user's intended local scope before calling it. Parcimonia's advisory assessor
recognizes explicit French/English file-duplicate searches and can shortlist
offered tools; it does not execute a scan or authorize filesystem access.

## Bounds and interpretation

Defaults: 5,000 files, 20,000 directory entries, depth 20, 16 MiB per file and
64 MiB total bytes read. Hashing and final comparisons share the read budget.
An internal limit of 20,000 comparisons also bounds collision-heavy inputs.
The declared default directory exclusions are `.git`, `node_modules`, `.venv`,
`venv` and `__pycache__`. An explicit `exclude_dirs` list replaces these defaults;
entries must be directory basenames, not paths.

Observed symlinks, Windows reparse points and special files are skipped. The scanner checks file
identity and metadata before/after reads and reports detected changes or read
failures. These checks are not an atomic filesystem snapshot. The report states
which filesystem-access strategy was available on the current platform.

Metadata from a path and an open descriptor must share file identity, file type,
size and modification time. Complete markers, including change/creation time,
are compared within each source before and after reading. This avoids comparing
different `ctime` meanings in Windows CPython 3.12 while preserving each source's
own change detection. Path-derived executable permission bits are not compared
against descriptor-derived permission bits. See the pinned CPython sources for
[path timestamps](https://github.com/python/cpython/blob/v3.12.10/Modules/posixmodule.c#L2148)
and [descriptor timestamps](https://github.com/python/cpython/blob/v3.12.10/Python/fileutils.c#L1108).

`scan_partial` means the scan could not fully inspect its admitted scope, for
example because of a budget, depth, oversized file, read error or detected
change. Deliberate directory exclusions are declared separately. Empty groups
in a partial scan do not establish that the directory has no duplicate files.

Reports contain at most 50 duplicate groups and 20 paths per group; hard-link
groups and error/skip details are also bounded. Counts and omitted totals remain
explicit. `report_truncated` distinguishes omitted report details from a partial
scan. The overall `status` is `partial` if either condition applies.

`logical_duplicate_bytes` counts equal content across independent file
identities. It is not a promise of reclaimable physical storage: hard links,
sparse/compressed files and necessary intentional copies require separate
interpretation. The report does not recommend deletion or merge files.

This first increment concerns exact file content. Similar-looking images,
normalized code fragments and functionally overlapping features need different
methods and evidence levels. The existing lexical code detector remains a
candidate generator; this tool does not turn it into a proof of equivalence.

The tool runs where the Python runtime and the selected directory are available.
The hosted cloud helpers cannot inspect a caller's local filesystem by receiving
its path. This increment does not modify the hosted service or desktop projects.

## Validation

Engine and boundary tests cover exact equality, forced hash collisions, hard
links, empty files, exclusions, limits, errors/changes, strict JSON, CLI exit
codes, MCP discovery/dispatch and advisory task selection. Real Windows/Linux
target execution and the full repository CI are separate evidence from local
fixture runs. The dedicated `Exact file duplicate pilot` workflow runs the
engine and boundary suites on Ubuntu and Windows with Python 3.10 and 3.12.
