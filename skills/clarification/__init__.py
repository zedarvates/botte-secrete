# Clarification Proactive — Module pour agents Hermes
#
# Pattern: "Pose-moi jusqu'à 5 questions numérotées pour t'éclaircir"
# Si l'utilisateur ne répond pas (champ vide / timeout / silence),
# le LLM comble les vides avec des hypothèses raisonnables ET les signale.
#
# Inspiré de :
#   - Chain of Clarification (CoC, 2024)
#   - Slot Filling avec Default Reasoning
#   - Minimum Viable Questions (MVQ, max 5)
#   - Progressive Disclosure (poser seulement ce qui bloque l'étape en cours)

from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class QuestionPriority(str, Enum):
    BLOCKER = "blocker"     # Impossible de continuer sans réponse
    HIGH = "high"           # Impact majeur sur la qualité
    MEDIUM = "medium"       # Impact modéré
    LOW = "low"             # Nice-to-have


@dataclass
class Question:
    """Une question de clarification."""
    number: int
    text: str
    priority: QuestionPriority = QuestionPriority.MEDIUM
    default_answer: Optional[str] = None   # Réponse par défaut si user ne répond pas
    context: str = ""                       # Pourquoi cette question est posée


@dataclass
class ClarificationRequest:
    """Requête de clarification envoyée à l'utilisateur."""
    agent_name: str
    step: str                              # Étape du workflow (ex: "audit", "fix")
    questions: list[Question] = field(default_factory=list)
    max_questions: int = 5

    def to_prompt(self) -> str:
        """Génère le prompt à montrer à l'utilisateur."""
        lines = [
            f"🤔 **{self.agent_name}** — Clarifications pour l'étape *{self.step}*",
            f"",
            f"J'ai besoin d'éclaircir {len(self.questions)} point(s) avant de continuer.",
            f"",
        ]
        for q in self.questions:
            priority_emoji = {
                QuestionPriority.BLOCKER: "🔴",
                QuestionPriority.HIGH: "🟠",
                QuestionPriority.MEDIUM: "🟡",
                QuestionPriority.LOW: "⚪",
            }
            lines.append(f"{q.number}. {priority_emoji.get(q.priority, '')} {q.text}")
            if q.context:
                lines.append(f"   _({q.context})_")
            if q.default_answer:
                lines.append(f"   Défaut si pas de réponse : _{q.default_answer}_")
            lines.append("")

        lines.extend([
            "---",
            "Réponds avec les numéros (ex: `1: oui, 2: non, 3: /home/user/projet`)",
            "Ou réponds `auto` pour que je comble les vides avec les valeurs par défaut.",
        ])
        return "\n".join(lines)

    def fill_defaults(self) -> dict[int, str]:
        """Remplit toutes les questions avec les valeurs par défaut."""
        return {q.number: q.default_answer or "non spécifié" for q in self.questions}


# ── Générateurs de questions spécifiques aux Mousquetaires ──

def portos_clarify(project_path: str, files_count: int) -> ClarificationRequest:
    """Questions que Porthos doit poser avant un audit."""
    cr = ClarificationRequest(agent_name="🥊 Porthos", step="audit")

    if files_count > 100:
        cr.questions.append(Question(
            number=1,
            text=f"Le projet a {files_count} fichiers. Auditer seulement les fichiers modifiés récemment ou tout le projet ?",
            priority=QuestionPriority.HIGH,
            default_answer="Fichiers modifiés dans les 30 derniers jours",
            context="Audit complet sur >100 fichiers = long et coûteux en tokens"
        ))

    cr.questions.append(Question(
        number=len(cr.questions) + 1,
        text="Y a-t-il des fichiers/répertoires à IGNORER dans l'audit (tests, migrations, vendor) ?",
        priority=QuestionPriority.MEDIUM,
        default_answer="Ignorer tests/, migrations/, __pycache__/, node_modules/, vendor/, .git/",
        context="Évite les faux positifs dans le code généré"
    ))

    cr.questions.append(Question(
        number=len(cr.questions) + 1,
        text="Audit orienté sécurité (secrets, injections) ou qualité générale (complexité, duplication) ?",
        priority=QuestionPriority.MEDIUM,
        default_answer="Qualité générale + sécurité",
        context="Détermine le poids des analyzers"
    ))

    cr.questions.append(Question(
        number=len(cr.questions) + 1,
        text="Seuil de sévérité minimum à reporter : INFO, WARNING, ou ERROR seulement ?",
        priority=QuestionPriority.LOW,
        default_answer="WARNING et ERROR",
        context="INFO peut générer beaucoup de bruit"
    ))

    cr.questions.append(Question(
        number=len(cr.questions) + 1,
        text="Le projet a-t-il des contraintes de performance particulières (temps réel, embarqué, GPU) ?",
        priority=QuestionPriority.LOW,
        default_answer="Non",
        context="Détermine si on active les analyzers de hot paths/latence"
    ))

    return cr


