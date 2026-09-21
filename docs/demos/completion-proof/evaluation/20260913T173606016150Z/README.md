# Mesure de fiabilité — corpus synthétique

20 scénarios préparés et étiquetés, pas un échantillon de production ni un test indépendant.

Une détection signifie que Botte refuse une clôture injustifiée. Une fausse alerte est un cas valable refusé ; un problème manqué est un cas injustifié accepté.

| Groupe | Cas | Problèmes détectés | Fausses alertes | Problèmes manqués | Cas valables acceptés |
|---|---:|---:|---:|---:|---:|
| Contrat couvert | 17 | 12 | 0 | 0 | 5 |
| Limites connues | 3 | 0 | 0 | 3 | 0 |

## Résultats cas par cas

| Cas | Groupe | Attendu | Observé |
|---|---|---|---|
| valid | contract | Accepter | Accepté |
| legacy_valid | contract | Accepter | Accepté |
| mixed_skipped | contract | Accepter | Accepté |
| unicode_source | contract | Accepter | Accepté |
| two_sources | contract | Accepter | Accepté |
| missing_receipt | contract | Refuser | Refusé |
| missing_log | contract | Refuser | Refusé |
| missing_source | contract | Refuser | Refusé |
| receipt_tampered | contract | Refuser | Refusé |
| log_tampered | contract | Refuser | Refusé |
| source_changed | contract | Refuser | Refusé |
| wrong_run | contract | Refuser | Refusé |
| all_skipped | contract | Refuser | Refusé |
| failed_test | contract | Refuser | Refusé |
| bad_counts | contract | Refuser | Refusé |
| traversal | contract | Refuser | Refusé |
| zero_tests | contract | Refuser | Refusé |
| skips_omitted | limits | Refuser | Accepté |
| unlisted_change | limits | Refuser | Accepté |
| dishonest_executor | limits | Refuser | Accepté |

## Interprétation

Les limites sont volontairement conservées dans le bilan : tests ignorés non déclarés, dépendance modifiée hors des fichiers listés, exécuteur malhonnête fournissant aussi la référence de confiance.

Un bon résultat sur les cas couverts ne prouve pas une fiabilité générale. Le corpus a été conçu en connaissant le code ; il est petit, non indépendant et sans fréquence représentative des usages réels. Les trois cas de limites violent ou dépassent les hypothèses du vérificateur, mais restent des clôtures injustifiées selon le scénario.

Aucun vrai test applicatif ni modèle n'est lancé par cet évaluateur : les reçus et journaux sont des fixtures synthétiques. Les exécutions réelles sont documentées séparément dans la démonstration du correctif.

[Données, labels, entrées et résultats complets](results.json). Les empreintes dans ce fichier identifient le code et le corpus utilisés.
