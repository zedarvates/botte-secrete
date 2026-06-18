"""Local Model Router — Routes tasks to local models when possible.

Principle 1: prefer local over cloud — existing EUREKAI hardware:
    Hailo-8 (vision), ComfyUI:8188 (images), LocalAI:8080 (text/voice)

Token savings: 40-60% of cloud tokens moved to local
"""

import hashlib
import json
from enum import Enum
from typing import Optional, Callable

class TaskType(Enum):
    SIMPLE_TEXT = "simple_text"       # Classification, extraction, summarization
    COMPLEX_REASONING = "complex"     # Multi-step reasoning, code generation
    VISION_CLASSIFY = "vision_cls"    # Image classification
    VISION_DETECT = "vision_det"      # Object detection
    VISION_OCR = "vision_ocr"         # Text extraction from images
    SPEECH_TO_TEXT = "stt"            # Audio transcription
    TEXT_TO_SPEECH = "tts"            # Voice synthesis
    IMAGE_GENERATION = "img_gen"      # Image creation
    SEMANTIC_SEARCH = "search"        # Semantic search in vault

class RouteDecision:
    """Decision: local or cloud, which backend, estimated savings."""
    def __init__(self, local: bool, backend: str, reason: str, token_savings_pct: float = 0):
        self.local = local
        self.backend = backend
        self.reason = reason
        self.token_savings_pct = token_savings_pct

    def __repr__(self):
        loc = "🏠 LOCAL" if self.local else "☁️ CLOUD"
        return f"{loc} → {self.backend} ({self.token_savings_pct:.0f}% saved) — {self.reason}"


