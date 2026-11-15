# Clarification ciblée

Lire d'abord la demande, les décisions et les preuves accessibles. Poser une
question seulement si une réponse manquante change matériellement l'action ou
le résultat ; une demande claire peut ne nécessiter aucune question.

- Réutiliser les réponses et autorisations déjà acquises. Ne pas redemander
  confirmation à chaque agent ou étape.
- Regrouper les seules questions utiles, en commençant par les blocages.
- Pour un choix réversible déjà autorisé, adopter au besoin une hypothèse
  raisonnable et la signaler. Continuer le travail indépendant d'une réponse.
- Le silence, un timeout ou `auto` ne valent ni réponse à un blocage ni
  autorisation d'une action. Conserver l'étape dépendante en attente si sa
  réponse ou son autorisation manque réellement.

**Module :** `skills.clarification`. Les générateurs proposent des candidats,
pas un questionnaire obligatoire. `pending_questions(answers)` écarte les
réponses établies par l'appelant ; `to_prompt(answers)` renvoie une chaîne vide
si tout est connu. `fill_defaults(answers)` contient seulement les hypothèses
facultatives déclarées, jamais un BLOCKER ou une question marquée
`requires_explicit_answer`. Examiner `blocking_questions(answers)` séparément.
Ces helpers ne vérifient pas la provenance des réponses ni les permissions.
