# 🧦 Spec — Harnais auto anti-hallucination pour modèles locaux

> **Date :** 26 Juin 2026
> **Sources :**
> - Audit Hermes — « les agents locaux basés sur Gemma hallucinent beaucoup »
> - Travail de session — NN belt, featurizer (`skills/botte_nn/features.py`), feedback implicite (`active_learning.record_feedback`)
> - Existant — `auto_router`, `fusion`, `ingest`/Qdrant, `cwe_kb`, `nlp_deterministic`, `fallow_like`, `meta_harness/pipeline_dsl.py`

---

## 🎯 Problème

Les petits modèles locaux (Gemma 2B/9B, Qwen 0.5–7B…) hallucinent surtout sur :

- **le factuel** — ils inventent des API, des chemins, des numéros de version ;
- **le long-form** — plus la génération est longue, plus la dérive est probable ;
- **l'agentique** — ils citent des fichiers/fonctions qui n'existent pas.

La cause n'est pas « le modèle est nul » : c'est qu'on lui demande de **rappeler depuis sa mémoire paramétrique** (peu fiable à cette taille) en **génération libre** (aucune contrainte), **sans faits** sous les yeux et **sans vérification** derrière.

## 💡 Principe

> **On ne corrige pas le modèle. On corrige le harnais autour.**

Deux leviers structurels :

1. **Transformer « rappeler » en « extraire/valider ».** Un petit modèle est mauvais pour *se souvenir* d'un fait, mais bon pour *extraire* un fait d'un texte qu'on lui fournit. On déplace la difficulté hors du modèle.
2. **Rendre la sortie invalide impossible.** Schéma JSON imposé, ensemble de labels fermé, grammaire contrainte → le modèle ne *peut pas* produire de la prose libre qui dérive.

Et quand le doute subsiste : **abstenir + escalader** vaut toujours mieux que mentir.

---

## 🏗️ Architecture — 5 couches

```
        tâche → [0 GATE] → [1 CONTRAINDRE] → [2 ANCRER] → LLM local
                                                              │
   réponse ← [4 ABSTENIR / ESCALADER] ← [3 VÉRIFIER] ◄───────┘
                      │ (échec)               │ (chaque échec = label)
                fusion.cascade → cloud      [5 APPRENDRE] → active_learning
```

