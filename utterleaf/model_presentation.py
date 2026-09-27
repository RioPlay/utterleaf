"""Pure, consumer-facing model names and language scope.

These labels describe known identifiers, not installation or engine readiness.
Keep custom identifiers and paths out of primary presentation; they belong in
explicit technical details. Do not import model, configuration, or I/O code here.
"""

_MODEL_NAMES = {
    "tiny": "Tiny",
    "tiny.en": "Tiny English",
    "base": "Base",
    "base.en": "Base English",
    "small": "Small",
    "small.en": "Small English",
    "medium": "Medium",
    "medium.en": "Medium English",
    "large-v3": "Large v3",
    "distil-small.en": "Distilled Small English",
}
PUBLIC_MODEL_TOKENS = frozenset(_MODEL_NAMES)


def model_token(name: str) -> str:
    """Return an exact public identifier or a fixed, privacy-safe fallback."""
    return name if type(name) is str and name in PUBLIC_MODEL_TOKENS else "custom"


def model_display_name(name: str) -> str:
    """Return a fixed human name without echoing unknown identifiers or paths."""
    name = name.strip()
    if not name:
        return "No model selected"
    return _MODEL_NAMES.get(name, "Custom model")


def model_purpose(name: str) -> str:
    """Describe language scope only, without performance or readiness claims."""
    name = name.strip()
    if not name:
        return "Choose a speech model."
    if name not in _MODEL_NAMES:
        return "Custom model; supported languages depend on its configuration."
    if name.endswith(".en"):
        return "English-only speech recognition."
    return "Multilingual speech recognition."
