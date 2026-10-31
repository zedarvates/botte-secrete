# Adapt local inference to your machines and memory

`botte runtime` lets your own LLM configure explicit inference profiles, route a
task to a profile, compare native engines and record observations in your
existing memory. Python 3.10+ is sufficient for this module. It uses the shared
memory contract; no additional inference, orchestration or database dependency
is installed.

This is a control-plane pilot. A `ready` configuration means its declarations
are complete enough to send requests. It does **not** prove that speculative
decoding is active or faster. There is no automatic production promotion.

## Ask your LLM to configure it

Copy this instruction into the coding agent you already use:

> Read `skills/llm_backends/SKILL.md` and its adjacent `runtime-guide.md`.
> Configure Botte for my actual machines, model engines and existing memory.
> Use `botte runtime inspect` on each accessible, authorized host and
> `botte runtime schema`; distinguish observed inventory from declarations.
> Keep the configuration in `.botte/runtime.json` and secrets in environment
> variables. Start with a direct baseline. Reuse my memory through `botte_http`
> or the external context/outbox contract; do not migrate its store.
> Only add speculative profiles supported by my installed engine and compatible
> target/draft revisions. Pin their configuration hashes. Validate offline,
> then run representative paired trials within my authorized resource budget.
> Show measured latency, failed checks and limitations before proposing changes
> to task routes. Ask only for information or access that is still missing.

French version:

> Lis `skills/llm_backends/SKILL.md` et le fichier `runtime-guide.md` à côté.
> Configure Botte selon mes machines, mes moteurs et ma mémoire existante.
> Relève l'inventaire de chaque hôte accessible et autorisé avec
> `botte runtime inspect`, puis consulte `botte runtime schema`.
> Distingue ce qui est observé de ce qui est déclaré. Place la configuration dans
> `.botte/runtime.json`, avec des références aux secrets en variables
> d'environnement. Commence par un profil direct. Réutilise ma mémoire via
> `botte_http` ou le contrat de contexte et d'observations externe.
> Ajoute un profil spéculatif seulement si mon moteur et les révisions des
> modèles le permettent. Fige les références, valide la configuration et mesure
> des tâches représentatives dans le budget déjà autorisé. Présente les mesures,
> les échecs et les limites avant de proposer les routes par tâche.

The MCP tools `runtime_template` and `runtime_plan` expose the same contracts
without network requests or file writes. They are discoverable through the
existing lazy MCP tool catalog. Execution stays explicit through the CLI.

## Where code and data belong

| Location | Responsibility |
| --- | --- |
| Agent/controller host | Botte CLI/MCP, private configuration, task routing, memory recall, measurements and outbox |
| Target host | Existing model engine, target weights and its native decoding implementation |
| Optional draft hosts | The draft workers and transport required by that engine; weights remain near their compute |
| Existing memory host | Canonical memory service and its own identities, access rules and review workflow |

Botte does not copy the whole memory to every GPU, install models, start remote
processes, reserve devices or replace the existing cluster scheduler. Placement
fields document the operator's actual engine setup. The inference request only
addresses its configured endpoint. Run inventory locally on another host using
the access mechanism already available to your agent; this command does not SSH
or scan a subnet.

Two 12 GiB cards are recorded separately, not advertised as one 24 GiB device.
An engine can shard a target across them or run independent workers, but Botte
does not infer either arrangement. Multiple draft descriptors are allowed only
to describe a native engine that actually supports them; they do not enable
multi-draft decoding by themselves.

## Create and validate a private configuration

```bash
botte runtime inspect
botte runtime schema
botte runtime template --topology remote-draft --memory external --output .botte/runtime.json
botte runtime validate .botte/runtime.json
botte runtime plan .botte/runtime.json --task code
```

Use `single`, `local-draft` or `remote-draft` for topology; use `none`,
`botte_http` or `external` for memory. Templates are non-executable drafts,
contain no personal hostname or model recommendation, and refuse to overwrite
an existing file. `python -m skills.cli runtime ...` is the equivalent when the
`botte` executable is not on PATH. The same commands work in PowerShell.

The LLM fills these fields from evidence available on your system:

