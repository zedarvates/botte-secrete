# Pre-Prompt Loader
Loads core-agent.md + agent delta for delegate_task subagents.

**Trigger:** When using delegate_task to spawn Mousquetaires or Cardinal agents.

**Usage:**
```python
from skills.loader import load_agent, load_agents_batch, suggest_agents
ctx = load_agent("porthos", project_root="/path/to/project")
tasks = load_agents_batch([("porthos","Audit",None), ("aramis","Optimize",None)])
suggestions = suggest_agents("reassess inherited architecture assumptions")
```

**Module:** `skills/loader`
**Agents:** 9 (porthos, dartagnan, aramis, athos, rochefort, milady, comte_de_wardes, cardinal, monte_cristo)

`monte_cristo` is neither blue nor red. It uses the canonical read-only agent
definition in `agents/monte-cristo.md` and receives no terminal toolset.
`suggest_agents(goal)` performs deterministic, zero-token special-agent routing
and fails closed unless the tracked trigger-evaluation gate passes.
