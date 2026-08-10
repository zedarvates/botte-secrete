# Décisions du Portfolio Cockpit

## ADR-P001 — Botte Secrète porte la gouvernance

**Statut :** accepté  
**Date :** 2026-08-06

Botte Secrète héberge le registre, les contrôles, les politiques et les futures fonctions de synchronisation. Elle ne remplace pas les dépôts applicatifs ni leurs décisions locales.

## ADR-P002 — Kanboard Neo est une interface, pas la source de vérité

**Statut :** accepté  
**Date :** 2026-08-06

Kanboard Neo présente les priorités et tâches aux humains. Le code, les documents techniques et l'état vérifiable restent dans les dépôts ou sources locales déclarées. Une perte de Kanboard ne doit pas faire perdre l'historique technique.

## ADR-P003 — Le registre est en JSON

**Statut :** accepté  
**Date :** 2026-08-06

JSON est retenu pour rester compatible avec la politique `stdlib-first` de Botte Secrète et permettre validation, diff, import Memory Hub et génération de vues sans dépendance YAML.

## ADR-P004 — Les projets locaux sont représentés sans chemin absolu

**Statut :** accepté  
**Date :** 2026-08-06

Le registre conserve un alias, un niveau de confidentialité et une prochaine action. Il ne stocke pas le chemin disque exact, les secrets, les données utilisateurs ni les détails d'infrastructure sensibles.

## ADR-P005 — Toutes les écritures passent par une branche

**Statut :** accepté  
**Date :** 2026-08-06

Les modifications Git passent par branche dédiée et pull request en brouillon. La fusion, la publication scientifique, le déploiement en production, les changements DNS, les migrations de données et les opérations destructives exigent une confirmation explicite.

## ADR-P006 — La mémoire partagée commence en proposition

**Statut :** accepté  
**Date :** 2026-08-06

Les éléments importés dans Memory Hub commencent au statut `proposal`. Une promotion exige provenance, portée, sensibilité et revue. Aucune conversation ou sortie de LLM ne devient automatiquement une vérité de projet.

## ADR-P007 — La recherche sépare affirmation et preuve

**Statut :** accepté  
**Date :** 2026-08-06

Toute publication distingue résultat mesuré, résultat reproduit, interprétation, hypothèse et limitation. Un commit, un DOI ou une archive ne valent pas évaluation par les pairs.

## ADR-P008 — Les snapshots ne certifient pas la qualité

**Statut :** accepté  
**Date :** 2026-08-06

Un snapshot confirme qu'un changement a été observé dans l'historique. Il ne prouve pas à lui seul que les tests passent, que les performances sont reproductibles ou que le code est prêt pour la production.

## ADR-P009 — Limite initiale de trois chantiers principaux

**Statut :** proposé  
**Date :** 2026-08-06

Le portefeuille vise un maximum de trois chantiers principaux simultanés : produit cœur, revenus/livraison et recherche/publication. La règle deviendra `accepté` après validation du propriétaire.