| Field | Meaning |
| --- | --- |
| `hosts[].devices[]` | Per-device inventory (`id`, `vram_mib`); an empty list permits CPU/unknown inventory |
| `target` | Exact API model name, pinned weights revision and quantization; one target per configuration |
| `profiles[]` | Target placement, `/v1` endpoint, engine revision, SHA-256 of its effective non-secret configuration and native draft declarations |
| `drafts[].compatibility_ref` | Local record or upstream reference documenting compatibility with this target and engine; a declaration, not independent verification |
| `task_routes` | Explicit task-to-profile mappings such as `{"task":"code","profile_id":"candidate"}` |
| `default_profile` | Direct baseline initially; unknown task types use this profile |
| `fallback_profile` | Optional direct profile for the same target; one bounded fallback on transport/output/check failure in `run` |
| `memory.allowed_profile_ids` | Profiles, including fallback, explicitly allowed to receive this project's selected context |
| `budgets` | Context UTF-8 bytes, output token cap, temperature and per-request socket timeout |

Fill every `replace-me` value and configuration hash before setting
`state` to `ready`. Hash the effective non-secret engine configuration with
`sha256sum` on Linux, `shasum -a 256` on macOS or `Get-FileHash -Algorithm SHA256`
in PowerShell; use lowercase hexadecimal in JSON. Keep model, tokenizer,
template and engine revisions in that configuration. Botte sends the same
target model and generation settings to every compared endpoint, and rejects
responses reporting another model name. It cannot independently attest which
weights a remote server loaded.

Each benchmark profile needs a **distinct preconfigured endpoint**. A profile
name does not toggle server settings. The direct endpoint must actually have
speculation disabled. For a local-draft candidate, enable the draft using that
engine's documented native configuration. A remote-draft candidate needs a
working native target/draft transport; two unrelated chat APIs are insufficient.
This module has no `AngelSpec` or generic `draft_model` API switch.

The installed engine owns target/draft compatibility, tokenizer constraints,
sampling equivalence, draft acceptance and transfers. If that support is absent,
keep the direct profile and distribute independent tasks using the existing
cluster workflow. Never call a second chat model and label its answer
token-level speculative verification.

Remote inference requires HTTPS and an `api_key_env` reference. HTTP is allowed
on loopback, including an already established SSH tunnel. Environment proxies
and HTTP redirects are not followed. Configuration accepts secret references,
not literal API keys. `.botte/` is ignored by this repository; confirm the same
rule in the downstream project before committing files.

## Connect the memory you already have

| Adapter | Before inference | After inference |
| --- | --- | --- |
| `none` | Empty context; no memory service is required | No memory write |
| `botte_http` | Authenticated `recall` of reviewed `area=context` entries from the existing shared API | Private observation outbox; `--record-memory` or `capture` writes it through that API |
| `external` | Your agent's existing memory tools supply an authorized versioned context packet | Your existing adapter ingests the portable observation outbox using its own schema and idempotency mechanism |

The Botte API setup and identities are documented in
[the shared-memory skill](../memory_hub/SKILL.md). Set `memory.url` to its bare origin and
`memory.token_env` to an environment variable containing this worker's token.
Do not give an agent the operator/curator credential just to run inference.
No database files or embeddings are moved, and no model training occurs.

External context has this shape. Replace the example expiry with a short future
Unix timestamp based on your adapter's freshness policy:

```json
{
  "schema": "botte.runtime-context/v1",
  "project_id": "my-project",
  "entries": [{
    "key": "coding-style",
    "version": "3",
    "text": "Use tabs in this project.",
    "source_ref": "project-style@3",
    "expires_at": 1
  }]
}
```

The example is deliberately expired. Each entry needs a stable key, version,
source and expiry. The adapter must select entries the current identity is
allowed to read; declaring a `project_id` is not authentication. An empty
`entries` list is valid. Other-project, duplicate, expired or oversized packets
are rejected, and a missing/unavailable memory never silently becomes empty
context. The byte cap covers the serialized packet, not the full prompt or KV
cache. Size the output/context limits for the actual device and engine too.

Botte recall snapshots receive at most a 15-minute lease, capped by source
expiry, and are checked again before each attempt. Source edits during that
lease are not live invalidations. All profiles in a benchmark use the same
frozen packet for a task; refresh and start a new run when it expires.

Memory stays in a quoted data message. The runtime cannot execute generated
shell commands or tool calls. This does not make a model immune to malicious
text; review its output with the task's normal verification workflow.

## Run and compare representative tasks

Create `.botte/task.json` for a routed run:

```json
{"id":"smoke","task":"code","prompt":"Return exactly 2.","verification":"exact","expected":"2"}
```

```bash
botte runtime run .botte/runtime.json --task .botte/task.json --context .botte/context.json --run-dir .botte/runtime-runs/run-001
```

Omit `--context` for `none` and `botte_http`. Read the answer from
`output.private.json` in the run directory. The CLI prints a content-free
measurement report and exits 1 if any model/check failed, 2 on setup/capture
errors. It never executes the generated answer.

