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


def prepare_delivery(text: str, *, previous_delivered: str = "",
                     text_cleanup: bool = True, code_mode: bool = False,
                     command: str | None = None) -> Delivery:
    """Separate semantic text from spacing included in a verified edit receipt.

    Pass previous_delivered only for an independently established continuation.
    The trailing separator remains useful when that context later expires.
    Replacement/copy callers must choose their own verified destination first.
    """
    if not text.strip() or not text_cleanup or code_mode:
        return Delivery(text)
    if command in {"discard", "replace"}:
        return Delivery(text)
    if command in {"bullets", "numbered", "paragraph", "newline"}:
        return Delivery(text, "\n" if previous_delivered else "")
    # Preserve explicit line formatting, including whitespace after a newline.
    if "\n" in text or "\r" in text:
        return Delivery(text)
    stitched = stitch_to_previous(previous_delivered, text)
    body = text.strip()
    if body and body[0].islower():
        body = body[0].upper() + body[1:]
    prefix = stitched[:-len(body)] if body else ""
    suffix = " " if re.search(r"[.!?][\"'’”\)\]]*$", body) else ""
    return Delivery(body, prefix, suffix)
