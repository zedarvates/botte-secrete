# Needle 2: consultative memory pilot

Status: implemented experiment, **not approved for automatic routing or execution**.
This change builds on the shared memory API/MCP and advisory scribe in PR #111.
It adds an optional CPU specialist without changing the default router, memory
store, agent identity, or the legacy `needle_rs` adapter.

## What is implemented

`python -m skills.cli needle2 route ...` returns a validated proposal. It never
calls the memory service. Its output includes `executable: false`,
`executed: false`, `activation_allowed: false`, and zero executed tool calls and
memory writes. An abstention returns `memory_call: null` and exit code 3.

| Model choice | Existing MCP operation | Host-enforced scope |
|---|---|---|
| `memory_context` | `memory_recall` | Reviewed context, five results maximum |
| `memory_observations` | `memory_recall` | Observation area, five results maximum |
| `memory_history` | `memory_history` | One exact validated memory key |
| `memory_wiki` | `memory_wiki` | Cited Markdown view, five results maximum |
| `memory_scribe` | `memory_scribe` | Similarity advice for an ephemeral generated query record |

The host supplies `project_id`; the model cannot supply a project, actor,
credential, or write operation. The proposal is revalidated against the existing
memory contract. Any future consumer must independently authorize its execution
through the authenticated memory client. Scribe is consultative: it does not
capture, correct, promote, merge, or forget memories. See [shared memory](shared-memory.md).

The adapter uses a dedicated subprocess and an explicitly selected Python
interpreter. Only that interpreter needs `cactus-needle==2.0.13`. Core imports
remain standard library only. The native model is Needle **2**, engine 2.0.4 in
the recorded experiment; the Python package version is a separate identifier.

Each request resets the conversation. Different router instances have separate
native processes. The worker receives JSON schemas, calls `complete()`, and
never receives Python callables or calls `run()`. Model fields retain their
original JSON order: sorting schema keys changed native selections in a direct
control experiment. Canonical JSON is used for fingerprints only.

Bounds: five tools, 512 UTF-8 bytes of query, 16 KiB of tool schemas, 64 KiB per
worker response, and 256 generated tokens. The query bound is a byte bound,
not a claim that every input fits the model's token window. Pipe reads and writes
each have a configurable deadline (15 seconds by default); initialization adds
another exchange and process cleanup can take up to four seconds. A timeout,
crash, malformed response, missing engine, rejected argument, negation flag, or
insufficient confidence produces an abstention. Multiple proposed calls are
rejected. Confidence is an experimental score, not an authorization or a
calibrated probability of correctness on this domain.

Before importing Needle, the worker disables its telemetry and Hugging Face
network fetching. Inference requires an existing local native library. The
subprocess separates native state and permits termination; it is not an OS
security sandbox for an arbitrary untrusted binary.

## Reproduce on Linux x86-64

The measured runtime uses Python 3.12 on Linux x86-64. Windows and the actual
homelab have not been qualified. Run from the repository root. Setup downloads
public packages and an explicitly pinned native artifact; inference does not
download anything.

```bash
python -m venv .botte-cache/needle2-venv
.botte-cache/needle2-venv/bin/python -m pip install cactus-needle==2.0.13
```

Fetch only the recorded library, checking both the wheel and extracted bytes:

```python
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

revision = "32e9e3a93b205f786929697446ae669cf0a84579"
artifact = "cactus_needle-2.0.4-py3-none-manylinux2014_x86_64.whl"
url = f"https://huggingface.co/Cactus-Compute/needle2/resolve/{revision}/python/{artifact}"
with urllib.request.urlopen(url, timeout=60) as response:
    wheel = response.read(25_000_000)
if hashlib.sha256(wheel).hexdigest() != "13a84e6c73095fd175b11d46a30a984b62123d94421b769c107074aff7f65c2b":
    raise ValueError("Needle 2 wheel checksum mismatch")
with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
    names = [name for name in archive.namelist() if name.endswith("/libneedle.so")]
    if len(names) != 1:
        raise ValueError("Expected exactly one native library")
    library = archive.read(names[0])
if hashlib.sha256(library).hexdigest() != "9fa5386d3e3a8ee17914fb23643bc5f5c906b683fa33561e79c5445dd78bc389":
    raise ValueError("Needle 2 library checksum mismatch")
target = Path(".botte-cache/needle2-model/libneedle.so")
target.parent.mkdir(parents=True, exist_ok=True)
with target.open("xb") as handle:
    handle.write(library)
```

