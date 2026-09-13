"""Prepare our own dictation payload without inspecting the destination editor."""
from dataclasses import dataclass
import re

from .polish import stitch_to_previous


@dataclass(frozen=True)
class Delivery:
    text: str
    prefix: str = ""
    suffix: str = ""

    @property
    def payload(self) -> str:
        return self.prefix + self.text + self.suffix


def _prose_suffix(text: str) -> str:
    # A final line break or list item is intentional layout, not a prose join.
    if not text or text[-1].isspace():
        return ""
    last_line = text.splitlines()[-1]
    if re.match(r"\s*(?:[-*\u2022]|\d+[.)])\s", last_line):
        return ""
    return " " if re.search(r"[.!?][\"'\u2019\u201d\)\]]*$", last_line) else ""


def _structured_suffix(text: str) -> str:
    """Keep the next insertion outside a completed explicit list."""
    if not text or text[-1].isspace():
        return ""
    last_line = text.splitlines()[-1]
    if re.match(r"\s*(?:[-*\u2022]|\d+[.)])\s", last_line):
        return "\n"
    return _prose_suffix(text) if "\n\n" in text else ""


def _context_prefix(text: str, command: str | None,
                    neighbors: tuple[str, str] | None) -> str:
    if neighbors is None or not text or text[0].isspace():
        return ""
    before, _ = neighbors
    if not before:
        return ""
    if command in {"bullets", "numbered"}:
        return "\n"
    if command == "heading":
        return "\n\n"
    if before.isspace() or text[0] in ",.;:!?)]}":
        return ""
    if before.isalnum() or before in "\"'\u2019\u201d)]":
        return " "
    return ""


def _block_prefix(previous_delivered: str, neighbors: tuple[str, str] | None,
                  breaks: int) -> str:
    if previous_delivered:
        existing = len(previous_delivered) - len(previous_delivered.rstrip("\n"))
        return "\n" * max(0, breaks - existing)
    if neighbors is None or not neighbors[0] or neighbors[0] in "\r\n":
        return ""
    return "\n" * breaks


def _context_suffix(suffix: str, neighbors: tuple[str, str] | None) -> str:
    if neighbors is None:
        return suffix
    _, after = neighbors
    # Newlines are structural delimiters: a following horizontal space or
    # punctuation cannot replace them. Keep prose's durable separator at an
    # end-of-field so a later take still has a safe boundary.
    if "\n" in suffix:
        return suffix
    # Preserve destination whitespace and never introduce a space before
    # punctuation, except that an empty field needs the durable suffix above.
    if after and (after.isspace() or after in ",.;:!?)]}"):
        return ""
    return suffix


def _avoid_right_delimiter(text: str, neighbors: tuple[str, str] | None) -> str:
    """Avoid a duplicate/clustered inferred full stop at a verified caret."""
    if neighbors is not None and text.endswith(".") and neighbors[1] and neighbors[1] in ".,;:":
        return text[:-1]
    return text


def prepare_delivery(text: str, *, previous_delivered: str = "",
                     text_cleanup: bool = True, code_mode: bool = False,
                     command: str | None = None,
                     neighbors: tuple[str, str] | None = None,
                     markdown: bool = False) -> Delivery:
    """Separate semantic text from spacing included in a verified edit receipt.

    Pass previous_delivered only for an independently established continuation.
    The trailing separator remains useful when that context later expires.
    Replacement/copy callers must choose their own verified destination first.
    """
    if not text.strip() or not text_cleanup or code_mode:
        return Delivery(text)
    if command in {"discard", "replace"}:
        return Delivery(text)
    if command in {"bullets", "numbered", "paragraph", "newline", "heading"}:
        if command in {"bullets", "numbered", "heading"}:
            breaks = 2 if command == "heading" or markdown else 1
            prefix = _block_prefix(previous_delivered, neighbors, breaks)
        else:
            prefix = "\n" if previous_delivered else _context_prefix(text, command, neighbors)
        suffix = "\n\n" if command == "heading" or markdown and command in {"bullets", "numbered"} else _structured_suffix(text)
        return Delivery(text, prefix, _context_suffix(suffix, neighbors))
    # Preserve explicit line formatting, including whitespace after a newline.
    if "\n" in text or "\r" in text:
        prefix = ""
        if previous_delivered and not text[0].isspace():
            stitched = stitch_to_previous(previous_delivered, text)
            prefix = stitched[:-len(text.strip())]
        return Delivery(text, prefix or _context_prefix(text, command, neighbors),
                        _context_suffix(_prose_suffix(text), neighbors))
    body = _avoid_right_delimiter(text.strip(), neighbors)
    stitched = stitch_to_previous(previous_delivered, body)
    if body and body[0].islower():
        body = body[0].upper() + body[1:]
    prefix = stitched[:-len(body)] if body else ""
    suffix = " " if re.search(r"[.!?][\"'’”\)\]]*$", body) else ""
    return Delivery(body, prefix or _context_prefix(body, command, neighbors),
                    _context_suffix(suffix, neighbors))
