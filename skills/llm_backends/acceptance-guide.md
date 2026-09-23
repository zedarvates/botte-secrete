# A minimal acceptance run on your actual hosts

Use this kit after the portable runtime's software tests pass. It prepares one
short, nonce-bound direct request and a deliberately limited public summary.
It does not deploy services, transfer files, merge code or run a benchmark.

The two roles are **controller** (the agent running Botte) and **engine** (the
host intended to serve the target model). Keep your own hostnames, paths, keys,
process IDs and model names in private operator notes. All generated files
except an explicitly exported summary are private.

## What the first run can establish

| Evidence | Conclusion it supports | Remaining evidence |
| --- | --- | --- |
| CI and temporary loopback tests | The collector, request and export software behaves as tested | Actual host execution |
| Fresh collector records with different salted installation IDs | Two OS installations were recorded using the same challenge and collector sources | Physical separation; VMs may share one computer |
| One response passing the exact nonce check | The configured endpoint answered the synthetic request | Binding that endpoint/tunnel to the intended engine host |
| Selected GPU listed on the engine host | The collector observed that device and its VRAM capacity | Proof that the target process executed this request on that GPU |
| Matching quarantined memory receipt | A capture receipt for this run was recorded | Broader identity/isolation/recovery acceptance, covered by the existing memory pilot |
| Native engine logs and request correlation | An operator can review the actual model/device execution path | Representative paired trials before any speedup claim |

The exporter keeps `endpoint_host_binding_verified`, `gpu_execution_verified`,
`speculative_mode_verified`, `speedup_measured` and `production_ready` false.
Those flags cannot be enabled by adding a claimed boolean to an input file.
Collected files are operator evidence, not signed hardware attestations. A
successful synthetic echo server is also capable of passing the smoke check.

## 1. Prepare on the controller

Use the same reviewed checkout or installed code on both hosts. The source
fingerprint covers the collector, runtime, memory client/contract and atomic
writer; it normalizes source line endings for Windows/Linux checkouts. It is
not an attestation of the separate model engine or memory server binaries.

Keep the current Git commit in your private operator notes. Use the existing
[runtime setup guide](runtime-guide.md) to fill `.botte/runtime-acceptance.json`
from actual engine configuration. This smoke requires:

- A `ready` direct profile selected for task `runtime_acceptance`.
- Exactly one declared target GPU, using the ID from `botte runtime inspect`.
- No fallback to a different profile.
- At most 256 output tokens and a 120-second socket timeout; 64 tokens is a
  reasonable starting cap for a model that answers directly. Reasoning-heavy
  engines may truncate; that is a failed smoke, not a reason to accept a partial answer.
- An existing model already loaded within the intended device's capacity.

Use `none` for an inference-only first run. Use `botte_http` when your existing
shared service and normal worker credential are ready. `external` accepts an
authorized context packet through `--context`. Reuse the existing store and
identities; this kit creates no memory service or operator credential.

These one-line commands work in PowerShell too:

```bash
python -m skills.cli runtime validate .botte/runtime-acceptance.json
python -m skills.cli runtime acceptance prepare .botte/runtime-acceptance.json --directory .botte/acceptance-001
```

Preparation is offline and refuses an existing directory. It creates a private
configuration copy, `challenge.json` and a fixed synthetic `task.json`. Keep
the configuration on the controller. Transfer only `challenge.json` to the
engine host through your existing private administration channel.

## 2. Collect on the engine host

Linux example, from the reviewed checkout:

```bash
python3 -m skills.cli runtime acceptance collect .botte/challenge.json --role engine --storage-path . --output .botte/engine-observation.private.json
```

Choose `--storage-path` on the existing model/artifact volume when it differs
from the checkout volume. The collector reads current OS/GPU inventory,
free space on that volume and free space on the root volume. It neither scans
model directories nor downloads weights. Inspect the private record before
proceeding if the root volume is tight; it is a measurement, not an automatic
storage-maintenance action.

The collector uses a nonce-salted Linux machine ID or Windows MachineGuid.
It never writes the raw ID or hostname into the observation. Missing identity
or unsupported OS identification stops collection; do not fabricate a second
host identity. GPU inventory can be unavailable in containers or under an
insufficient account: collect on the actual host with the intended access.

