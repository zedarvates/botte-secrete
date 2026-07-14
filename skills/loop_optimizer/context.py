"""Build a bounded, deterministic context for the next loop iteration."""

from __future__ import annotations

from dataclasses import dataclass

from skills.context_windows.windows import WindowManager


def estimate_tokens(text: str) -> int:
    return (len(text) + 3) // 4


@dataclass(frozen=True, slots=True)
class ContextBuild:
    content: str
    tokens: int
    included: tuple[str, ...]
    dropped: tuple[str, ...]
    pruning_hint: tuple[str, float] | None = None
    final_verification_required: bool = True


class LoopContextBuilder:
    def __init__(self, manager: WindowManager, max_context_tokens: int = 1_024):
        if max_context_tokens < 1:
            raise ValueError("max_context_tokens must be positive")
        self.manager = manager
        self.max_context_tokens = max_context_tokens

    def build(self, *, since_step: int = 0, references: tuple[str, ...] = (),
              unresolved_errors: tuple[str, ...] = ()) -> ContextBuild:
        candidates: list[tuple[str, str]] = []
        active = self.manager.get_active()
        if active is not None:
            candidates.append((f"active:{active.id}", active.content))
        for reference in references:
            window = self.manager.windows.get(reference)
            if window is not None and window is not active:
                candidates.append((f"reference:{reference}", window.content))
        deltas = self.manager.structured_deltas(since_step)
        if deltas:
            candidates.append(("deltas", "\n".join(
                f"{item.window_id}: {item.changed_lines} changed line(s)" for item in deltas[-3:])))
        if unresolved_errors:
            candidates.append(("errors", "\n".join(unresolved_errors)))

        included, dropped, parts, used = [], [], [], 0
        for label, content in candidates:
            section = f"[{label}]\n{content}"
            tokens = estimate_tokens(section)
            if used + tokens <= self.max_context_tokens:
                included.append(label)
                parts.append(section)
                used += tokens
            elif not parts:
                limit = self.max_context_tokens * 4
                parts.append(section[:limit])
                included.append(label)
                used = estimate_tokens(parts[-1])
            else:
                dropped.append(label)
        text = "\n\n".join(parts)
        hint = None
        if dropped:
            # The hard deterministic cap is already enforced above.  Belt 2.0
            # is consulted only as telemetry/advice after that free pruning.
            try:
                from skills.auto_router.nn_belt2 import context_pruning_hint
                hint = context_pruning_hint(total_size=sum(len(item) for _, item in candidates),
                                            num_sections=len(candidates),
                                            query_similarity=0.0)
            except Exception:
                hint = None
        return ContextBuild(text, estimate_tokens(text), tuple(included), tuple(dropped), hint)
