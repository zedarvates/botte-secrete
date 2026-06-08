# JSON Report Schemas — Compact Output Formats

> Loaded once. All agents use these schemas.
> Keys are shortened for token efficiency.

## AuditReport (Porthos → `audit-report.json`)
```json
{
  "h": {"s": 59, "g": "C"},
  "st": {"f": 40, "l": 3841},
  "fn": [
    {"f": "core.py:42", "s": "err", "t": "dead", "d": "calc_tax() - 0 refs"},
    {"f": "utils.py:88", "s": "warn", "t": "dup", "d": "parse_input() x3"}
  ],
  "by": {"dead": 88, "dup": 5, "cmp": 0, "sec": 0, "bnd": 0, "flg": 1},
  "rc": [
    {"p": "P0", "d": "Nettoyer 88 dead code"},
    {"p": "P1", "d": "Dédupliquer 5 blocs"}
  ]
}
```
Key legend: h.s=health score, h.g=grade, st.f=files, st.l=lines, fn=findings, f=file:line, s=severity(err/warn/info/crit), t=type(dead/dup/cmp/sec/bnd/flg), d=description, by=counts by type, rc=recommendations, p=priority(P0/P1/P2)

## FixReport (d'Artagnan → `fix-report.json`)
```json
{
  "ok": 26, "sk": 1, "fc": 15,
  "fx": [
    {"f": "core.py:42", "a": "CMT", "t": "grep -r calc_tax → 0", "s": "ok"},
    {"f": "utils.py:88", "a": "SKP", "r": "appelé via getattr()", "s": "skip"}
  ],
  "uf": [{"f": "aramis_optimize.py", "r": "dedup manuel"}]
}
```
Key legend: ok=fixed, sk=skipped, fc=files_changed, fx=fixes, a=action(CMT=comment/DEL=delete/SKP=skip), t=test verification, s=status(ok/skip/fail), r=reason, uf=unfixed

## OptimizationPlan (Aramis → `optimization-plan.json`)
```json
{
  "tk": {"b": 78000, "a": 21000, "pct": 73},
  "sk": {"ld": 8, "ex": 23},
  "sv": {"skills": 73, "build": 0, "git": 0},
  "ac": [
    {"p": "P0", "d": ".skills-profile: exclure 23 skills", "i": "-73% tokens"},
    {"p": "P1", "d": "scanner.py:95 — dead code", "i": "-200 tokens"}
  ]
}
```
Key legend: tk.b=tokens_before, tk.a=tokens_after, tk.pct=saved_percent, sk.ld=skills_loaded, sk.ex=skills_excluded, sv=savings_by_category, ac=actions, i=impact

## CounterAuditReport (Rochefort → `counter-audit.json`)
```json
{
  "ps": 72,
  "fn": [{"f": "core.py:88", "s": "err", "d": "getattr() appel dynamique"}],
  "un": [{"f": "auth.py:30", "w": "warn", "s": "err", "d": "secret via log"}],
  "mf": ["scripts/deploy.sh"],
  "v": "PARTIELLEMENT FIABLE"
}
```
Key legend: ps=porthos_score, fn=false_negatives, un=underestimated, w=was, s=should, mf=missed_files, v=verdict

## CounterFixReport (Milady → `counter-fix.json`)
```json
{
  "ds": 85,
  "rg": [{"f": "cli.py:26", "a": "CMT", "b": "cli.py:88 — import manquant"}],
  "ic": [{"f": "utils.py:42", "d": "Code commenté appelé par core.py:88"}],
  "se": [],
  "v": "COMPÉTENT"
}
```
Key legend: ds=dartagnan_score, rg=regressions, a=action_that_caused_it, b=what_broke, ic=incomplete_fixes, se=side_effects, v=verdict

## CounterOptimReport (Comte de Wardes → `counter-optim.json`)
```json
{
  "as": 78,
  "ov": [{"f": "hooks.py:15", "d": "Supprimé mais PluginLoader.getattr()"}],
  "we": [{"sk": "github-workflow", "r": ".github/workflows/ci.yml présent"}],
  "fd": [{"f": "events.py:30", "d": "importlib.import_module() → pas dead"}],
  "v": "PRUDENT"
}
```
Key legend: as=aramis_score, ov=over_optimizations, we=wrongly_excluded, sk=skill_name, r=reason, fd=false_dead, v=verdict

## ConsolidatedReport (Athos → `consolidated.json`)
```json
{
  "pl": "porthos→dartagnan→aramis",
  "sc": {"h": 59, "f": "26/27", "t": "73%"},
  "v": "À AMÉLIORER",
  "ac": [
    {"p": "P0", "ag": "dartagnan", "d": "1 finding non corrigé"},
    {"p": "P1", "ag": "porthos", "d": "Health 59 — ré-auditer"}
  ],
  "rt": true
}
```
Key legend: pl=pipeline, sc=scores(h=health, f=fixed, t=tokens_saved), v=verdict, ac=actions, ag=agent, rt=red_team_activated

## RedTeamReport (Le Cardinal → `redteam.json`)
```json
{
  "bs": 65,
  "v": "PARTIELLEMENT FIABLE",
  "ag": {
    "rochefort": {"ps": 72, "fn": 2, "un": 1},
    "milady": {"ds": 85, "rg": 1, "ic": 1},
    "wardes": {"as": 78, "ov": 1, "we": 1}
  },
  "ac": [
    {"p": "P0", "ag": "porthos", "d": "Corriger 2 faux négatifs"},
    {"p": "P1", "ag": "dartagnan", "d": "1 régression: cli.py:26"}
  ]
}
```
Key legend: bs=blue_score, v=verdict, ag=agents, ps=porthos_score, fn=false_negatives, un=underestimated, ds=dartagnan_score, rg=regressions, ic=incomplete, as=aramis_score, ov=over_optimizations, we=wrongly_excluded, ac=actions, ag=target_agent
