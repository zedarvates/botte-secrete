---
name: security_scanner
description: Scan Python skills and MCP servers for malicious code — dangerous imports, network exfiltration, filesystem abuse, subprocess injection, obfuscation, crypto weakness, environment leaks, and supply-chain attacks. Use when auditing code for security, running pre-commit hooks, or preparing CI/CD security gates.
tags: [security, audit, scan, static-analysis, supply-chain]
---

# security_scanner — code security scanner

Détecte les patterns malveillants dans les skills Python, MCP servers, et pipelines.
Combinaison de regex pattern-matching et d'analyse AST Python.

## Usage

```bash
# Scanner un dossier
python -m skills.security_scanner.cli scan skills/ --fail-on critical
python -m skills.security_scanner.cli scan . --format json
python -m skills.security_scanner.cli scan src/main.py --verbose

# Audit complet
python -m skills.security_scanner.cli audit skills/ --format compact
```

## Checks effectués

| Check | Regex | AST | Exemple |
|-------|-------|-----|---------|
| `dangerous_imports` | ✅ | ✅ | `eval(user_input)`, `exec(code)` |
| `network_exfil` | ✅ | ✅ | `requests.post("evil.com")` |
| `filesystem_abuse` | ✅ | ✅ | `open("/etc/passwd", "w")` |
| `subprocess_injection` | ✅ | ✅ | `shell=True` avec input concaténé |
| `obfuscation` | ✅ | ❌ | `base64.b64decode`, `bytes([...]).decode()` |
| `crypto_weak` | ✅ | ❌ | `RSA.generate(512)`, `MD5` |
| `env_leak` | ✅ | ✅ | `print(os.environ["SECRET"])` |
| `supply_chain` | ✅ | ❌ | Imports de packages inconnus |

## Architecture

```
security_scanner/
├── scanner.py     # Orchestrateur : itère fichiers, appelle analyseurs
├── patterns.py    # Base de patterns (regex + metadata)
├── ast_checker.py # Analyse Python AST
├── report.py      # Compilation du rapport
├── rules/         # YAML rules extensibles
├── cli.py         # CLI argparse
└── test_security_scanner.py
```

## Intégration

```bash
# Pre-commit hook
python -m skills.security_scanner.cli scan . --fail-on critical --format compact

# CI/CD
python -m skills.security_scanner.cli scan skills/ --format json --output security-report.json

# Nightly audit
python -m skills.security_scanner.cli audit . --format markdown
```

## Pitfalls

1. **Faux positifs** — `eval` dans un contexte contrôlé (ex: `eval("1+1")`) est signalé.
   L'AST checker permet de filtrer les évaluations statiques.
2. **Fichiers binaires** — Skip automatique (.pyc, .so, .dll, images).
3. **Dossiers ignorés** — .git, node_modules, __pycache__, .venv.
4. **Performance** — Utilise `concurrent.futures` pour scanner en parallèle.
