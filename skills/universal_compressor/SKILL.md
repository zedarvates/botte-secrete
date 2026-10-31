---
name: universal-compressor
description: "Compacter des données choisies pour le contexte : JSON, logs et sorties d'outils. Restauration optionnelle en mémoire ; conserver les instructions et le code exacts."
metadata:
  version: "1.1.0"
---

# Universal Compressor

Appliquer après sélection du contexte. La taille et le ratio sont mesurés en
octets UTF-8, pas en tokens facturés. Aucun gain fixe n'est garanti.

| Type | Transformation |
|---|---|
| `json` | Retirer les espaces hors chaînes ; conserver clés, éléments et lexèmes numériques |
| `log` | Résumer les répétitions consécutives strictement identiques ; garder les lignes distinctes dans l'ordre |
| `tool_output` | Retirer les codes ANSI, garder toutes les lignes |
| `text` | Résumer les répétitions consécutives et réduire les lignes vides |
| `code` | Conserver le contenu exact |
| `auto` | Détection heuristique ; préférer un type explicite lorsqu'il est connu |

Le texte et les logs restent des représentations résumées. Pour des instructions,
preuves ou chaînes dont chaque octet compte, conserver l'original (`code` convient
comme passage sans transformation). Un résumé n'acquiert aucune autorité nouvelle.

```python
from skills.universal_compressor import compress, restore

result = compress(content, content_type="json", reversible=True)
assert restore(result.reversible_key) == content
```

Le stockage est en mémoire du processus. La clé SHA-256 porte sur tout l'original.
La restauration cesse après `flush_store()` ou arrêt du processus ; la CLI ne
fournit pas de stockage persistant. Ne pas confondre restauration exacte et
qualité de décision sur le résumé. Les réponses MCP rendent tout le résultat.

`learn=True`, avec `reversible=True`, peut écrire un label de compressibilité
après restauration exacte. Le registre contient empreinte et caractéristiques,
jamais le contenu brut. Ce label ne prouve pas la qualité d'une réponse LLM.
Les tests et benchmarks utilisent `learn=False` ou `BOTTE_NN_AUTO_LABELS=0`.

Voir le [protocole de comparaison](../../docs/plans/2026-09-13-compression-integrity.md)
pour les invariants, la provenance et les limites des mesures.
