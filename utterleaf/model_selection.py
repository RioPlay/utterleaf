"""Pure model-pack selection rules shared by runtime and Settings."""

from __future__ import annotations


MULTILINGUAL_BASES = ("tiny", "base", "small", "medium")
MULTILINGUAL_SUFFIX = ".multilingual"
ENGLISH_ONLY_MODELS = frozenset({
    "tiny.en", "base.en", "small.en", "medium.en", "distil-small.en",
})
MULTILINGUAL_MODELS = frozenset({*MULTILINGUAL_BASES, "large-v3"})


def explicit_model_selection(model: str, language: str) -> str:
    """Turn a legacy size selection into an explicit pack without changing behavior."""
    name = model.strip()
    if name not in MULTILINGUAL_BASES:
        return name
    if language.strip().casefold() in {"en", "english"}:
        return f"{name}.en"
    return f"{name}{MULTILINGUAL_SUFFIX}"


def resolve_model_selection(model: str, language: str) -> str:
    """Resolve product selection tokens to an actual local model identifier.

    Bare size names retain the pre-explicit-selection behavior for existing
    configs and command-line users. Settings writes an explicit ``.en`` or
    ``.multilingual`` selection when a guided pack is chosen.
    """
    name = model.strip()
    if name.endswith(MULTILINGUAL_SUFFIX):
        base = name.removesuffix(MULTILINGUAL_SUFFIX)
        return base if base in MULTILINGUAL_BASES else name
    if language.strip().casefold() in {"en", "english"} and name in MULTILINGUAL_BASES:
        return f"{name}.en"
    return name


def model_language_compatible(model: str, language: str) -> bool:
    """Whether the resolved pack can honor this language preference."""
    resolved = resolve_model_selection(model, language)
    code = language.strip().casefold()
    return resolved not in ENGLISH_ONLY_MODELS or code in {"auto", "en", "english"}


def is_english_only_model(model: str, language: str) -> bool:
    """Identify only known guided English packs, never infer custom scope."""
    return resolve_model_selection(model, language) in ENGLISH_ONLY_MODELS


def model_language_scope(model: str, language: str) -> str:
    """Return english-only, multilingual, or custom for primary guidance."""
    resolved = resolve_model_selection(model, language)
    if resolved in ENGLISH_ONLY_MODELS:
        return "english-only"
    if resolved in MULTILINGUAL_MODELS:
        return "multilingual"
    return "custom"
