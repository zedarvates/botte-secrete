# Structure `.botte/` — schéma complet

```
.botte/
├── policy.md              # Règles partagées (routing, budget, hygiene)
├── events.jsonl           # Décisions de routing (une par ligne JSON)
├── events.1.jsonl         # Rotation après 5 MB
├── cache/                 # Cache de scans (checkup, bench)
│   ├── <hash>_audit-report.json
│   └── <hash>_scan-result.json
├── reports/               # Rapports générés
│   ├── checkup-<ts>.html
│   ├── fixes-<ts>.md
│   └── checkup-latest.json
├── metrics/               # Métriques persistantes
│   └── trends.json        # Snapshots périodiques
├── fleet/                 # Registre multi-projet
│   └── <project>.json     # Un par projet enregistré
└── models/                # Poids micro-NN (optionnel)
    └── *.json
```

## Fichiers générés (pas commités)
- `.botte-cache/` — cache de build
- `fix-report.json` — sortie de dartagnan_fix (racine, transitoire)

## Fichiers commités
- `.botte/policy.md` — règles partagées (explicitement un-ignoré dans .gitignore)
