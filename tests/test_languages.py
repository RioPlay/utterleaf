from utterleaf.languages import (
    LANGUAGE_CODES,
    LANGUAGE_LABELS,
    language_guidance,
    language_supported,
    normalize_language,
)
from utterleaf.model_selection import (
    explicit_model_selection,
    model_language_compatible,
    resolve_model_selection,
)


def test_complete_language_catalog_is_unique_and_human_readable():
    assert len(LANGUAGE_CODES) == len(set(LANGUAGE_CODES)) == 100
    assert LANGUAGE_CODES[0] == "af" and LANGUAGE_CODES[-1] == "yue"
    assert LANGUAGE_LABELS["en"] == "English (en)"
    assert LANGUAGE_LABELS["yue"] == "Cantonese (yue)"
    assert LANGUAGE_LABELS["auto"] == "Automatic detection"
    assert all(code in LANGUAGE_LABELS and code in LANGUAGE_LABELS[code]
               for code in LANGUAGE_CODES)


def test_language_validation_normalizes_legacy_english_alias():
    assert normalize_language(" English ") == "en"
    assert language_supported("auto")
    assert language_supported("YUE")
    assert not language_supported("private-language")


def test_explicit_pack_tokens_preserve_legacy_resolution_but_allow_multilingual_english():
    assert explicit_model_selection("small", "en") == "small.en"
    assert explicit_model_selection("small", "fr") == "small.multilingual"
    assert resolve_model_selection("small", "en") == "small.en"
    assert resolve_model_selection("small.multilingual", "en") == "small"
    assert resolve_model_selection("small.en", "fr") == "small.en"
    assert model_language_compatible("small.multilingual", "en")
    assert model_language_compatible("small.multilingual", "fr")
    assert not model_language_compatible("small.en", "fr")
    assert model_language_compatible("small.en", "auto")
    assert model_language_compatible("private/custom.en", "fr")


def test_language_guidance_explains_shared_multilingual_pack():
    assert language_guidance("fr", model_scope="multilingual") == (
        "French will use the selected multilingual model pack."
    )
    assert language_guidance("en", model_scope="multilingual") == (
        "English will use the selected multilingual model pack."
    )
    assert language_guidance("en", model_scope="english-only") == (
        "English will use the selected English-only model pack."
    )
    assert language_guidance("fr", model_scope="english-only") == (
        "French requires a multilingual model pack."
    )
    assert language_guidance("fr", model_scope="custom") == (
        "French support depends on this custom model."
    )