| # | Couche | Rôle | Déjà dans le repo | Net-nouveau |
|---|--------|------|-------------------|-------------|
| 0 | **Gate** | ne pas demander ce que le modèle rate ; au-delà d'un effort/risque, escalade directe | ✅ `auto_router/effort.py` + `nn_belt` | — |
| 1 | **Contraindre** | sortie = JSON schema / labels fermés / grammaire GBNF | — | ⚠️ `response_format` dans `client.chat()` |
| 2 | **Ancrer (RAG)** | injecter les faits ; « réponds **uniquement** depuis ce contexte, sinon `NEEDS_ESCALATION` » | ✅ `ingest`/Qdrant, `cwe_kb` | — |
| 3 | **Vérifier** | le JSON parse ? chaque preuve est **dans** le contexte ? fichier/symbole cité **existe** ? code **parse** (ast) ? | ✅ `nlp_deterministic`, `fallow_like`, `features.featurize` | ⚠️ module `verifier` (composition) |
| 4 | **Abstenir / Escalader** | échec de vérif ou confiance basse → escalade, jamais une réponse fausse | ✅ `fusion.cascade` | seuil **calibré** (cf. audit Hermes #3) |
| 5 | **Apprendre** | chaque abstention/rejet/override = exemple labellisé | ✅ `active_learning.record_feedback` | — |

**3 des 5 couches existent déjà** ; il reste 2 briques + le câblage.

---

## 📋 La spec déclarative — `HarnessSpec`

Un harnais est un **fichier**, pas du code — réutilisable et versionnable par modèle/tâche. Format aligné sur `meta_harness/pipeline_dsl.py`.

```yaml
harness: local-extract-v1          # id
model: gemma-2-9b                  # backend ciblé (ou 'auto' → registry)

gate:
  max_effort: 0.4                  # effort estimé au-dessus → cloud direct, on n'essaie pas
  allow_task_types: [extract, classify, summarize_grounded]

output:
  format: json_schema              # free_text | json_object | json_schema | enum
  schema:                          # si json_schema
    type: object
    required: [answer, evidence]
    properties:
      answer:   { type: string }
      evidence: { type: array, items: { type: string } }
  enum: null                       # si format=enum : liste fermée de réponses
  max_tokens: 512

ground:
  source: qdrant://project         # qdrant://… | files:… | none
  top_k: 6
  rule: answer_from_context_only   # interdit le rappel « de mémoire »
  escalate_token: NEEDS_ESCALATION # le modèle DOIT répondre ça s'il ne sait pas

verify:                            # toutes doivent passer
  - schema                         # parse + conforme au schéma
  - evidence_in_context            # chaque 'evidence' apparaît littéralement dans le contexte
  - citations_exist                # fichiers/symboles cités existent sur le disque
  - code_parses                    # si la sortie contient du code → ast.parse OK

self_consistency:                  # optionnel
  samples: 3                       # N tirages (temperature > 0)
  agree: 2                         # consensus requis ; sinon → on_fail

on_fail: escalate                  # escalate | abstain | return_best
escalate_to: STANDARD              # tier cloud cible (fusion.cascade)

learn: true                        # logue l'issue vers active_learning (binary_router + le futur 'hallucination_detector')
```

### Champs — résumé

- **`gate`** — pré-filtre 0-token (réutilise `effort` + le belt). Hors périmètre = pas d'appel local.
- **`output`** — la couche la plus rentable : `enum`/`json_schema` rendent la dérive *impossible*.
- **`ground`** — bascule « rappel » → « extraction ». `escalate_token` donne au modèle une **sortie de secours honnête**.
- **`verify`** — checks **déterministes** (0 token), composés depuis l'existant.
- **`self_consistency`** — le désaccord entre tirages est un signal d'incertitude bon marché.
- **`on_fail` / `escalate_to`** — la politique de repli.
- **`learn`** — ferme la boucle : les échecs deviennent des données d'entraînement.

---

## ⚙️ Exécuteur — flux

`skills/local_harness/executor.py` (nouveau), `run(spec, task, context=None) -> HarnessResult` :

```
1. GATE      effort(task) ; si > spec.gate.max_effort ou task_type interdit → escalate
2. GROUND    si spec.ground.source : récupère top_k passages, construit le prompt ancré
3. CONSTRAIN appelle client.chat(prompt, response_format=spec.output, temperature=…)
             (répété spec.self_consistency.samples fois si défini)
4. VERIFY    applique chaque check de spec.verify ; consensus si self_consistency
5. DECIDE    tout passe → réponse ; sinon selon spec.on_fail :
                escalate → fusion.cascade(task, escalate_to)
                abstain  → {answer: null, reason: 'verification_failed'}
6. LEARN     si spec.learn : record_feedback(...) (succès local / échec→escalade)
```

`HarnessResult` : `{ answer, source: local|escalated|abstained, verifications: {...}, samples, escalated, reason }` — **traçable** (on sait *pourquoi* une réponse a été acceptée/rejetée).

---

## 🔨 Net-nouveau à construire (3 pièces)

1. **Sortie structurée — `skills/llm_backends/client.py`**
   Ajouter `response_format` à `chat()` : passer `{"type": "json_object"}` ou `{"type":"json_schema","json_schema":…}` dans le body OpenAI `/v1`. Pour llama.cpp : champ `grammar` (GBNF) généré depuis le schéma. *Levier n°1, ~30 lignes.*

2. **Module `verifier` — `skills/local_harness/verifier.py`**
   Compose l'existant, 0 token :
   - `schema_ok(out, schema)` ← `features.featurize`-style ;
   - `evidence_in_context(out, ctx)` ← `nlp_deterministic` (extraction/normalisation) ;
   - `citations_exist(out, repo)` ← `fallow_like` (résolution symboles/chemins) ;
   - `code_parses(out)` ← `ast.parse` / arbre Tree-sitter.

3. **`HarnessSpec` + exécuteur — `skills/local_harness/`**
   Loader YAML (réutilise le parseur de `pipeline_dsl`), `executor.py`, et un outil MCP `harness_run`. Specs livrées dans `examples/harnesses/`.

Le reste — **gate, RAG, escalade, apprentissage — existe déjà** et n'a qu'à être câblé.

---

## 🗺️ Roadmap

- [ ] **P1 — Contraindre.** `response_format`/GBNF dans `client.chat()` + tests. *(Plus gros gain, plus petit effort.)*
- [ ] **P2 — Vérifier.** Module `verifier` (schema, evidence_in_context, citations_exist, code_parses) + tests.
- [ ] **P3 — Exécuteur.** `HarnessSpec` (YAML) + `executor.py` enchaînant les 5 couches ; outil MCP `harness_run`.
- [ ] **P4 — Ancrer.** Brancher `ingest`/`cwe_kb` comme sources `ground` ; prompt ancré + `escalate_token`.
- [ ] **P5 — Apprendre.** `hallucination_detector` (micro-NN) entraîné sur les rejets de vérif ; alimente le Gate (couche 0).
- [ ] **P6 — Bench.** 50 tâches factuelles/agentiques → taux d'hallucination **avec / sans** harnais, par modèle local. *(Aussi le contenu Reddit/X.)*

## 🚫 Non-objectifs

- **Pas de fine-tuning du modèle** — le harnais est externe, marche avec n'importe quel backend OpenAI `/v1`.
- **Pas de « zéro hallucination »** — l'objectif est de **détecter et escalader**, pas de garantir l'infaillible.
- **Pas de dépendance cloud obligatoire** — sans clé cloud, `on_fail` dégrade en `abstain` (réponse honnête « je ne sais pas ») plutôt qu'en réponse inventée.

## ⚠️ Risques

- **Sur-escalade** — un harnais trop strict envoie tout au cloud (coût). Mitigation : le Gate + le seuil calibré + la boucle d'apprentissage ajustent le périmètre local au fil du temps.
- **Latence** — `self_consistency` multiplie les appels locaux. Réservé aux tâches critiques ; `samples: 1` par défaut.
- **Coût de vérification** — les checks restent déterministes (0 token) ; le budget est en CPU local, négligeable vs un appel LLM.

---

*Dépendances : référence le NN belt, `features.py` et `active_learning.record_feedback` introduits dans la PR `integration/all-improvements` (à merger avant P3/P5).*
