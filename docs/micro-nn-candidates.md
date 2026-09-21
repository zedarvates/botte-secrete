# Micro-NN: inspect collection and train a separate candidate

This workflow advances the existing micro-NN inventory through local collection
and experimental training. It never activates a model or changes routing policy.
The [grounding roadmap](plans/2026-08-06_micro-nn-grounding-roadmap.md) still defines
the production qualification requirements.

## Inspect the account that actually runs Botte

From the intended checkout, using the same operating-system account as the agent:

```bash
python -m skills.botte_nn.active_learning status --json
```

The default ledger is `~/.cache/botte/active_learning/inference_logs.jsonl`.
An operator can explicitly inspect another known ledger directory:

```bash
python -m skills.botte_nn.active_learning status --json --data-dir /path/to/active_learning
```

These commands require only the Python standard library, do not create the
directory, and print counts, a local path and a SHA-256 snapshot digest. They
never print the underlying records. `collect` also only reads existing records;
its name does not mean it starts collection from agents.

| Ledger state | Meaning |
| --- | --- |
| `missing` | No ledger found at that path |
| `empty` | Readable ledger with no non-whitespace content |
| `present` | Readable, structurally valid records |
| `invalid` | Malformed UTF-8 or records; any returned counts are partial |
| `unreadable` | File access failed; the contents were not measured |

An invalid or unreadable ledger makes `status` exit 2. Missing and empty are
distinct successful observations of the selected path. A CI runner's missing
ledger does not establish an empty ledger on Eurekai, Odin or another account.
The checkup's `unavailable` state means the diagnostic itself could not run.

## Collect through the existing consumers

- Compression: Python callers need `reversible=True, learn=True`. The CLI and
  MCP wrappers already opt into learning, but a reversible call is still required.
  The current reversible implementation keeps the original in process memory;
  successful restoration labels the measured size reduction, not downstream
  answer quality or a standalone lossless encoding.
- Cache: the shared response cache enables labels unless
  `BOTTE_NN_AUTO_LABELS=0`. Explicit `ResponseCache` instances need `learn=True`.
  Hits and misses describe the cache outcome, not whether the cached answer is
  correct or reusable for another task.
- Routing: keep the returned `feedback_id` and use `route_feedback` or
  `active_learning verify <feedback_id> local|cloud` only after the correct route
  is established. Backend completion or failure alone is not a route verdict.

The collectors record features and fingerprints, not raw content or queries.
Keep production observations separate from tests, rehearsals and generated
corpora. This change neither starts a homelab collector nor imports the frozen
Needle/Qwen study into the production ledger.

## Train an explicitly selected model

Start with compression, for which an exact local outcome is already available:

```bash
python -m skills.botte_nn.active_learning train --model compressibility_predictor --data-dir /path/to/active_learning --output-dir /path/to/nn-candidates
```

Training needs NumPy, at least 50 unique locally declared verdicts, and every
output class in both training and validation. Duplicate input vectors and repeated
record identities are excluded; contradictory labels for an identical input are
excluded together. Missing verdicts or timestamps do not count. Malformed ledgers,
incompatible features/classes and malformed source tensors are rejected.

Inputs are deduplicated before a temporal 80/20 split; equal timestamps stay
together. The current source tensors are evaluated on that validation set before
fitting. Historical prediction fields are not used as the baseline score.

Only a strict improvement over the source model produces a candidate. The default
output root is the selected ledger directory's `candidates` subdirectory. Each
export uses a fresh private directory and a completed `model.json`; an interrupted
write can leave a `.tmp` file which is not a completed candidate. Existing candidates,
source JSON, embedded Rust weights and calibration files are never replaced.
The old `rebuild` command exits 2 before reading the ledger or running any process.

Candidate provenance includes source model/metadata, ledger and selected-dataset
digests, code digests, Python/NumPy versions, fitting parameters, partition digests,
class counts, measured source/candidate accuracy and explicit remaining evidence.
Keep the original ledger snapshot to reproduce a run; a digest cannot recover it.
Hashes bind local bytes, not an authenticated historical witness. No bit-identical
result across NumPy/platform versions is claimed.

`train` returns exit 0 when a candidate is exported, 1 for insufficient samples or
no improvement, and 2 for invalid inputs or an I/O/dependency error. The Python
`train()` returns the exported candidate's accuracy or `None`; invalid evidence
raises an exception. A multi-model run can retain completed candidates if a later
model fails, so a selected single model is the recommended first step.

## Counts do not authorize activation

The checkup preserves `verified` as the count of locally declared verdict rows and
adds `unique_verified`. `training_sample_ready` (and legacy `train_ready`) only
reports whether a readable valid ledger meets the 50-example floor. Training also
checks model shape and class coverage. `activation_sample_ready` only reports the
binary router's 2,000-example floor. `activation_ready` stays false and
`activation_status` stays `not_evaluated`: this diagnostic consumes no production
qualification evidence.

Local declarations do not authenticate an oracle or reviewer. Correlated tasks
with different feature vectors may remain, and repeated experiments can overfit
the same validation set. Independent evaluation, the task's deterministic baseline,
calibration, drift checks, rollback and intended-host evidence remain necessary.
The compression model's roadmap gate remains 1,000 deduplicated real outcomes;
the candidate-training floor does not replace it. Needle 2 remains consultative,
with its threshold study stopped. No activation or merge is part of this workflow.
