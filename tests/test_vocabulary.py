"""Headless checks for staging personal vocabulary entries."""

import pytest

from utterleaf.vocabulary import append_vocabulary_entry
from utterleaf.settings_ui import SettingsWindow


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _MockText:
    def __init__(self, value, cursor="1.0", selection=("1.0", "1.2")):
        self.value = value
        self.cursor = cursor
        self.selection = selection

    def get(self, start, end):
        assert (start, end) == ("1.0", "end-1c")
        return self.value

    def index(self, index):
        assert index == "insert"
        return self.cursor

    def tag_ranges(self, tag):
        assert tag == "sel"
        return self.selection

    def edit_separator(self):
        pass

    def insert(self, index, value):
        assert index == "end-1c"
        self.value += value

    def mark_set(self, mark, index):
        assert mark == "insert"
        self.cursor = index

    def tag_remove(self, *_args):
        pass

    def tag_add(self, tag, start, end):
        assert tag == "sel"
        self.selection = (start, end)


def _callback_window(draft, spoken, written):
    class FakeWindow:
        pass

    window = FakeWindow()
    window.names = draft
    window.vocabulary_spoken = _Value(spoken)
    window.vocabulary_written = _Value(written)
    window.vocabulary_add_status = _Value("")
    return window


@pytest.mark.parametrize(("spoken", "written"), [
    ("Ada Lovelace", "Ada Lovelace"),
    ("p 53", "p53"),
    ("東京", "東京都"),
    ("résumé", "resume"),
])
def test_appends_names_numbers_and_unicode(spoken, written):
    original = "# keep this comment\nold phrase = Old Phrase\n"
    assert append_vocabulary_entry(original, spoken, written) == original + f"{spoken} = {written}"


def test_preserves_existing_text_and_adds_separator_only_when_needed():
    assert append_vocabulary_entry("# comment\nlegacy invalid", "new", "entry") == (
        "# comment\nlegacy invalid\nnew = entry")


def test_rejects_case_insensitive_duplicate_without_overwriting():
    original = "Known = Original\n"
    with pytest.raises(ValueError, match="already"):
        append_vocabulary_entry(original, "KNOWN", "Replacement")
    assert original == "Known = Original\n"


@pytest.mark.parametrize(("spoken", "written"), [
    ("two\nlines", "value"), ("two\u2028lines", "value"),
    ("phrase\x00", "value"), ("   ", "value"),
    ("# comment", "value"), ("phrase", ""), ("phrase", "two\r\nlines"),
])
def test_rejects_invalid_values(spoken, written):
    with pytest.raises(ValueError):
        append_vocabulary_entry("existing = text", spoken, written)


def test_written_value_may_contain_equals():
    assert append_vocabulary_entry("", "x equals", "x = y") == "x equals = x = y"


def test_invalid_existing_draft_text_is_retained_unchanged():
    original = "# comment\ninvalid line\n"
    assert append_vocabulary_entry(original, "new", "entry") == original + "new = entry"


def test_settings_callback_stages_pair_without_persistence(monkeypatch):
    import utterleaf.settings_ui as settings_ui

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Adding to the draft must not save settings or vocabulary.")

    monkeypatch.setattr(settings_ui, "apply_form", forbidden)
    monkeypatch.setattr(settings_ui, "save_dictionary", forbidden, raising=False)
    original = "# keep\nold = Old\n"
    draft = _MockText(original, cursor="1.3", selection=("1.0", "1.2"))
    window = _callback_window(draft, "new phrase", "New Phrase")

    SettingsWindow.add_vocabulary_entry(window)

    assert draft.value == original + "new phrase = New Phrase"
    assert (draft.cursor, draft.selection) == ("1.3", ("1.0", "1.2"))
    assert window.vocabulary_spoken.get() == window.vocabulary_written.get() == ""
    assert "Save changes" in window.vocabulary_add_status.get()


@pytest.mark.parametrize(("original", "spoken", "written", "expected_error"), [
    ("# retained\nexisting = Existing\n", "bad\nphrase", "Value", "single line"),
    ("# retained\nexisting = Existing\n", "EXISTING", "Replacement", "already"),
])
def test_settings_callback_error_keeps_draft_and_inputs(
        original, spoken, written, expected_error):
    draft = _MockText(original)
    window = _callback_window(draft, spoken, written)

    SettingsWindow.add_vocabulary_entry(window)

    assert draft.value == original
    assert window.vocabulary_spoken.get() == spoken
    assert window.vocabulary_written.get() == written
    assert expected_error in window.vocabulary_add_status.get()