Transfer the resulting observation privately back to the controller. The
engine observation must be within 15 minutes of the request, with at most
60 seconds of future clock skew. Each output file is new; use a new filename
when recollecting. Collection itself performs no network request.

## 3. Execute the single direct request on the controller

```bash
python -m skills.cli runtime acceptance run .botte/acceptance-001 --engine-probe .botte/engine-observation.private.json
```

For shared memory, add `--record-memory` to record the resulting observation.
For external memory, add `--context .botte/context.private.json` instead.

The command collects the controller locally, checks the challenge/source/time
bindings and refuses the same OS installation in both roles. It then records
an exclusive attempt marker before any inference or memory network request.
The selected GPU must be present in the engine observation. No second model
call is made for fallback. An unavailable endpoint or failed/truncated nonce
check remains a failure.

An existing attempt cannot be rerun, including after an interruption. Inspect
`run/state.json`, `run/report.json` when present, and the completed private
artifacts before preparing another attempt. A timeout does not prove the remote
request was cancelled. Use the existing engine's controls to check its state.

After an uncertain memory write, retry only capture with the original config:

```bash
python -m skills.cli runtime capture .botte/acceptance-001/run/config.private.json --run-dir .botte/acceptance-001/run
```

The original identity credential and exact outbox must remain available. This
does not repeat inference. A completed inference can therefore be preserved even
when its memory receipt still needs reconciliation.

## 4. Review and export

```bash
python -m skills.cli runtime acceptance export .botte/acceptance-001 --output .botte/acceptance-001.public.json
```

Export is offline and refuses failed/mismatched smoke artifacts. It rechecks
the exact saved output and message binding, the two host records and any memory
receipt. Freshness is evaluated at request time, so later review is possible.
Use the original source revision to review an old package. The summary copies
only fixed labels, bounded numeric observations and evidence/source hashes;
it omits hostnames, paths, installation tokens, project/model/profile IDs,
endpoints, credential references, raw prompts, outputs and recalled content.

Only this explicitly exported file is intended as a PR attachment. Keep the
private evidence package locally for audit and review the summary before sharing.
Do not attach the entire `.botte` directory or upload private logs to CI.

## 5. Close the actual GPU and network evidence gap

Before describing the run as inference on the intended GPU, retain native
engine evidence covering the same time window and synthetic request:

1. Record which HTTPS endpoint or existing tunnel terminates at which actual
   engine instance. Correlate its request log with the private nonce/request
   timestamp; a declared URL plus another host's inventory is insufficient.
2. Record the engine process/container, loaded target revision/quantization,
   native GPU/offload configuration and device mapping. Correlate native logs
   and GPU telemetry with that process and request. GPU presence or unrelated
   ComfyUI activity is insufficient; VRAM allocation alone does not prove GPU
   execution of the request.
3. Confirm that the direct baseline has speculation disabled. Keep operator
   identity separate from normal worker credentials and preserve existing jobs.
4. Attach a reviewed, sanitized account of these observations and their evidence
   hashes to the PR. Describe missing telemetry or ambiguous attribution as a
   remaining gap; the portable exporter does not assert these facts for you.

Use the actual installed engine's documented diagnostics rather than a generic
invented draft API. This first acceptance has no draft worker and does not
change the global scheduler. Once the direct path is understood, compare an
already supported native candidate on representative tasks using `runtime
benchmark`, with the same target, context and controlled hardware conditions.
If both profiles cannot coexist in VRAM, plan a separate controlled sequence;
this kit does not unload models or change their deployment.

## Instruction for the local agent

> Lis ce guide et la configuration privée disponible. Prends cet ordinateur
> comme contrôleur et l'hôte de modèles comme moteur. Vérifie la révision des
> sources, les chemins, l'espace libre et le profil direct à une seule carte.
> Prépare puis exécute cet essai unique dans le budget déjà autorisé. Utilise
> uniquement les accès existants, conserve les fichiers privés et ne publie que
> le bilan exporté et les preuves natives relues. Si une écriture mémoire est
> incertaine, réessaie seulement sa capture. Aucune fusion ni activation d'un
> profil spéculatif ne fait partie de cet essai.

The test module `python -m skills.llm_backends.test_acceptance` exercises these
boundaries using synthetic collectors/HTTP and a real temporary memory service.
Its Windows label fixture is not a Windows host execution claim.
