from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


RouteCategory = Literal[
    "general",
    "reasoning",
    "coding",
    "vision",
]


@dataclass(frozen=True)
class ModelDecision:
    category: RouteCategory
    model: str
    reason: str
    confidence: float
    options: dict[str, int | float]


MODEL_MAP: dict[RouteCategory, str] = {
    "general": "llama3.1:8b",
    "reasoning": "llama3.1:8b",
    "coding": "qwen2.5-coder:7b",
    "vision": "llama3.1:8b",
}


MODEL_OPTIONS: dict[RouteCategory, dict[str, int | float]] = {
    "general": {
        "temperature": 0.72,
        "top_p": 0.92,
        "top_k": 40,
        "repeat_penalty": 1.08,
        "num_ctx": 4096,
        "num_predict": 500,
    },
    "reasoning": {
        "temperature": 0.45,
        "top_p": 0.90,
        "top_k": 40,
        "repeat_penalty": 1.06,
        "num_ctx": 6144,
        "num_predict": 900,
    },
    "coding": {
        "temperature": 0.30,
        "top_p": 0.90,
        "top_k": 40,
        "repeat_penalty": 1.05,
        "num_ctx": 4096,
        "num_predict": 600,
    },
    "vision": {
        "temperature": 0.55,
        "top_p": 0.90,
        "top_k": 40,
        "repeat_penalty": 1.06,
        "num_ctx": 8192,
        "num_predict": 700,
    },
}


CODING_PATTERNS = [
    r"\bpython\b",
    r"\bjavascript\b",
    r"\btypescript\b",
    r"\bjava\b",
    r"\bkotlin\b",
    r"\bhtml\b",
    r"\bcss\b",
    r"\bsql\b",
    r"\bfastapi\b",
    r"\bdocker\b",
    r"\bcompose\b",
    r"\bdebug\b",
    r"\bdebugging\b",
    r"\btraceback\b",
    r"\bexception\b",
    r"\berror message\b",
    r"\bfunction\b",
    r"\bclass\b",
    r"\bapi endpoint\b",
    r"\bscript\b",
    r"\bsource code\b",
    r"\bcode review\b",
    r"\bcompile\b",
    r"\bsyntax\b",
    r"\bgit\b",
    r"\bterminal command\b",
    r"\bbash\b",
    r"\blinux command\b",
    r"\bprogramming\b",
    r"\bcoding\b",
    r"\brefactor\b",
    r"\bimplementation\b",
    r"\bdatabase query\b",
    r"\bregex\b",
]


REASONING_PATTERNS = [
    r"\banalyze\b",
    r"\banalysis\b",
    r"\bevaluate\b",
    r"\bcompare\b",
    r"\btrade[- ]?offs?\b",
    r"\broot cause\b",
    r"\bcritical thinking\b",
    r"\breason through\b",
    r"\bstrategy\b",
    r"\barchitecture\b",
    r"\bdecision\b",
    r"\bpros and cons\b",
    r"\bsolve this problem\b",
    r"\bdeep analysis\b",
    r"\bwhy does\b",
    r"\bwhat would happen\b",
    r"\bexplain the reasoning\b",
    r"\bassess\b",
    r"\bjudge\b",
    r"\bweigh the options\b",
    r"\bplan\b",
    r"\bdesign\b",
    r"\bdiagnose\b",
]


VISION_PATTERNS = [
    r"\bscreenshot\b",
    r"\bimage\b",
    r"\bphoto\b",
    r"\bpicture\b",
    r"\bdiagram\b",
    r"\bwhat do you see\b",
    r"\blook at this\b",
    r"\bvisual\b",
]


def _count_matches(text: str, patterns: list[str]) -> int:
    return sum(
        1
        for pattern in patterns
        if re.search(pattern, text, flags=re.IGNORECASE)
    )


def _manual_override(
    requested_model: str | None,
) -> ModelDecision | None:
    if not requested_model:
        return None

    normalized = requested_model.strip().lower()

    if normalized in {"", "auto", "default"}:
        return None

    return ModelDecision(
        category="general",
        model=requested_model.strip(),
        reason="A manual model override was requested.",
        confidence=1.0,
        options=MODEL_OPTIONS["general"].copy(),
    )


def select_model(
    message: str,
    *,
    requested_model: str | None = None,
    has_image: bool = False,
    previous_category: RouteCategory | None = None,
) -> ModelDecision:
    """
    Select the best approved Ollama model for a user message.

    Routing order:
    1. Manual model override
    2. Image or visual request
    3. Coding request
    4. Deep reasoning request
    5. Continue the previous specialist route
    6. General conversation fallback
    """

    override = _manual_override(requested_model)

    if override is not None:
        return override

    text = message.strip()

    if not text:
        return ModelDecision(
            category="general",
            model=MODEL_MAP["general"],
            reason="The request was empty, so the general model was selected.",
            confidence=0.50,
            options=MODEL_OPTIONS["general"].copy(),
        )

    if has_image:
        return ModelDecision(
            category="vision",
            model=MODEL_MAP["vision"],
            reason="The request contains visual input.",
            confidence=1.0,
            options=MODEL_OPTIONS["vision"].copy(),
        )

    coding_score = _count_matches(text, CODING_PATTERNS)
    reasoning_score = _count_matches(text, REASONING_PATTERNS)
    vision_score = _count_matches(text, VISION_PATTERNS)

    if "```" in text:
        coding_score += 2

    if re.search(
        r"\b(import|def|class|const|let|var|SELECT|INSERT|UPDATE|DELETE)\b",
        text,
        flags=re.IGNORECASE,
    ):
        coding_score += 1

    if len(text) > 1400:
        reasoning_score += 2

    if vision_score >= 1:
        return ModelDecision(
            category="vision",
            model=MODEL_MAP["vision"],
            reason="The request refers to visual content.",
            confidence=min(0.98, 0.84 + vision_score * 0.05),
            options=MODEL_OPTIONS["vision"].copy(),
        )

    if coding_score >= 1:
        return ModelDecision(
            category="coding",
            model=MODEL_MAP["coding"],
            reason="Programming, debugging, or development signals were detected.",
            confidence=min(0.98, 0.72 + coding_score * 0.06),
            options=MODEL_OPTIONS["coding"].copy(),
        )

    if reasoning_score >= 2:
        return ModelDecision(
            category="reasoning",
            model=MODEL_MAP["reasoning"],
            reason="The request requires extended analysis or critical reasoning.",
            confidence=min(0.96, 0.68 + reasoning_score * 0.07),
            options=MODEL_OPTIONS["reasoning"].copy(),
        )

    if previous_category in {"coding", "reasoning"} and len(text) < 220:
        return ModelDecision(
            category=previous_category,
            model=MODEL_MAP[previous_category],
            reason="The message appears to continue the current specialist conversation.",
            confidence=0.70,
            options=MODEL_OPTIONS[previous_category].copy(),
        )

    return ModelDecision(
        category="general",
        model=MODEL_MAP["general"],
        reason="General conversation is the best match.",
        confidence=0.78,
        options=MODEL_OPTIONS["general"].copy(),
    )
