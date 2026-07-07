# LangChain Tool Connector (stub)

For integrating Botte tools into LangChain agents:

```python
from langchain.tools import tool
from skills.auto_router import auto_route

@tool
def botte_route_task(task: str, task_type: str = "") -> dict:
    """Route a task to the cheapest available backend (local or cloud)."""
    return auto_route(task, task_type)

@tool
def botte_context_profiler(project: str = ".") -> dict:
    """Measure always-on token prefix cost."""
    from skills.context_profiler import profile_host
    return profile_host(project)
```

## n8n Webhook

Expose `auto_route` as an n8n webhook:

1. Create a webhook node in n8n
2. Set URL to `http://localhost:8769/auto_route`
3. POST `{"prompt": "...", "task_type": "..."}`
4. Returns routing decision as JSON
