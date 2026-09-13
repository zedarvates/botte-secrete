# Private Holdout Runner

Factory Assurance can consume a genuinely private holdout without storing its
cases in the Botte Secrète repository.

## Security model

The private set lives on a machine or store that the builder-visible repository
does not expose. Examples: an operator-owned directory on Eurekai/Odin, a
maintainer-owned machine, or another access-controlled test environment.

Botte receives the local path only at execution time. The runner:

1. reads the private JSON set locally;
2. computes a canonical SHA-256 digest over the complete private set;
3. sends each case to an explicitly supplied evaluator via JSON stdin;
4. requires a JSON response containing only a boolean `passed` verdict;
5. aggregates the verdicts;
6. writes a public-safe attestation containing set ID, digest, candidate SHA,
   count and pass/fail status;
7. never includes the private case payloads in that attestation.

The runner uses `subprocess.run(..., shell=False)` and does not discover,
download, or select an evaluator automatically.

## Private set shape

This file must stay **outside the public repository**:

```json
{
  "set_id": "my-private-suite-v1",
  "cases": [
    {"id": "opaque-001", "input": {"...": "private payload"}},
    {"id": "opaque-002", "input": {"...": "private payload"}}
  ]
}
```

Do not commit real holdout cases, expected hidden answers, local paths,
credentials, or proprietary inputs.

## Evaluator protocol

For every case the evaluator receives on stdin:

```json
{"id": "opaque-001", "input": {"...": "private payload"}}
```

It must emit exactly one JSON object to stdout:

```json
{"passed": true}
```

A timeout, non-zero exit, malformed response, or missing boolean fails closed.
Evaluator stderr is not copied into the public attestation.

## Running locally

Use a candidate SHA that identifies the exact code under test:

```bash
python -m skills.factory_assurance.private_holdout_cli \
  /private/path/holdout.json \
  --candidate-sha <40-char-git-sha> \
  --output /safe/path/attestation.json \
  -- python /private/path/evaluator.py
```

The resulting `attestation.json` may be shared publicly if its metadata itself
is not sensitive. Before publishing it, inspect the set ID and any operator
metadata you choose to add around it.

## Public attestation shape

```json
{
  "schema": "botte.factory-holdout-attestation/v1",
  "set_id": "my-private-suite-v1",
  "set_digest_sha256": "...",
  "candidate_sha": "...",
  "case_count": 20,
  "status": "pass",
  "contains_cases": false
}
```

A digest proves that later reports refer to the same private set; it does **not**
prove who authored the set, that the set is good, or that it was secret. Signed
issuer identity remains a later capability.

## StoryCore first dark lap

The current StoryCore shadow lap already has public CI and controlled negative
mutation evidence. To close its private-holdout gap, create a small independent
MusicPlan suite outside both public repositories, run it against the exact
StoryCore candidate, preserve the private set locally, and feed only the
attestation into the Factory Assurance record.

Do not derive the hidden cases by copying the public unit tests verbatim; the
holdout should exercise plausible unseen edge cases while staying bounded and
non-destructive.