Inspect the catalog or request a proposal without contacting a memory server:

```bash
python -m skills.cli needle2 tools
python -m skills.cli needle2 route "Affiche la vue wiki du projet" --project-id pilot --engine-python .botte-cache/needle2-venv/bin/python --library .botte-cache/needle2-model/libneedle.so
python -m skills.cli needle2 benchmark --engine-python .botte-cache/needle2-venv/bin/python --library .botte-cache/needle2-model/libneedle.so --output .botte-cache/needle2-fr.json
```

An output file must not already exist. Exit codes: 0 for completed evaluation or
a proposal, 2 for invalid configuration/data/output, 3 for an abstention or an
unavailable/failed native runtime. A successful benchmark exit does **not** mean
that the model is accurate. `--confidence-threshold 0` is available for diagnostic
measurement only; it does not enable execution. The default remains 0.9.

Stop the CLI or close the router to end the experiment. No configuration switch,
background service, model download, or default routing change persists after it.

## Evidence and limits

The [validation manifest](validation/needle2-memory-pilot-v1.json) records the
native artifact, source fingerprints, checks and experiments. Full case results:
[default threshold](validation/needle2-memory-fr-default.json) and
[threshold-zero diagnostic](validation/needle2-memory-fr-diagnostic.json).

| Router / threshold | Exact positive calls | Unwanted proposals on negatives |
|---|---|---|
| Lexical baseline | 3 / 30 | 3 / 18 |
| Needle 2 / 0.9 (default) | 0 / 30 | 0 / 18 |
| Needle 2 / 0 (diagnostic) | 17 / 30 | 3 / 18 |

At the default threshold every case abstained. Removing the confidence filter
improves coverage, but leaves substantial errors; it is not an activation fix.
The [earlier diagnostics](validation/needle2-memory-superseded-diagnostics.json)
retain the results from before schema-field ordering was preserved, and the
direct controls used to isolate that integration issue. Their 7 / 30 diagnostic
score is superseded by the corrected adapter's 17 / 30 above. The corpus and tool
descriptions were unchanged between those runs.

The fixed [French corpus](../skills/tool_router/needle2_cases_fr.jsonl) has 30
positive and 18 negative synthetic cases, including spelling variation,
negation, missing arguments, writes, and requests outside the catalog. Baseline
and candidate receive identical inputs. Exact call accuracy requires **both** the
right tool and exactly matching arguments; even an empty optional query differs
from an omitted query. Negative abstention uses only the 18 negative cases as its
denominator. Aggregate tool accuracy includes negatives and cannot establish
useful routing by itself. The lexical baseline performs no argument extraction.

Measurements are exploratory, authored for this pilot, and not a held-out
production evaluation. P95 includes the cold first request and measures the
parent/worker round trip; no latency claim is transferable to the homelab. Native
peak memory has not been independently measured. A local generalist comparison,
French threshold calibration on a separate corpus, and real authorized user
tasks remain unmeasured. These records must not enter the successful-action
learning ledger or be used as an activation gate.

Unit tests use stand-in engines for response validation, process failure,
context reset, and isolation. The integration test exercises the real local
MemoryService and MCP bridge with synthetic temporary data, verifies an
unchanged database after all five reads, and checks identity/project boundaries.
CI runs these tests without downloading Needle. Actual model quality is measured
separately in the linked native experiments.

Sources: [Needle implementation](https://github.com/cactus-compute/needle),
[pinned Needle 2 artifacts](https://huggingface.co/Cactus-Compute/needle2/tree/32e9e3a93b205f786929697446ae669cf0a84579),
[Python package 2.0.13](https://pypi.org/project/cactus-needle/2.0.13/).