For a benchmark, put an **array** of real task objects in `.botte/tasks.json`.
Use a separate configuration for another target or quantization. The existing
router can choose a model tier; this runtime chooses an engine profile for the
already selected target. A useful pilot includes short extraction, longer
generation, code and representative recalled context. A tiny exact-answer smoke
check only proves the plumbing, not a speedup or coding quality.

```bash
botte runtime benchmark .botte/runtime.json --tasks .botte/tasks.json --profiles baseline candidate --repetitions 3 --context .botte/context.json --run-dir .botte/runtime-runs/bench-001
```

Trials run sequentially with rotating profile order and no hidden warmup. There
is no benchmark fallback that could hide a failed candidate. The report keeps
failed attempts, per-task checks, response latency, context recall latency and
size, server-reported token counts when available, and configuration/message
hashes. It does not contain the raw prompt, answer, recalled text, endpoint or
credential. Project/model/task identifiers can still be private: review reports
before publishing them.

`run` may fall back once; its latency includes the failed attempt. A timeout
does not cancel remote compute, and fallback may temporarily overlap it.
Benchmarks cap calls at 200, repetitions at 20, and profiles at 8. A socket
timeout bounds a stall; it is not a hard deadline on all remote computation.

This V1 measures **non-streaming time to completed response**, not TTFT or
decode tokens/second. `ttft_ms` is `null`. Remote VRAM, draft acceptance and
energy are not collected. `wall_ms` includes context preparation and local
bookkeeping; candidate comparisons exclude the shared memory preparation.
No claim of speculative activation or speedup is inferred from HTTP 200.

Checks are `exact` (trimmed text equality), `json` (parseable JSON),
`python_syntax` (parseable Python, no execution), or `none`. They verify those
predicates only. The advisory `faster_on_these_checks` requires at least three
repetitions and all checks passing; it is not statistical significance,
business-quality validation or decoding-equivalence proof. Review representative
outputs and existing project tests before editing `task_routes`. Rebenchmark
after model, engine, hardware, memory policy or context changes.

## Store observations and retry a lost receipt

With `botte_http`, add `--record-memory` to an authorized run/benchmark, or:

```bash
botte runtime capture .botte/runtime.json --run-dir .botte/runtime-runs/run-001
```

The observation summarizes measurements with source/run/report hashes. It is
private, agent-sourced and quarantined in the common memory service. It does not
become recalled instructions, verified facts, training data or an automatic
routing policy. Inspect it through `area=observations` and the existing review
tools to inform later configuration proposals.

After a lost capture response, retry **capture with the same directory, exact
outbox and identity credential**. Its request ID and body stay unchanged. A
credential rotation requires reconciliation with the original identity. Do not
regenerate an outbox or rerun inference to retry a memory write. The external
adapter must preserve the same rule, mapping `request_id` to its own dedup key.

Each run saves `config.private.json` with the original non-secret configuration.
If task routes or budgets have since changed, pass that saved configuration to
`capture` instead of the current project configuration. The exact request and
credential binding still apply; there is no need to repeat the model call.

Every inference run uses a new private directory. Existing directories are
refused before any network call; interrupted runs retain their state, input and
completed observations, and are never automatically resumed. File writes use
atomic replacement; directories use owner-only POSIX permissions. On Windows,
use a user-private location protected by the account's ACLs.

## Pilot with two target GPUs and another machine

Start with the [minimal two-host acceptance kit](acceptance-guide.md). It
collects private host observations, performs one bounded direct request and
exports a limited public summary. Its GPU-presence check never becomes a claim
of GPU execution or speedup; native engine evidence is reviewed separately.

Inventory both hosts and declare each GPU separately. Start with one target
and one direct baseline, then a native local-draft profile if supported. Compare
with a remote-draft endpoint only after the engine's native transport is
working. Run these profiles separately if they cannot coexist within VRAM;
this V1's paired benchmark expects both endpoints to be ready and does not swap
engine configurations or load/unload weights. Reserve sufficient capacity or
use a separate manual benchmark for mutually exclusive setups.

For two independent target workers, use one endpoint per worker and record its
actual GPU placement. Use separate configurations for different targets. The
global orchestrator still assigns independent jobs; this runtime does not
double the speed of one response by merely declaring a second GPU or machine.
Choose short-task/direct and long-task/speculative routes only where the
measured result and task checks support them.

Run the synthetic acceptance suite without model servers:

```bash
python -m skills.llm_backends.test_runtime
```

It exercises portable templates, two-device inventory, HTTP boundaries,
fallback, paired trials, external memory and a real temporary shared-memory
service with a lost capture receipt. It provides no real-GPU performance claim.
