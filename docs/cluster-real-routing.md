# Real cluster routing — multi-machine task distribution

## Current state

`skills/cluster/` detects machines on the local network and registers backends.
`skills/cluster/agent.py` delegates tasks to remote agents.

## Next steps for real cluster

1. **Load-aware routing**: query `/health` on each machine before routing,
   pick the least-loaded one (lowest CPU/RAM usage).
2. **Failover**: if a machine is unreachable, automatically retry on another.
3. **Heterogeneous routing**: send vision tasks to Hailo-8 machines, code tasks
   to GPU machines, small NLP to CPU-only machines.
4. **Redis pub/sub**: replace polling with event-driven task dispatch.

## Configuration

```yaml
# ~/.botte/cluster.yaml
machines:
  - host: 192.168.1.47
    role: vision   # Hailo-8
  - host: 192.168.1.66
    role: llm      # GPU
  - host: 192.168.1.100
    role: worker   # CPU-only
```
