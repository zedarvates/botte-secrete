---
name: cluster
layer: DECIDE
description: Treat the homelab/micro-cluster as one schedulable resource — discover every reachable machine and spread cheap work across them (least-recently-used first) so idle boxes get the next task, recovering wasted local capacity instead of paying the cloud. Use to see cluster status, route a task to the idlest machine, or hand a task to a trusted agent on another machine. Also use when the user mentions homelab, cluster, idle machines, load balancing, or distributing work across machines.
---

# cluster — the homelab as one schedulable resource

Idle local capacity is recovered cost. Instead of always hitting the same backend
(or the cloud), spread work across every reachable machine.

```bash
python -m skills.cluster.cli status --subnet      # all machines + recommended target
python -m skills.cluster.cli pick --strategy lru  # spread to the idlest machine
python -m skills.cluster.cli pick --strategy latency
python -m skills.cluster.cli delegate 192.168.1.38 "restart the model server"
```

## How it routes

- **status** groups discovered backends (LM Studio, Ollama, LocalAI, ComfyUI,
  Qdrant…) by host → the cluster view, with latency and the recommended target.
- **pick `lru`** chooses the *least-recently-used* capable chat backend, so the
  next task lands on an under-used box — work spreads across the cluster.
- **pick `latency`** chooses the most responsive backend.

## Delegation (hand-off only)

`delegate(host, task)` POSTs `{"task": …}` to a machine's agent endpoint
(`BOTTE_AGENT_<host>` env or `--url`). It **never runs privileged maintenance
itself** — wire a trusted agent (e.g. Hermes, which has the rights to do simple
machine maintenance) on each box to receive and execute tasks. No endpoint
configured → safe no-op that tells you how to wire one.

> Security: elevated-rights machine maintenance stays in *your* agent on each
> machine; botte only routes and hands off.


## Reference machine-agent (deploy on each box)

Until your agent (Hermes) exposes an endpoint, run the bundled receiver — it
accepts delegated tasks **safely**: a whitelist of *named* read-only actions
(`ping`, `machine_status`, `disk`, `local_backends`), **never arbitrary shell**,
loopback by default, token-gated for any non-loopback bind. Privileged
maintenance handlers are deliberately absent until you scope the policy.

```bash
python -m skills.cluster.agent serve --host 0.0.0.0 --token "$BOTTE_AGENT_TOKEN"
# then from the cluster:
python -m skills.cluster.cli delegate <host> machine_status --url http://<host>:8799/task
```


### Privileged maintenance (operator-approved, confirm-gated)

To let the cluster trigger real maintenance (restart a model server, pull/update
a model, clear a cache), the **operator** pre-approves a named whitelist on each
machine — the remote caller can only trigger commands **by name** and must pass
`confirm: true`. There is no arbitrary shell from the network.

```bash
# operator, on the machine (example: examples/cluster/maintenance-commands.json)
python -m skills.cluster.agent serve --host 0.0.0.0 --token "$BOTTE_AGENT_TOKEN"        --commands examples/cluster/maintenance-commands.json
# caller: list what's permitted, then run with confirmation
#   {"task":"list_commands"}
#   {"task":{"action":"run","args":{"name":"restart_ollama","confirm":true}}}
```

Defaults are safe: with no `--commands` file, **no** maintenance is possible —
only the read-only actions. Maintenance on a non-loopback bind requires a token.

Exposed via [[llm_mcp]] as `cluster_status`. Related: [[llm_backends]]
(discovery), [[infra_advisor]] (per-machine tips), [[auto_router]].
