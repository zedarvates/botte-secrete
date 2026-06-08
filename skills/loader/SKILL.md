# Pre-Prompt Loader
Loads core-agent.md + agent delta for delegate_task subagents.

**Trigger:** When using delegate_task to spawn Mousquetaires or Cardinal agents.

**Usage:**
```python
from skills.loader import load_agent, load_agents_batch
ctx = load_agent("porthos", project_root="/path/to/project")
tasks = load_agents_batch([("porthos","Audit",None), ("aramis","Optimize",None)])
```

**Module:** `skills/loader`
**Agents:** 8 (porthos, dartagnan, aramis, athos, rochefort, milady, comte_de_wardes, cardinal)
