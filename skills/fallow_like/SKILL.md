# Fallow-Like Static Analyzers
8 code analyzers: dead code, duplication, complexity, secrets, boundaries, feature flags, hot paths, blast radius.

**Trigger:** Code audit, quality checks, pre-commit analysis.

**Analyzers:**
- DeadCodeAnalyzer, DuplicationAnalyzer, ComplexityAnalyzer
- SecretsAnalyzer, BoundaryAnalyzer, FeatureFlagAnalyzer
- HotPathAnalyzer, BlastRadiusAnalyzer

**Module:** `skills/fallow_like`
**Health:** `calculate_health()` → score 0-100 + grade A-F
**Output:** JSON (compact) or markdown (verbose)
