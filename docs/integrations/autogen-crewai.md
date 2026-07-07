# AutoGen / CrewAI Connector

Stub for integrating Botte tools into AutoGen or CrewAI agents.

## AutoGen

```python
from autogen import AssistantAgent
from skills.auto_router import auto_route, auto_run

class BotteAgent(AssistantAgent):
    def route_task(self, task: str) -> dict:
        return auto_route(task)

    def execute_task(self, task: str) -> dict:
        return auto_run(task)

agent = BotteAgent("botte-router")
result = agent.route_task("classify: bug or feature?")
```

## CrewAI

```python
from crewai import Tool
from skills.context_profiler import profile_host

botte_profiler = Tool(
    name="Context Profiler",
    func=lambda project=".": profile_host(project),
    description="Measure always-on token prefix cost"
)
```
