"""Turn raw dictation into text that is ready to send."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from utterleaf.config import atomic_write_text, dictionary_path


FILLERS = (
    r"\b(?:um+|uh+|er+|ah+|hmm+|huh+|mm+|mhm)\b",
    r"\byou know\b",
    r"\bi guess\b",
    r"\bbasically\b",
    r"\blet me see\b",
    r"\blet's see\b",
)

SPOKEN_PUNCT = (
    (r"\bquestion mark\b", "?"),
    (r"\bexclamation (?:point|mark)\b", "!"),
    (r"(?<!\ba )(?<!\bthe )(?<!\bthis )\bperiod\b", "."),
    (r"\bfull stop\b", "."),
    (r"\bcomma\b", ","),
    (r"\bcolon\b", ":"),
    (r"\bsemicolon\b", ";"),
    (r"\bopen (?:paren|parenthesis|bracket)\b", "("),
    (r"\bclose (?:paren|parenthesis|bracket)\b", ")"),
)

HALLUCINATION_TAIL = re.compile(
    r"(?<=[.!?])\s*(?:thank you(?: for watching)?|thanks(?: for watching)?|"
    r"please subscribe|subscribe)\.?\s*$",
    re.IGNORECASE,
)

CORRECTION_MARKERS = (
    r"\bno wait\b",
    r"\bwait no\b",
    r"\bwait,? wait\b",
    r", sorry,",
    r"\bscratch that\b",
    r"\bforget that\b",
    r"\bno no\b",
    r"\bi mean\b",
    r"\bor rather\b",
    r"\bactually wait\b",
)

COMMANDS = (
    ("scratch that", "discard"),
    ("delete that", "discard"),
    ("new paragraph", "paragraph"),
    ("new line", "newline"),
    ("make this shorter", "shorter"),
    ("make it shorter", "shorter"),
    ("make this more professional", "professional"),
    ("make it more professional", "professional"),
    ("make this a numbered list", "numbered"),
    ("make this a bulleted list", "bullets"),
    ("make this a bolded list", "bullets"),
    ("make this a bullet list", "bullets"),
    ("make this a list", "bullets"),
    ("as a numbered list", "numbered"),
    ("as a bulleted list", "bullets"),
    ("as a bolded list", "bullets"),
    ("make a numbered list", "numbered"),
    ("make a bulleted list", "bullets"),
    ("make a bolded list", "bullets"),
    ("make a bullet list", "bullets"),
    ("make a list", "bullets"),
)

# Shown in Settings so voice commands are discoverable without the README.
COMMAND_HINT = (
    "Voice commands: scratch that · new line / new paragraph · "
    "make this shorter · make it more professional · make a list of …"
)

CONTRACTIONS = (
    (r"\bgonna\b", "going to"),
    (r"\bwanna\b", "want to"),
    (r"\bgotta\b", "have to"),
    (r"\bkinda\b", "kind of"),
    (r"\byeah\b", "yes"),
    (r"\byep\b", "yes"),
    (r"\bnope\b", "no"),
    (r"\bidk\b", "I do not know"),
    (r"\bbtw\b", "by the way"),
    (r"\bcan't\b", "cannot"),
    (r"\bwon't\b", "will not"),
    (r"\bdon't\b", "do not"),
    (r"\bisn't\b", "is not"),
    (r"\baren't\b", "are not"),
    (r"\bwasn't\b", "was not"),
    (r"\bweren't\b", "were not"),
    (r"\bhaven't\b", "have not"),
    (r"\bhasn't\b", "has not"),
    (r"\bhadn't\b", "had not"),
    (r"\bi'm\b", "I am"),
    (r"\bi've\b", "I have"),
    (r"\bi'll\b", "I will"),
    (r"\bi'd\b", "I would"),
    (r"\bwe're\b", "we are"),
    (r"\bthey're\b", "they are"),
    (r"\bit's\b", "it is"),
    (r"\bthat's\b", "that is"),
)

HEDGES = (
    r"\bi think\b",
    r"\bi feel like\b",
    r"\bi just\b",
    r"\bjust\b",
    r"\bprobably\b",
    r"\bmaybe\b",
    r"\bkind of\b",
    r"\bsort of\b",
    r"\ba little bit\b",
    r"\bto be honest\b",
    r"\bif that makes sense\b",
)

CODE_HINTS = (
    "code",
    "cursor",
    "vscode",
    "devenv",
    "pycharm",
    "idea",
    "goland",
    "webstorm",
    "nvim",
    "vim",
    "emacs",
    "terminal",
    "powershell",
    "windows terminal",
    "wt",
    "cmd",
    "iterm",
    "alacritty",
    "kitty",
    "gnome-terminal",
    "konsole",
)

EMAIL_HINTS = ("outlook", "thunderbird", "mail", "gmail", "mailbox")
CHAT_HINTS = ("slack", "discord", "teams", "telegram", "whatsapp", "signal", "messages")


@dataclass
class PolishResult:
    text: str
    command: str | None = None
    command_only: bool = False
    discarded: bool = False


def load_vocabulary(path: Path | None = None) -> list[tuple[str, str]]:
    path = path or dictionary_path()
    if not path.exists():
        return []
    pairs: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        spoken, written = line.split("=", 1)
        spoken, written = spoken.strip(), written.strip()
        if spoken and written:
            pairs.append((spoken, written))
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return pairs


def dictionary_text() -> str:
    path = dictionary_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def save_dictionary(text: str) -> Path:
    return atomic_write_text(dictionary_path(), text)


def _collapse(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?]){2,}", r"\1", text)
    return text.strip(" \t")


def _remove_fillers(text: str) -> str:
    for pattern in FILLERS:
        text = re.sub(rf",?\s*{pattern}\s*,?", " ", text, flags=re.IGNORECASE)
    # Discourse "like" only: " , like, " or leading "Like, "
    text = re.sub(r"(?:,|\s)\s*like\s*,", ",", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*like,\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:okay|ok|so|alright)[, ]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r",\s*right\??\s*$", "", text, flags=re.IGNORECASE)
    return _collapse(text)


def _spoken_punct(text: str) -> str:
    for pattern, repl in SPOKEN_PUNCT:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([.,!?:;)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    return _collapse(text)


DICTATION_FIXES = (
    (r"\bim\b", "I'm"),
    (r"\bive\b", "I've"),
    (r"\bdont\b", "don't"),
    (r"\bdoesnt\b", "doesn't"),
    (r"\bdidnt\b", "didn't"),
    (r"\bcant\b", "can't"),
    (r"\bwont\b", "won't"),
    (r"\bisnt\b", "isn't"),
    (r"\barent\b", "aren't"),
    (r"\bwasnt\b", "wasn't"),
    (r"\bwerent\b", "weren't"),
    (r"\bhasnt\b", "hasn't"),
    (r"\bhavent\b", "haven't"),
    (r"\bhadnt\b", "hadn't"),
    (r"\bwouldnt\b", "wouldn't"),
    (r"\bcouldnt\b", "couldn't"),
    (r"\bshouldnt\b", "shouldn't"),
    (r"\bthats\b", "that's"),
    (r"\bwhats\b", "what's"),
    (r"\bwheres\b", "where's"),
    (r"\btheres\b", "there's"),
    (r"\bheres\b", "here's"),
    (r"\byoure\b", "you're"),
    (r"\btheyre\b", "they're"),
    (r"\blets\b", "let's"),
)

QUESTION_START = re.compile(
    r"^(what|what's|whats|who|who's|where|when|why|how|is|are|am|do|does|did|"
    r"can|could|would|should|will|won't|have|has|had)\b",
    re.IGNORECASE,
)

# Spoken expansions for acronyms that have a word pronunciation. Applied after
# letter runs are merged. The names dictionary is the user's permanent home for
# more of these ("sequel = SQL" etc.); this list covers the near-universal ones.
ACRONYM_FIXES = (
    (r"\bmy\s+sequel\b", "MySQL"),
    (r"\bsequel\s+server\b", "SQL Server"),
    (r"\bsequel\b", "SQL"),
)

# "s q l" -> "SQL", "ls dash l a" -> "ls -la" in one pass. Runs of 2-6 spoken
# letters (or letter/symbol mixes) merge together: pure letters uppercased like
# an acronym, runs with a symbol token keep spoken case (shell commands, paths).
# Normal words are never single letters, so false positives need someone
# literally dictating isolated tokens in a row — which is what we want to catch.
_SPOKEN_SYMBOLS = {
    "dash": "-",
    "minus": "-",
    "dot": ".",
    "slash": "/",
    "underscore": "_",
    "pipe": "|",
    "equals": "=",
    "star": "*",
    "percent": "%",
    "tilde": "~",
}
_RUN_TOKEN = r"[A-Za-z]|" + "|".join(_SPOKEN_SYMBOLS)
_LETTER_RUN = re.compile(
    # Treat apostrophes as part of the surrounding word. Otherwise the
    # ``s a`` in ``there's a`` is mistaken for an acronym and becomes ``SA``.
    rf"(?<![\w'’])(?:{_RUN_TOKEN})(?:[ \t]+(?:{_RUN_TOKEN})){{1,11}}(?![\w'’])",
    re.IGNORECASE,
)


def _merge_letter_runs(text: str) -> str:
    def merge(match: re.Match) -> str:
        tokens = match.group(0).lower().split()
        if any(token in _SPOKEN_SYMBOLS for token in tokens):
            # Command/path run: keep spoken case, symbols attach to what follows.
            out = ""
            previous_symbol = False
            for token in tokens:
                if token in _SPOKEN_SYMBOLS:
                    if out and not previous_symbol:
                        out += " "
                    out += _SPOKEN_SYMBOLS[token]
                    previous_symbol = True
                else:
                    out += token
                    previous_symbol = False
            return out
        return "".join(token.upper() for token in tokens)

    return _LETTER_RUN.sub(merge, text)


def _merge_acronyms(text: str) -> str:
    text = _merge_letter_runs(text)
    for pattern, repl in ACRONYM_FIXES:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def _fix_pronouns(text: str) -> str:
    return re.sub(r"\bi\b", "I", text)


def _light_grammar(text: str) -> str:
    for pattern, repl in DICTATION_FIXES:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def _tidy_spacing(text: str) -> str:
    text = _collapse(text)
    text = re.sub(r"([.!?])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return _collapse(text)


def stitch_to_previous(previous: str, incoming: str) -> str:
    """Insert this take after the last one as a new sentence, with a space."""
    incoming = (incoming or "").strip()
    if not incoming:
        return incoming
    if incoming[0].islower():
        incoming = incoming[0].upper() + incoming[1:]
    previous = previous or ""
    prev = previous.rstrip()
    if not prev:
        return incoming
    if "\n" in previous[len(prev):] or "\r" in previous[len(prev):]:
        return incoming
    if prev.rstrip("\"'’”)]").endswith((".", "!", "?", ":")):
        return ("" if previous[-1:].isspace() else " ") + incoming
    return ". " + incoming


def _strip_hallucinations(text: str) -> str:
    cleaned = HALLUCINATION_TAIL.sub("", text).strip(" \t")
    return cleaned if cleaned.strip() else text


def _quoted_at(text: str, position: int) -> bool:
    """Recognize command references in quotes, without treating contractions as quotes."""
    closing = None
    for index, char in enumerate(text[:position]):
        if closing:
            if char == closing:
                closing = None
        elif char in {"'", "’"} and index and text[index - 1].isalnum():
            continue
        elif char in {'"', "'", "“", "‘", "`"}:
            closing = {"“": "”", "‘": "’"}.get(char, char)
    return closing is not None


def _command_reference_at(text: str, position: int) -> bool:
    return _quoted_at(text, position) or bool(re.search(
        r"\b(?:say|said|saying|phrase|words?|command|called|means?)\s*[:;,]?\s*$",
        text[:position], re.IGNORECASE))


def _apply_corrections(text: str) -> str:
    # Repeated word: "the the" -> "the"
    text = re.sub(r"\b(\w+)(?:\s+\1)+\b",
                  lambda m: m.group(0) if m.group(1).lower() in _SPOKEN_SYMBOLS else m.group(1),
                  text, flags=re.IGNORECASE)
    others = [marker for marker in CORRECTION_MARKERS if marker != r"\bi mean\b"]
    matches = [m for m in re.finditer("|".join(others), text, flags=re.IGNORECASE)
               if not _command_reference_at(text, m.start())]
    if matches:
        kept = text[matches[-1].end():].strip(" ,;:-")
        if kept:
            text = kept
    # "I mean" is a correction only when there is text on both sides.
    match = re.search(r"\bi mean\b", text, flags=re.IGNORECASE)
    if match and not _quoted_at(text, match.start()):
        before = text[: match.start()].strip(" ,;:-")
        after = text[match.end() :].strip(" ,;:-")
        if before and after:
            return after
    return text


def _apply_vocabulary(text: str, vocab: list[tuple[str, str]]) -> str:
    for spoken, written in vocab:
        text = re.sub(rf"\b{re.escape(spoken)}\b", written, text, flags=re.IGNORECASE)
    return text


def _split_command(text: str) -> tuple[str, str | None]:
    original = text
    scratch = re.match(r"^scratch(?:\s*,\s*|\s+)that\b", text, re.IGNORECASE)
    if scratch:
        tail = text[scratch.end():]
        if not tail.strip(" \t.!?,:;"):
            return "", "discard"
        if re.match(r"\s*[,;:.!?]\s*\S", tail):
            return tail.lstrip(" \t,;:.!?"), "replace"
    # Whisper normally adds sentence punctuation, including to command-only takes.
    text = text.rstrip(" .!?:;")
    lowered = text.lower().strip()
    for phrase, name in sorted(COMMANDS, key=lambda item: len(item[0]), reverse=True):
        if lowered == phrase:
            return "", name
        if lowered.endswith(phrase):
            start = len(lowered) - len(phrase)
            if _command_reference_at(text, start):
                continue
            if start and lowered[start - 1].isalnum():
                continue
            body = text[: len(text) - len(phrase)].rstrip(" ,.;:-")
            body = re.sub(r"\bas$", "", body, flags=re.IGNORECASE).strip(" ,.;:-")
            return body, name
        if phrase.startswith(("make a list", "make a numbered", "make a bullet", "make a bulleted")):
            for glue in (" of ", " "):
                prefix = phrase + glue
                if lowered.startswith(prefix):
                    return text[len(prefix) :].strip(" ,.;:-"), name
    return original, None


LIST_REQUEST = re.compile(
    r"\b(?:please\s+)?make(?:\s+(?:this|it))?\s+a\s+"
    r"(?:(?P<style>bulleted|bullet|bolded|numbered)\s+)?list\b(?:\s+of\b)?",
    re.IGNORECASE,
)


def _list_request_is_command(text: str, request: re.Match[str]) -> bool:
    """Avoid turning a sentence about making a list into a list command."""
    before = text[:request.start()].rstrip()
    if not before:
        return True
    # A phrase such as "so that we can say make a list" reports a possible
    # command rather than issuing one. Keep the shorter, explicit "say make a
    # list" form available for dictated commands embedded in a take.
    if re.search(r"\b(?:so that\s+)?(?:we|you|i)\s+can\s+say\s*$", before,
                 flags=re.IGNORECASE):
        return False
    # Reported or hypothetical statements such as "I can make a list" and
    # "I said make a list" are prose, while an imperative embedded after
    # filler ("I'm gonna say make a list ...") remains available below.
    if re.search(r"\b(?:i|we|you|they)\s+(?:can|could|might|would|will|said)\s*$",
                 before, flags=re.IGNORECASE):
        return False
    # Imperative/quoted commands commonly follow other words. Planning and
    # reported intent commonly follow these phrases and should stay prose.
    return re.search(
        r"\b(?:don't|do not|didn't|did not|want to|need to|have to|should|could|"
        r"would|might|will)\s*$",
        before,
        flags=re.IGNORECASE,
    ) is None
_NUMBER_ITEM = r"(?:\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)\b"
_NUMBER_SEQUENCE = re.compile(
    rf"^{_NUMBER_ITEM}(?:(?:\s*,\s*(?:and\s+)?|\s+(?:and\s+)?){_NUMBER_ITEM})+",
    re.IGNORECASE,
)


def _list_payload(text: str) -> tuple[str, str]:
    """An explicit end marker supports prose after a list without guessing items."""
    parts = re.split(r"\bend (?:the )?list\b", text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return parts[0].strip(" ,:;"), parts[1].lstrip(" ,.;:!?")
    # A short counting test has an unambiguous end even when the speaker keeps
    # talking: 'one two three just because ...' must not become one giant item.
    numbers = _NUMBER_SEQUENCE.match(text)
    if numbers:
        remainder = text[numbers.end():]
        if not remainder or remainder[0] in " ,.;:!?":
            return numbers.group(0), remainder.lstrip(" ,.;:!?")
    return text, ""


LIST_LEAD = re.compile(
    r"^(?:please\s+)?(?:make|write|give me|create|get)\s+(?:me\s+)?(?:a\s+)?(?:list of|the following)\s+",
    re.IGNORECASE,
)
ITEM_SPLIT = re.compile(
    r"\s*\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"next|then|also|and then)\b\s*",
    re.IGNORECASE,
)


_LIST_STOP = {"the", "a", "an", "to", "for", "of", "in", "on", "with"}


def _expand_bare_words(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        words = item.split()
        if 2 <= len(words) <= 5 and all(
            word.isalpha() and word.lower() not in _LIST_STOP and len(word) < 16 for word in words
        ):
            out.extend(words)
        else:
            out.append(item)
    return out


def split_items(text: str) -> list[str]:
    text = LIST_LEAD.sub("", (text or "").strip()).strip(" .")
    if not text:
        return []
    # Explicit item boundaries take priority over words inside an item (for
    # example "research and development" or "first aid supplies").
    marked = re.split(r"\b(?:next\s+)?bullet\s+point\b\s*[:,-]?\s*", text,
                      flags=re.IGNORECASE)
    if len(marked) > 1 and not marked[0].strip(" .,:;"):
        return [part.strip(" .,:;") for part in marked[1:] if part.strip(" .,:;")]
    if "," in text:
        bits = [re.sub(r"^and\s+", "", part.strip(" ."), flags=re.IGNORECASE)
                for part in text.split(",") if part.strip(" .")]
        if len(bits) >= 2:
            return [part for part in bits if part]
    # Recognizers may return '1 2 3' rather than 'one two three'.
    if re.fullmatch(r"\d+(?:\s+\d+)+", text):
        return text.split()
    numbered = re.split(r"\s*\b\d+[.)]\s*", text)
    numbered = [part.strip(" .") for part in numbered if part.strip()]
    if len(numbered) >= 2:
        return numbered
    stepped = [part.strip(" .") for part in ITEM_SPLIT.split(text) if part.strip()]
    if len(stepped) >= 2:
        return stepped
    anded = [part.strip(" .") for part in re.split(r"\band\b", text) if part.strip()]
    if len(anded) >= 2:
        return _expand_bare_words(anded)
    sentences = [part.strip(" .") for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if len(sentences) >= 2:
        return sentences
    return _expand_bare_words([text])


def _to_list(text: str, *, numbered: bool) -> str:
    items = split_items(text)
    if not items:
        return text
    lines = []
    for index, item in enumerate(items, 1):
        item = item.strip(" .;:")
        if not item:
            continue
        item = item[:1].upper() + item[1:]
        lines.append(f"{index}. {item}" if numbered else f"- {item}")
    return "\n".join(lines)


def _sentence_case(text: str, code_mode: bool) -> str:
    if code_mode or not text:
        return text
    pieces = re.split(r"([.!?]\s+|\n+)", text)
    out: list[str] = []
    capitalize_next = True
    for piece in pieces:
        if not piece:
            continue
        if re.fullmatch(r"[.!?]\s+|\n+", piece):
            out.append(piece)
            capitalize_next = True
            continue
        if capitalize_next:
            out.append(piece[:1].upper() + piece[1:])
            capitalize_next = False
        else:
            out.append(piece)
    result = "".join(out)
    if result and result[-1] not in ".!?:\n":
        if QUESTION_START.match(result):
            result += "?"
        elif len(result.split()) >= 2:
            result += "."
    return result


def _shorter(text: str) -> str:
    text = _remove_fillers(text)
    for pattern in HEDGES:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = _collapse(text)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) > 2:
        text = " ".join(sentences[:2]).strip()
    return text


def _professional(text: str) -> str:
    for pattern, repl in CONTRACTIONS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    text = _shorter(text)
    return text


def _apply_command(text: str, command: str | None) -> str:
    if command == "discard":
        return ""
    if command == "paragraph":
        return (text + "\n\n") if text else "\n\n"
    if command == "newline":
        return (text + "\n") if text else "\n"
    if command == "shorter":
        return _shorter(text)
    if command == "professional":
        return _professional(text)
    if command == "bullets":
        return _to_list(text, numbered=False)
    if command == "numbered":
        return _to_list(text, numbered=True)
    return text


def infer_style(app_name: str) -> str:
    name = (app_name or "").lower()
    # Windows supplies "executable.exe window title"; title words must not
    # switch a browser or chat app into code mode. macOS supplies the process
    # name; X11 titles conventionally put the application after the last dash.
    executable = re.match(r"^([^\s]+)\.exe(?:\s|$)", name)
    app_identity = executable.group(1) if executable else re.split(r"\s+[—–-]\s+", name)[-1]

    def has_hint(hints: tuple[str, ...], source: str = name) -> bool:
        return any(
            re.search(rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])", source)
            for hint in hints
        )

    if has_hint(CODE_HINTS, app_identity):
        return "code"
    if has_hint(EMAIL_HINTS):
        return "email"
    if has_hint(CHAT_HINTS):
        return "chat"
    return "default"


def polish_local(
    raw: str,
    *,
    app_name: str = "",
    vocab: list[tuple[str, str]] | None = None,
    remove_fillers: bool = True,
    fix_corrections: bool = True,
    text_cleanup: bool = True,
) -> PolishResult:
    if not text_cleanup:
        return PolishResult(raw or "")
    text = (raw or "").strip()
    if not text:
        return PolishResult("")

    style = infer_style(app_name)
    request = LIST_REQUEST.search(text) if style != "code" else None
    if request is not None and _list_request_is_command(text, request):
        tail = text[request.end():].lstrip(" ,:;").rstrip(" .!?")
        if tail:
            items, following = _list_payload(tail)
            options = dict(app_name=app_name, vocab=vocab, remove_fillers=remove_fillers,
                           fix_corrections=fix_corrections)
            before = text[:request.start()].rstrip(" ,:;")
            # Each recursive call consumes the command, so the list can sit
            # inside a longer take without applying list formatting to its prose.
            cleaned = polish_local(items, **options)
            if cleaned.discarded:
                return cleaned
            numbered = (request.group("style") or "").lower() == "numbered"
            sections = []
            if before:
                sections.append(polish_local(before, **options).text)
            sections.append(_to_list(cleaned.text, numbered=numbered))
            if following:
                sections.append(polish_local(following, **options).text)
            return PolishResult("\n\n".join(part for part in sections if part),
                                command="numbered" if numbered else "bullets")

    body, command = _split_command(text) if style != "code" else (text, None)
    command_only = bool(command) and not body.strip()
    if command == "discard" and command_only:
        return PolishResult("", command=command, command_only=True, discarded=True)

    if remove_fillers:
        body = _remove_fillers(body)
    if fix_corrections and style != "code":
        body = _apply_corrections(body)
    body = _spoken_punct(body)
    # Pronouns before letter runs: "a p i" still merges (run is case-insensitive)
    # and this keeps a dictated "dash i" flag from being uppercased afterwards.
    body = _fix_pronouns(body)
    body = _merge_acronyms(body)
    body = _light_grammar(body)
    body = _apply_vocabulary(body, vocab if vocab is not None else load_vocabulary())
    body = _apply_command(body, command)
    if command == "discard":
        return PolishResult("", command=command, discarded=True)

    style = infer_style(app_name)
    if style == "code":
        # A spoken single dash before a full word joins a compound name;
        # double dash starts a long option, and single-letter runs form flags.
        body = re.sub(r"\b(?:dash|minus)\s+(?:dash|minus)\b", "--", body, flags=re.IGNORECASE)
        body = re.sub(r"(?<=\w)\s+(?:dash|minus)\s+(?=\w{2})", "-", body, flags=re.IGNORECASE)
        # Shell/editor dictation, minimal: symbol words become symbols; path
        # pieces (dot, slash, underscore) bind on both sides; other operators
        # attach to what follows. No command grammar — shells tolerate the rest.
        for word, symbol in _SPOKEN_SYMBOLS.items():
            body = re.sub(rf"\b{word}\b", symbol, body, flags=re.IGNORECASE)
        # Resolve double-dashes at the word level BEFORE any attach-right logic.
        body = re.sub(r"(-)\s+(-)", r"\1\2", body)
        for symbol in {".", "/", "_"}:
            pattern = re.escape(symbol)
            body = re.sub(rf"\s*{pattern}\s*", symbol, body)
        body = re.sub(r"(-+)\s+", r"\1", body)
        body = re.sub(r"\s*\|\s*", " | ", body)
        for symbol in {"=", "*", "~"}:
            pattern = re.escape(symbol)
            body = re.sub(rf"(?<!{pattern}){pattern}\s+", symbol, body)
        body = _collapse(body)
    if command not in {"newline", "paragraph", "bullets", "numbered"}:
        if command == "professional":
            body = _professional(body)
        if style != "code":
            # Normalize punctuation spacing before sentence casing so a fused
            # take such as ``sentence.the next`` gets a capital T.
            body = _tidy_spacing(body)
        body = _sentence_case(body, code_mode=(style == "code"))
    body = _strip_hallucinations(body)
    if command not in {"newline", "paragraph", "bullets", "numbered"}:
        if code := (style == "code"):
            # _tidy_spacing adds a space mid-word after '.', losing note.txt
            body = _collapse(body)
        else:
            body = _tidy_spacing(body)
    else:
        body = _collapse(body)
    return PolishResult(body, command=command, command_only=command_only)


def apply_edit(text: str, command: str | None) -> str:
    return _apply_command(text, command)


def polish(
    raw: str,
    *,
    app_name: str = "",
    vocab: list[tuple[str, str]] | None = None,
    remove_fillers: bool = True,
    fix_corrections: bool = True,
    text_cleanup: bool = True,
) -> PolishResult:
    return polish_local(
        raw,
        app_name=app_name,
        vocab=vocab,
        remove_fillers=remove_fillers,
        fix_corrections=fix_corrections,
        text_cleanup=text_cleanup,
    )
