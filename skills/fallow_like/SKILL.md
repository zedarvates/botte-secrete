# Fallow-Like Static Analyzers
9 code analyzers: dead code, duplication, complexity, secrets, **taint (data-flow security)**, boundaries, feature flags, hot paths, blast radius.

**Trigger:** Code audit, quality/security checks, pre-commit analysis.

**Analyzers:**
- DeadCodeAnalyzer, DuplicationAnalyzer, ComplexityAnalyzer
- SecretsAnalyzer, **TaintAnalyzer**, BoundaryAnalyzer, FeatureFlagAnalyzer
- HotPathAnalyzer, BlastRadiusAnalyzer

**Module:** `skills/fallow_like`
**Health:** `calculate_health()` → score 0-100 + grade A-F
**Output:** JSON (compact), SARIF, or markdown (verbose)

## Taint / data-flow security (neuro-symbolic, local-first)

Inspired by RepoAudit/DeepAudit, in botte's local-first shape:

- **symbolic (0 tokens)** — Python `ast` traces attacker-controlled *sources*
  (`sys.argv`, `os.environ`/`getenv`, `input`, framework `request.*`) into
  dangerous *sinks* (`subprocess`/`os.system`/`eval`/`exec`, SQL `execute`,
  `pickle`/`yaml.load`/`marshal`, `urlopen`/`requests`) and flags
  insecure-by-default calls (`shell=True` + dynamic, `yaml.load` without a safe
  Loader). Each finding is **CWE-tagged** (78/89/94/502/918). No compilation.
- **neuro (0 cloud tokens, optional)** — `--judge` asks a LOCAL model to confirm
  each candidate (exploitable vs sanitized); it only annotates/adjusts confidence.

```bash
python -m skills.fallow_like.cli taint .            # data-flow security scan
python -m skills.fallow_like.cli taint . --judge    # + local-model confirmation
```

Exposed via [[llm_mcp]] as `security_scan`. v1 does intra-procedural data flow
for Python (botte's primary language); other languages are the next iteration.
