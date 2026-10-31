# Action memory: two-identity host pilot

This operator pilot prepares the next deployment check for
[action-consequence memory](action-consequence-memory.md). It uses the existing
authenticated API and a dedicated project. Run both clients from the same
reviewed repository commit with Python 3.10+. No package installation, model,
database migration, scheduled task or change to an agent's MCP configuration
is performed by the pilot.

## Scope and effects

`produce` previews by default. With `--execute`, it creates a new private local
workspace, executes a fixed synthetic stock calculation twice, writes report
archives and trajectory envelopes, and captures one project-visible episode
and one private episode. It deliberately discards one successful API capture
response in the client, then retries capture from the archive. This simulates
an uncertain response after a committed write; it does not interrupt the server
or prove recovery from a real network outage.

The stock fixture contains 4 units at 150 cents, 7 at 220 and 2 at 300:
13 units and 2,740 cents. The pilot temporarily alters its own output to check
stale detection, then restores it. It never edits an existing work project.
An existing destination is refused, so rerunning the command cannot silently
repeat its completed actions.

`consume` uses a separate identity. It only reads the service and the handoff
file; it executes no remembered command and writes its JSON result to stdout.
It requires the shared episode to be unchanged, the private episode to be
hidden, and both episodes to remain outside normal trusted context. Using the
producer's credential for this step must fail.

## Prepare the service and identities

Follow the [shared-service guide](shared-memory.md) for authentication and
transport. If no dedicated pilot service exists, initialize a fresh directory:

```bash
python -m skills.memory_hub.cli init --directory /absolute/private/action-memory-service --project action-pilot
```

Before starting this new service, add a reader identity on its host. The example
creates an owner-only secret without printing it; use the initialized directory
and project above. Keep the operator credential out of both agent clients.

```python
import json
import os
import secrets
from pathlib import Path
from skills.atomic_json import write_json

root = Path("/absolute/private/action-memory-service")
config = json.loads((root / "auth.json").read_text(encoding="utf-8"))
if any(p["actor_id"] == "pilot-reader" for p in config["principals"]):
    raise ValueError("Reader already configured; inspect the existing identity")
fd = os.open(root / "pilot-reader.secret", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    stream.write(secrets.token_urlsafe(48) + "\n")
config["principals"].append({"actor_id": "pilot-reader", "projects": ["action-pilot"],
    "rights": ["read"], "token_file": "pilot-reader.secret"})
write_json(root / "auth.json", config)
```

On Windows, restrict the directory and token ACLs to their intended accounts.
Start the service with the already documented loopback binding:

```bash
python -m skills.memory_hub.cli serve --directory /absolute/private/action-memory-service --port 8766
```

Give client A only its `worker.secret` and client B only its
`pilot-reader.secret`, through an existing private credential-transfer channel.
Never put token contents in Git, the handoff or model tool arguments. An existing
service needs equivalent identities and a restart after its auth configuration
changes. Do not overwrite a running service's configuration with this example.

For another machine, use the configured HTTPS origin or an existing SSH tunnel.
The tunnel's local port must match the service's expected Host port (8766 in
these examples). A TLS proxy must set the upstream Host header as described in
the shared-service guide. Connectivity and client credentials must already work.

## Client A: produce and retain evidence

From the checkout root, first preview:

```bash
python -m scripts.action_memory_pilot produce --url http://127.0.0.1:8766 --token-file /absolute/private/worker.secret --project-id action-pilot --directory /absolute/private/action-pilot-run
```

Add `--execute` to run the fixed fixture. Preview does not read credentials,
contact the service or create the destination. A successful execution returns
`complete=true`, `executions=2`, `capture_retry_replayed=true`,
`stale_detection=true` and `peer_validation=pending`.

Keep the private workspace: `plan.json`, checkpoints, immutable archives,
`interrupted-capture.json`, `capture-retry.json`, `private-capture.json` and
`producer-result.json` explain what happened. Transfer only `handoff.json` to
client B for the next step. That bounded file contains the project, opaque
episode keys and fingerprints, with no command, token, endpoint or local path.
It is observation data, not an instruction or authenticated attestation.

If a real service failure occurs, the command exits 1. Inspect the saved
checkpoint before deciding the next action. If execution completed, use the
documented `action_cli capture` with `plan.json`, the matching archive or
checkpoint, the original identity and original visibility. Do not delete the
workspace to force another execution. An incomplete producer has no successful
handoff and must not be counted as a passed host pilot.

## Client B: consume with its own identity

```bash
python -m scripts.action_memory_pilot consume --url http://127.0.0.1:8766 --token-file /absolute/private/pilot-reader.secret --project-id action-pilot --handoff /absolute/private/handoff.json
```

Require exit 0 and `complete=true`, `shared_episode_unchanged=true`,
`private_episode_hidden=true`, `normal_context_excluded=true`, and
`commands_executed=0`. A changed handoff, wrong project, mismatched pilot script,
incomplete retrieval sample, missing shared episode or visible private episode
fails the check. The source comparison covers this pilot script only; use the
same reviewed commit for the imported modules too.

Retain both result JSONs with `git rev-parse HEAD`, `python --version`, UTC time
and the actual host/transport used, in private operational evidence. A local
two-identity run demonstrates the flow but does not prove two home machines
were connected. Passing the pilot does not prove retrieval quality on a real
corpus, independent task quality, causal attribution or full deletion behavior.

The pilot leaves its two episodes and local evidence in place. For later
cleanup, use the existing `forget` operation with the owner's identity and
current versions for exactly the handoff keys. Local archives and trajectory
files remain separate copies; forgetting the service entries does not erase
the workspace. Stop only a service started specifically for this pilot.

## Reproduce the local acceptance

```bash
python -m scripts.test_action_memory_pilot
```

These tests use actual CLI subprocesses and an authenticated loopback server
with separate writer and read-only identities. They include same-identity
rejection, handoff tampering, wrong scope, preview without credentials and
refusal to re-execute an existing workspace. See the
[recorded local acceptance](validation/action-memory-host-pilot-v1.json).
