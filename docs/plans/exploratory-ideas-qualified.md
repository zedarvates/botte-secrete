# Idées exploratoires — qualifiées

## Cache sémantique (embeddings locaux)

**Faisabilité**: Haute. Qdrant déjà intégré. Embeddings locaux via sentence-transformers.

**Approche**: Hasher le prompt → chercher dans Qdrant les prompts similaires (cosine > 0.95) → retourner la réponse cachée au lieu d'appeler le LLM.

**Gain estimé**: -60% appels LLM pour prompts répétitifs/similaires.

**Code existant**: `skills/response_cache/`, `skills/vector_protocol/`

## Compression de contexte pour logs volumineux

**Faisabilité**: Moyenne. Résumer les logs avant de les passer à l'agent.

**Approche**: Extraire les lignes uniques, compter les patterns, ne garder que les échantillons représentatifs.

**Gain estimé**: -80% tokens pour analyses de logs.

## Plugin navigateur/VS Code statusline

**Faisabilité**: Haute. Extension VS Code qui affiche `🦶12,345` dans la barre de statut.

**Approche**: Lire `.botte/metrics.json` périodiquement, afficher tokens_saved.

## Budget de session configurable

**Faisabilité**: Haute. Extension du Budget existant avec un plafond par session.

**Approche**: Ajouter `session_limit` dans `.botte/policy.md`. Bloquer les appels cloud quand dépassé.
