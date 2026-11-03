"""Consumer-facing catalog for languages supported by bundled Whisper engines."""

from __future__ import annotations


# Keep this explicit and dependency-free so Settings can open without importing
# the speech engine. Codes match faster-whisper 1.2's multilingual tokenizer.
_LANGUAGES = (
    ("af", "Afrikaans"), ("am", "Amharic"), ("ar", "Arabic"),
    ("as", "Assamese"), ("az", "Azerbaijani"), ("ba", "Bashkir"),
    ("be", "Belarusian"), ("bg", "Bulgarian"), ("bn", "Bengali"),
    ("bo", "Tibetan"), ("br", "Breton"), ("bs", "Bosnian"),
    ("ca", "Catalan"), ("cs", "Czech"), ("cy", "Welsh"),
    ("da", "Danish"), ("de", "German"), ("el", "Greek"),
    ("en", "English"), ("es", "Spanish"), ("et", "Estonian"),
    ("eu", "Basque"), ("fa", "Persian"), ("fi", "Finnish"),
    ("fo", "Faroese"), ("fr", "French"), ("gl", "Galician"),
    ("gu", "Gujarati"), ("ha", "Hausa"), ("haw", "Hawaiian"),
    ("he", "Hebrew"), ("hi", "Hindi"), ("hr", "Croatian"),
    ("ht", "Haitian Creole"), ("hu", "Hungarian"), ("hy", "Armenian"),
    ("id", "Indonesian"), ("is", "Icelandic"), ("it", "Italian"),
    ("ja", "Japanese"), ("jw", "Javanese"), ("ka", "Georgian"),
    ("kk", "Kazakh"), ("km", "Khmer"), ("kn", "Kannada"),
    ("ko", "Korean"), ("la", "Latin"), ("lb", "Luxembourgish"),
    ("ln", "Lingala"), ("lo", "Lao"), ("lt", "Lithuanian"),
    ("lv", "Latvian"), ("mg", "Malagasy"), ("mi", "Maori"),
    ("mk", "Macedonian"), ("ml", "Malayalam"), ("mn", "Mongolian"),
    ("mr", "Marathi"), ("ms", "Malay"), ("mt", "Maltese"),
    ("my", "Myanmar"), ("ne", "Nepali"), ("nl", "Dutch"),
    ("nn", "Nynorsk"), ("no", "Norwegian"), ("oc", "Occitan"),
    ("pa", "Punjabi"), ("pl", "Polish"), ("ps", "Pashto"),
    ("pt", "Portuguese"), ("ro", "Romanian"), ("ru", "Russian"),
    ("sa", "Sanskrit"), ("sd", "Sindhi"), ("si", "Sinhala"),
    ("sk", "Slovak"), ("sl", "Slovenian"), ("sn", "Shona"),
    ("so", "Somali"), ("sq", "Albanian"), ("sr", "Serbian"),
    ("su", "Sundanese"), ("sv", "Swedish"), ("sw", "Swahili"),
    ("ta", "Tamil"), ("te", "Telugu"), ("tg", "Tajik"),
    ("th", "Thai"), ("tk", "Turkmen"), ("tl", "Tagalog"),
    ("tr", "Turkish"), ("tt", "Tatar"), ("uk", "Ukrainian"),
    ("ur", "Urdu"), ("uz", "Uzbek"), ("vi", "Vietnamese"),
    ("yi", "Yiddish"), ("yo", "Yoruba"), ("zh", "Chinese"),
    ("yue", "Cantonese"),
)

LANGUAGE_NAMES = dict(_LANGUAGES)
LANGUAGE_CODES = tuple(code for code, _name in _LANGUAGES)
LANGUAGE_LABELS = {
    "auto": "Automatic detection",
    **{code: f"{name} ({code})" for code, name in _LANGUAGES},
}


def normalize_language(value: str) -> str:
    code = value.strip().casefold()
    return "en" if code == "english" else code


def language_supported(value: str) -> bool:
    return normalize_language(value) in {"auto", *LANGUAGE_CODES}


def language_guidance(value: str, *, model_scope: str) -> str:
    code = normalize_language(value)
    if code == "auto":
        if model_scope == "english-only":
            return "Automatic detection stays English with this English-only pack."
        if model_scope == "multilingual":
            return "Automatic detection uses the selected multilingual model pack."
        return "Automatic detection support depends on this custom model."
    name = LANGUAGE_NAMES.get(code)
    if name is None:
        return "Choose a supported language from the list."
    if model_scope == "custom":
        return f"{name} support depends on this custom model."
    if model_scope == "english-only" and code != "en":
        return f"{name} requires a multilingual model pack."
    if code == "en":
        return ("English will use the selected English-only model pack."
                if model_scope == "english-only" else
                "English will use the selected multilingual model pack.")
    return f"{name} will use the selected multilingual model pack."
