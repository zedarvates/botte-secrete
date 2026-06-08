# Les Mousquetaires du Cardinal — Red Team
Adversarial agents that challenge the Blue Team's work.

**Trigger:** After Blue Team pipeline, for critical code or health < 70.

**Agents:**
- 🗡️ Rochefort: Counter-auditor (finds what Porthos missed)
- 🔪 Milady: Counter-developer (finds what d'Artagnan broke)
- 🕯️ Comte de Wardes: Counter-optimizer (finds over-optimizations)
- 👑 Le Cardinal: Orchestrator (coordinates, verdict)

**Workflow:** `rochefort ∥ milady ∥ comte_de_wardes → cardinal`

**Module:** `skills/cardinal`
**Pre-prompts:** `skills/cardinal/prompts/` + `skills/core-agent.md`
