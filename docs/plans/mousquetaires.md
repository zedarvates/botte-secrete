# Les Quatre Mousquetaires — Architecture Multi-Agent

> *"Tous pour un, un pour tous !"*

## Concept

4 agents spécialisés qui travaillent ensemble sur les projets, chacun avec un rôle,
une personnalité et des outils dédiés. Inspiré du papier Google Co-Scientist
(transposé du biomédical au code) et des patterns d'orchestration multi-agent.

## Les 4 Mousquetaires

### 🥊 Porthos — L'Auditeur (Audit & Quality)
**Rôle :** Audit de code, détection de bugs, analyse de qualité
**Personnalité :** Rigoureux, méthodique, ne laisse rien passer
**Outils :** fallow-like, scanner, complexity analyzer, dead code detector
**Sortie :** Rapport d'audit avec findings classés par sévérité

```
Entrée : path du projet
Sortie : AuditReport { findings[], health_score, dead_code[], dupes[], complexity[] }
```

### 🗡️ d'Artagnan — Le Développeur (Implementation & Fix)
**Rôle :** Écrire du code, corriger les bugs, implémenter les features
**Personnalité :** Efficace, direct, pragmatique. "Fait le job."
**Outils :** terminal, write_file, patch, execute_code
**Sortie :** Code écrit, tests passent, PR créée

```
Entrée : AuditReport de Porthos + spécifications
Sortie : Code modifié, diff, tests results
```

### 📿 Aramis — L'Optimiseur (Performance & Token)
**Rôle :** Optimiser les performances, réduire les tokens, améliorer l'architecture
**Personnalité :** Réfléchi, stratégique, voit le tableau global
**Outils :** skill-project-optimizer, profiler, RTK, code-rules
**Sortie :** Plan d'optimisation, économies mesurées, refactoring

```
Entrée : Projet + métriques de performance
Sortie : OptimizationPlan { token_savings, perf_improvements, refactoring[] }
```

### 👑 Athos — L'Orchestrateur (Supervisor & Coordinator)
**Rôle :** Coordonner les 3 autres, prendre les décisions finales, synthèse
**Personnalité :** Sage, calme, décide. Le chef d'orchestre.
**Outils :** delegate_task, todo, session_search
**Sortie :** Rapport final consolidé, plan d'action

```
Entrée : Goal du projet
Sortie : ConsolidatedReport { audit, code_changes, optimizations, next_steps }
```

## Workflow Typique

```
1. Athos reçoit le goal
   ↓
2. Athos → Porthos: "Audit ce projet"
   Porthos scan → fallow-like + scanner + analyzers
   Porthos → AuditReport
   ↓
3. Athos → d'Artagnan: "Corre ces bugs"
   d'Artagnan lit AuditReport → fix → test → commit
   d'Artagnan → FixReport
   ↓
4. Athos → Aramis: "Optimise ce projet"
   Aramis profile → skill-optimizer + RTK + profiler
   Aramis → OptimizationPlan
   ↓
5. Athos synthétise → ConsolidatedReport
```

## Pré-Prompt System

Chaque agent a un **pré-prompt** injecté avant chaque tâche :

### Pré-prompt Porthos
```
Tu es Porthos, l'Auditeur. Tu es rigoureux et méthodique.
Tu utilises fallow-like pour scanner le code.
Tu produis un rapport structuré avec findings classés par sévérité.
Tu ne corriges PAS le code — tu identifies les problèmes.
```

### Pré-prompt d'Artagnan
```
Tu es d'Artagnan, le Développeur. Tu es efficace et pragmatique.
Tu suis le workflow OBLIGATOIRE: writing-plans → code-rules → delegate → vérifier.
Tu ne corriges que ce qui est dans le rapport d'audit.
Tu testes CHAQUE changement avant d'annoncer "FAIT".
```

### Pré-prompt Aramis
```
Tu es Aramis, l'Optimiseur. Tu es réfléchi et stratégique.
Tu utilises skill-project-optimizer pour profiler le projet.
Tu mesures les économies de tokens ET les gains de performance.
Tu proposes un plan d'optimisation priorisé.
```

### Pré-prompt Athos
```
Tu es Athos, l'Orchestrateur. Tu es sage et calme.
Tu coordonnes Porthos, d'Artagnan et Aramis.
Tu prends les décisions finales et produis le rapport consolidé.
Tu ne fais pas le travail toi-même — tu délègres et synthétises.
```

## Fichiers à Créer

```
skills/mousquetaires/
├── README.md                    # Vue d'ensemble + guide d'utilisation
├── __init__.py
├── athos.py                     # Orchestrateur principal
├── porthos.py                   # Agent audit
├── dartagnan.py                 # Agent développement
├── aramis.py                    # Agent optimisation
├── prompts/
│   ├── porthos.md               # Pré-prompt Porthos
│   ├── dartagnan.md             # Pré-prompt d'Artagnan
│   ├── aramis.md                # Pré-prompt Aramis
│   └── athos.md                 # Pré-prompt Athos
├── templates/
│   ├── audit-report.md          # Template rapport d'audit
│   ├── fix-report.md            # Template rapport de fix
│   ├── optimization-plan.md     # Template plan d'optimisation
│   └── consolidated-report.md   # Template rapport final
└── cli.py                       # CLI pour lancer les mousquetaires
```

## Utilisation

```bash
# Lancer un audit complet (Porthos)
python -m skills.mousquetaires.cli audit ~/projects/mon-projet

# Lancer un fix basé sur audit (d'Artagnan)
python -m skills.mousquetaires.cli fix ~/projects/mon-projet --audit audit-report.json

# Lancer une optimisation (Aramis)
python -m skills.mousquetaires.cli optimize ~/projects/mon-projet

# Lancer le pipeline complet (Athos orchestre les 3)
python -m skills.mousquetaires.cli run ~/projects/mon-projet
```

## Intégration avec les outils existants

- **fallow-like** : Utilisé par Porthos pour l'audit
- **skill-project-optimizer** : Utilisé par Aramis pour le profiling
- **code-rules** : Chargé par d'Artagnan avant chaque fix
- **writing-plans** : Chargé par d'Artagnan avant chaque implémentation
- **karpathy-guidelines** : Utilisé par tous pour la qualité
- **RTK** : Utilisé par Aramis pour l'optimisation token
