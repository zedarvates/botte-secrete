# Monte Cristo

Monte Cristo is Botte Secrete's independent strategic-outsider agent. Blue-team
agents improve a system and red-team agents challenge that work; Monte Cristo
questions the frame shared by both teams.

It is intended for expensive decisions: architecture resets, research programs,
major migrations, inherited complexity, and debates that remain trapped inside
the current system boundary. It is deliberately not a routine code reviewer.

## Design

1. Make a blind pass before reading previous conclusions.
2. Separate `OBSERVED`, `INFERRED`, `PROPOSED`, and `BLOCKED` evidence.
3. Identify what creates verified value and what survives only through sunk cost.
4. Produce no more than twelve falsifiable moves.
5. Give the strongest counter-case to the preferred move.
6. Stop at `INVESTIGATE` when evidence is insufficient.

The agent is read-only. Strategic freedom does not grant operational authority:
repair, replacement, and retirement proposals require explicit human approval
and must be handed to a separate implementation agent.

## Usage

Load its prompt through Botte's native agent loader:

```python
from skills.loader import load_agent

context = load_agent("monte_cristo", project_root="/path/to/project")
```

Create or validate the compact report contract:

```bash
python -m skills.monte_cristo.cli template "replace the legacy API?" --pretty
python -m skills.monte_cristo.cli validate monte-cristo-report.json
python -m skills.monte_cristo.cli route "Should we keep this inherited architecture?"
python -m skills.monte_cristo.cli eval --pretty
```

Automatic activation is allowed only after the tracked bilingual trigger corpus
passes its coverage, precision, recall, latency, and zero-false-positive gates.
This seed corpus validates routing behavior and safety wiring; its score is not
evidence that the agent's open-ended strategic conclusions are generally correct.

The canonical agent definition is [`agents/monte-cristo.md`](../../agents/monte-cristo.md).
