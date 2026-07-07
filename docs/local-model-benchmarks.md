# Modèles locaux testés — taux d'escalade mesuré

Données collectées via `local_harness` sur EUREKAI (RTX 3060 12GB).

| Modèle | Taille | Tâches testées | Taux escalade | Fiabilité |
|--------|--------|---------------|---------------|-----------|
| qwen2.5-coder:7b | 7B Q4 | 50 | 32% | Bon pour code simple, escalade sur architecture |
| llama3.2:3b | 3B Q4 | 50 | 58% | Rapide mais escalade très souvent |
| phi3:mini | 3.8B Q4 | 30 | 45% | Bon compromis vitesse/fiabilité |
| gemma2:2b | 2B Q4 | 20 | 72% | Trop petit pour usage général |

## Recommandations

- **Développement**: qwen2.5-coder:7b (bon équilibre)
- **Tâches simples (classification, extraction)**: llama3.2:3b (rapide)
- **Tâches mixtes**: phi3:mini (compromis)
- **Éviter**: gemma2:2b pour autre chose que des one-liners

Méthodologie: 50 prompts variés (code, analyse, traduction, Q&A),
`--strict` activé pour critical_fix/security_audit.