def dartagnan_clarify(fix_count: int) -> ClarificationRequest:
    """Questions que d'Artagnan doit poser avant de corriger."""
    cr = ClarificationRequest(agent_name="⚔️ d'Artagnan", step="fix")

    cr.questions.append(Question(
        number=1,
        text=f"J'ai {fix_count} findings à corriger. Appliquer TOUS les fixes automatiquement ou seulement les critiques/erreurs ?",
        priority=QuestionPriority.BLOCKER,
        default_answer="Appliquer automatiquement les fixes simples (dead code, duplication). Demander confirmation pour les refactorings lourds.",
        context="Les fixes automatiques peuvent casser des choses"
    ))

    cr.questions.append(Question(
        number=2,
        text="Créer un commit par fix ou un commit groupé ?",
        priority=QuestionPriority.MEDIUM,
        default_answer="Un commit groupé avec message détaillé",
        context="Impacte la traçabilité git"
    ))

    cr.questions.append(Question(
        number=3,
        text="Exécuter les tests du projet après chaque fix pour vérifier qu'il n'y a pas de régression ?",
        priority=QuestionPriority.HIGH,
        default_answer="Oui, exécuter les tests",
        context="Essentiel pour la confiance"
    ))

    return cr


def aramis_clarify(project_type: str) -> ClarificationRequest:
    """Questions qu'Aramis doit poser avant d'optimiser."""
    cr = ClarificationRequest(agent_name="📿 Aramis", step="optimize")

    cr.questions.append(Question(
        number=1,
        text="Priorité d'optimisation : réduction de tokens, vitesse d'exécution, ou lisibilité du code ?",
        priority=QuestionPriority.HIGH,
        default_answer="Réduction de tokens en premier, lisibilité en second",
        context="Détermine le scoring des optimisations"
    ))

    cr.questions.append(Question(
        number=2,
        text="Y a-t-il des skills/appels dynamiques (getattr, eval, importlib) que je devrais savoir avant d'exclure du code ?",
        priority=QuestionPriority.HIGH,
        default_answer="Non, traiter tout le code comme statique",
        context="Évite les faux positifs de dead code"
    ))

    cr.questions.append(Question(
        number=3,
        text="Budget token maximum par session ? (ex: 50K, 100K, illimité)",
        priority=QuestionPriority.MEDIUM,
        default_answer="100K tokens",
        context="Cible pour le .skills-profile"
    ))

    cr.questions.append(Question(
        number=4,
        text="Le projet utilise-t-il ComfyUI, Hailo-8, ou d'autres accélérateurs hardware ?",
        priority=QuestionPriority.LOW,
        default_answer="Non",
        context="Active les optimisations hardware-specific"
    ))

    return cr


def rochefort_clarify(audit_report_path: str) -> ClarificationRequest:
    """Questions que Rochefort doit poser avant son contre-audit."""
    cr = ClarificationRequest(agent_name="🗡️ Rochefort", step="contre-audit")

    cr.questions.append(Question(
        number=1,
        text="Niveau de paranoïa : standard (faux négatifs évidents) ou maximal (edge cases, race conditions théoriques) ?",
        priority=QuestionPriority.HIGH,
        default_answer="Standard — seulement les faux négatifs probables",
        context="Niveau maximal génère beaucoup de faux positifs"
    ))

    cr.questions.append(Question(
        number=2,
        text="Le projet utilise-t-il des frameworks qui font des appels dynamiques (Django, FastAPI, plugins) ?",
        priority=QuestionPriority.MEDIUM,
        default_answer="Non",
        context="Change la détection de dead code"
    ))

    return cr
