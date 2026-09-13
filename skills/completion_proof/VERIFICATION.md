# Receipt verification v1

The optional `--verify` path performs read-only integrity and source-version
checks. Legacy A11 marker detection stays unchanged. No commands from reports
or receipts are executed.

```text
python -m skills.completion_proof.cli report.json --verify --evidence-root evidence --source-root checkout --receipt-sha256 TRUSTED_DIGEST --json
```

Obtain `TRUSTED_DIGEST` from the trusted test executor, independently of the
agent report. Taking it from the report defeats the trust boundary. This is
an integrity anchor, not a signature or proof of executor honesty. A malicious
executor or an attacker able to replace both the receipt and trusted digest
can fabricate a passing result. The verifier does not reinterpret arbitrary
log text as proof of success: the trusted executor owns the structured result.

## Contract

The report names a receipt relative to `--evidence-root`:

```json
{"status":"complete","run_id":"run-1","proof":{"receipt_ref":"receipt.json"}}
```

Receipt shape (replace placeholders with actual SHA-256 values):

```json
{
  "schema_version": 1,
  "run_id": "run-1",
  "result": {"exit_code": 0, "tests_run": 3, "failures": 0, "errors": 0},
  "log": {"path": "tests.txt", "sha256": "LOG_SHA256"},
  "sources": [
    {"path": "app.py", "sha256": "SOURCE_SHA256"},
    {"path": "test_app.py", "sha256": "TEST_SHA256"}
  ]
}
```

The executor must capture source and test hashes before the run, ensure they
have not changed afterward, capture the actual outcome, then persist the
receipt and deliver its digest separately. The demo implements this controlled
capture for its three known unittest cases. There is no generic trusted-runner
service or signing system in this change.

## Checked conditions

- A well-formed receipt exists and matches the caller's SHA-256.
- Receipt and report name the same run.
- The recorded log exists and matches the receipt's hash.
- Every listed source/test file exists under the caller's source root and has
  the same bytes as recorded. This detects code or test changes after the run.
- Counts are typed integers with at least one test. Nonzero exit code, errors
  or failures produce `test_failed`, never success.
- Relative paths reject traversal, absolute paths, links/junctions and alternate
  stream syntax. JSON rejects duplicate keys and non-finite constants. Reads
  are bounded: 1 MB JSON, 8 MB per artifact, 32 MB aggregate log/source content,
  and at most 128 listed source files.

Roots must remain quiescent during verification. This is not a sandbox against
concurrent filesystem replacement. Only listed files are covered; dependencies,
environment, omitted files, coverage and latest-task identity are not inferred.
The caller must choose the expected receipt for the task being closed, not an
arbitrary historical passing receipt.

## Results

Human verification output defaults to French; use `--lang en` for English.
It shows a status, an explanation, a next action and the scope of verification.
Recorded test and checked-file counts appear when available. `--json` retains
the same schema and machine statuses regardless of language, and strict exit
codes do not change. Unknown or inconsistent results never display success.

| Status | Meaning |
|---|---|
| `announced` | Input is not a supported completion claim |
| `missing_evidence` | Missing receipt reference or referenced file |
| `invalid_evidence` | Invalid context, malformed data or integrity/version mismatch |
| `test_failed` | Artifacts match, but the recorded tests failed |
| `verified_on_recorded_tests` | Artifacts and listed files match the trusted passing receipt |

Without `--strict`, consumers must inspect `verified` and `status`: the CLI
returns zero for a completed verification, including invalid evidence.

## Optional strict gate

Append `--strict` to the verification command to use its exit status as a gate.
It requires `--verify` and the same explicit roots and trusted receipt digest.
The JSON result is identical in both modes. No global setting is changed.

| Exit code | Meaning |
|---|---|
| 0 | Consistent verified result, no errors |
| 2 | Incorrect CLI arguments |
| 3 | Missing evidence |
| 4 | Invalid evidence, unknown or inconsistent result |
| 5 | Recorded test failure |
| 6 | Not a supported completion claim |
| 7 | Root/access/read error |

The caller **must stop for every nonzero code**, including unexpected process
errors. For example, a local orchestrator using `subprocess.run(argv, check=True)`
must only close the task after that call succeeds, without swallowing its error.
The verifier itself does not write task state or enforce anything in a caller
that ignores its exit status. The replay demonstrates a local closure marker
written only on a successful strict process exit.

Run `python -m skills.completion_proof.test_verify` for adversarial cases and
a real unittest run followed by a detected test-source change. Run the
[demonstration](../../docs/demos/completion-proof/README.md) for published examples.
