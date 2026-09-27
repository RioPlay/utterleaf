import pytest

from utterleaf.model_presentation import model_display_name, model_purpose


@pytest.mark.parametrize("name,display,scope", [
    ("tiny", "Tiny", "Multilingual"),
    ("tiny.en", "Tiny English", "English-only"),
    ("base", "Base", "Multilingual"),
    ("base.en", "Base English", "English-only"),
    ("small", "Small", "Multilingual"),
    ("small.en", "Small English", "English-only"),
    ("medium", "Medium", "Multilingual"),
    ("medium.en", "Medium English", "English-only"),
    ("large-v3", "Large v3", "Multilingual"),
    ("distil-small.en", "Distilled Small English", "English-only"),
])
def test_known_model_presentation(name, display, scope):
    assert model_display_name(name) == display
    assert model_purpose(name) == f"{scope} speech recognition."
    assert model_display_name(f"  {name}  ") == display
    assert model_purpose(f"  {name}  ") == f"{scope} speech recognition."
    text = f"{model_display_name(name)} {model_purpose(name)}".lower()
    assert not any(claim in text for claim in ("ready", "installed", "fast", "accurate", "recommended"))


@pytest.mark.parametrize("name", ["", " ", "\n\t"])
def test_empty_selection_is_explicit(name):
    assert model_display_name(name) == "No model selected"
    assert model_purpose(name) == "Choose a speech model."


@pytest.mark.parametrize("name", [
    "private-org/private-model",
    r"C:\Users\Private Person\private-speech-model",
    "/home/private-person/private-model",
    "../../private-model",
    "private-model.en",
    "private-model\nready",
    "large-v3.en",
    "BASE.EN",
])
def test_custom_identifiers_are_not_echoed_or_inferred(name):
    assert model_display_name(name) == "Custom model"
    assert model_purpose(name) == "Custom model; supported languages depend on its configuration."
    assert name not in model_display_name(name)
    assert name not in model_purpose(name)
    assert "ready" not in model_purpose(name).lower()
    assert "English-only" not in model_purpose(name)
