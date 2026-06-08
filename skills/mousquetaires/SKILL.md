# Les Quatre Mousquetaires — Blue Team
Multi-agent pipeline: Audit → Fix → Optimize → Consolidate.

**Trigger:** When the user wants code audit, automated fixes, or token optimization.

**Agents:**
- 🥊 Porthos: Auditor (fallow-like analyzers)
- ⚔️ d'Artagnan: Developer (auto-fix)
- 📿 Aramis: Optimizer (token reduction)
- 👑 Athos: Orchestrator (pipeline coordination)

**Workflow:** `porthos ∥ aramis → dartagnan → athos`

**Module:** `skills/mousquetaires`
**CLI:** `python3 -m skills.mousquetaires.cli run <project> --output <dir>`
**Pre-prompts:** `skills/mousquetaires/prompts/` + `skills/core-agent.md`