class LocalRouter:
    """Decides whether a task can be handled locally or needs cloud."""

    # Complexity thresholds
    SIMPLE_MAX_WORDS = 200       # Simple tasks: short prompts
    SIMPLE_PATTERNS = ["résume", "classe", "extrait", "liste", "combien",
                       "traduis", "corrige", "explique brièvement"]

    def __init__(self):
        self.stats = {"local": 0, "cloud": 0, "tokens_saved": 0}

    def route_text(self, prompt: str) -> RouteDecision:
        """Route text generation to local (LocalAI) or cloud (DeepSeek)."""
        word_count = len(prompt.split())

        # Simple tasks → local
        prompt_lower = prompt.lower()
        is_simple = word_count < self.SIMPLE_MAX_WORDS and any(
            p in prompt_lower for p in self.SIMPLE_PATTERNS)

        if is_simple:
            self.stats["local"] += 1
            self.stats["tokens_saved"] += word_count * 10
            return RouteDecision(True, "LocalAI/gemma-4-e2b-it",
                                "Requête simple, modèle local suffit", 100)
        else:
            self.stats["cloud"] += 1
            return RouteDecision(False, "DeepSeek/cloud",
                                "Raisonnement complexe, cloud nécessaire", 0)

    def route_vision(self, task: str, image_path: Optional[str] = None) -> RouteDecision:
        """Route vision tasks to Hailo-8 (always local if available)."""
        mapping = {
            "classify": ("Hailo-8/ResNet-18", "Classification locale Hailo-8"),
            "detect": ("Hailo-8/YOLOv8", "Détection locale Hailo-8"),
            "ocr": ("Hailo-8/OCR", "OCR local Hailo-8"),
        }
        backend, reason = mapping.get(task, ("Hailo-8", "Vision locale"))
        self.stats["local"] += 1
        self.stats["tokens_saved"] += 5000  # Vision uploads are expensive
        return RouteDecision(True, backend, reason, 100)

    def route_speech(self, task: str) -> RouteDecision:
        """Route speech tasks to LocalAI (STT/TTS)."""
        if task == "stt":
            self.stats["local"] += 1
            self.stats["tokens_saved"] += 3000
            return RouteDecision(True, "LocalAI/Whisper", "Transcription locale", 100)
        elif task == "tts":
            self.stats["local"] += 1
            self.stats["tokens_saved"] += 2000
            return RouteDecision(True, "LocalAI/Piper TTS", "Synthèse vocale locale", 100)
        else:
            return RouteDecision(False, "Cloud", "Tâche audio non reconnue", 0)

    def route_image_gen(self, prompt: str) -> RouteDecision:
        """Route image generation to ComfyUI (local) if available."""
        self.stats["local"] += 1
        self.stats["tokens_saved"] += 8000  # Image gen API costs
        return RouteDecision(True, "ComfyUI:8188", "Génération locale ComfyUI", 100)

    def route_search(self, query: str) -> RouteDecision:
        """Route semantic search to Qdrant (local)."""
        self.stats["local"] += 1
        self.stats["tokens_saved"] += 1000
        return RouteDecision(True, "Qdrant:6333", "Recherche sémantique locale", 100)

    def decide(self, task_type: TaskType, content: str = "",
               image_path: Optional[str] = None) -> RouteDecision:
        """Main routing decision."""
        if task_type == TaskType.SIMPLE_TEXT:
            return self.route_text(content)
        elif task_type == TaskType.COMPLEX_REASONING:
            # Always cloud for complex reasoning
            self.stats["cloud"] += 1
            return RouteDecision(False, "DeepSeek/cloud",
                                "Raisonnement complexe nécessite cloud", 0)
        elif task_type in (TaskType.VISION_CLASSIFY, TaskType.VISION_DETECT, TaskType.VISION_OCR):
            task_map = {TaskType.VISION_CLASSIFY: "classify",
                       TaskType.VISION_DETECT: "detect",
                       TaskType.VISION_OCR: "ocr"}
            return self.route_vision(task_map[task_type], image_path)
        elif task_type == TaskType.SPEECH_TO_TEXT:
            return self.route_speech("stt")
        elif task_type == TaskType.TEXT_TO_SPEECH:
            return self.route_speech("tts")
        elif task_type == TaskType.IMAGE_GENERATION:
            return self.route_image_gen(content)
        elif task_type == TaskType.SEMANTIC_SEARCH:
            return self.route_search(content)
        else:
            self.stats["cloud"] += 1
            return RouteDecision(False, "Cloud", "Type de tâche inconnu", 0)

    def report(self) -> dict:
        """Router statistics."""
        total = self.stats["local"] + self.stats["cloud"]
        local_pct = round(self.stats["local"] * 100 / total) if total else 0
        return {
            "total_decisions": total,
            "local_routed": self.stats["local"],
            "cloud_routed": self.stats["cloud"],
            "tokens_saved_est": self.stats["tokens_saved"],
            "local_pct": local_pct,
        }


def resolve_live_backend():
    """Return a concrete, reachable local chat backend from the discovery
    registry, or None. Bridges the abstract routing decisions above to the
    actual servers found by `skills.llm_backends` (LM Studio, Ollama, …).

    Falls back gracefully if the registry is empty or llm_backends is absent.
    """
    try:
        from skills.llm_backends import registry
    except ImportError:
        return None
    best = registry.best_chat_backend()
    if not best:
        return None
    return {
        "host": best.host,
        "port": best.port,
        "label": best.label,
        "base_url": best.base_url,
        "model": registry.preferred_model(best),
    }


def local_chat_available() -> bool:
    """True if at least one OpenAI-compatible local backend is reachable."""
    return resolve_live_backend() is not None


# Singleton
_router = LocalRouter()
def route(task_type: str, content: str = "", **kwargs) -> RouteDecision:
    """Quick routing: route('text', 'résume ce document')"""
    type_map = {
        "text": TaskType.SIMPLE_TEXT,
        "complex": TaskType.COMPLEX_REASONING,
        "vision": TaskType.VISION_CLASSIFY,
        "detect": TaskType.VISION_DETECT,
        "ocr": TaskType.VISION_OCR,
        "stt": TaskType.SPEECH_TO_TEXT,
        "tts": TaskType.TEXT_TO_SPEECH,
        "img": TaskType.IMAGE_GENERATION,
        "search": TaskType.SEMANTIC_SEARCH,
    }
    tt = type_map.get(task_type, TaskType.SIMPLE_TEXT)
    return _router.decide(tt, content, kwargs.get("image_path"))
