"""Pure save recovery copy never promotes private exception data into UI."""

import pytest

from utterleaf.save_presentation import SaveFailure, save_failure
from utterleaf.settings import SettingsSaveError


PRIVATE = r"C:\Users\Private Person\secret-dictation.toml: private hotkey"
SEQUENCES = (
    ("dictation settings", "vocabulary", "start at login"),
    ("dictation settings", "start at login"),
)
SPLITS = [
    (steps[:index], label, steps[index + 1:])
    for steps in SEQUENCES
    for index, label in enumerate(steps)
]


def failure(saved=(), failed="dictation settings", pending=("vocabulary", "start at login")):
    return SettingsSaveError(saved, failed, pending, OSError(PRIVATE))


def public_text(presentation):
    return "\n".join((presentation.title, presentation.message, presentation.status))


@pytest.mark.parametrize("saved,failed,pending", SPLITS)
def test_all_actual_save_stages_preserve_exact_progress(saved, failed, pending):
    error = failure(saved, failed, pending)
    result = save_failure(error)

    assert isinstance(result, SaveFailure)
    assert result.message.split("\n\n")[0].splitlines() == [
        f"Saved: {', '.join(saved) or 'none'}.",
        f"Not saved: {failed}.",
        f"Not attempted: {', '.join(pending) or 'none'}.",
    ]
    assert result.title == ("Some changes were saved" if saved else "Couldn't save settings")
    assert result.status == ("Some changes saved" if saved else "Couldn't finish saving")
    assert "Your form entries are kept. Try Save again." in result.message
    assert PRIVATE not in public_text(result)
    assert not any(claim in public_text(result).lower() for claim in ("rollback", "rolled back", "applied"))


def test_omitted_vocabulary_is_not_described_as_saved_or_pending():
    result = save_failure(failure(("dictation settings",), "start at login", ()))
    assert "vocabulary" not in public_text(result)


@pytest.mark.parametrize("field,value", [
    ("saved", ["dictation settings"]),
    ("saved", "dictation settings"),
    ("saved", None),
    ("saved", ("dictation settings", "dictation settings")),
    ("saved", ("vocabulary", "dictation settings")),
    ("saved", (PRIVATE,)),
    ("saved", (object(),)),
    ("failed", PRIVATE),
    ("failed", None),
    ("failed", ("vocabulary",)),
    ("failed", b"vocabulary"),
    ("pending", ["start at login"]),
    ("pending", "start at login"),
    ("pending", None),
    ("pending", ("start at login", "start at login")),
    ("pending", ("vocabulary", "start at login")),
    ("pending", (PRIVATE,)),
    ("pending", ()),
])
def test_malformed_progress_falls_back_without_echoing_metadata(field, value):
    error = failure(("dictation settings",), "vocabulary", ("start at login",))
    setattr(error, field, value)
    assert save_failure(error) == save_failure(RuntimeError(PRIVATE))


@pytest.mark.parametrize("field", ["saved", "failed", "pending"])
def test_missing_progress_field_is_unknown(field):
    error = failure()
    delattr(error, field)
    assert save_failure(error) == save_failure(RuntimeError(PRIVATE))


def test_empty_or_incomplete_sequence_is_not_confirmed_progress():
    result = save_failure(failure((), "dictation settings", ()))
    assert result == save_failure(RuntimeError(PRIVATE))


def test_generic_failure_does_not_claim_nothing_was_saved():
    result = save_failure(RuntimeError(PRIVATE))
    assert result.title == result.status == "Couldn't finish saving"
    assert result.message == (
        "Save progress could not be confirmed. Some changes may have been saved.\n\n"
        "Your form entries are kept. Try Save again."
    )
    assert PRIVATE not in public_text(result)
    assert "no changes" not in public_text(result).lower()
    assert "Saved:" not in result.message


def test_unrelated_exception_cannot_supply_confirmed_progress():
    error = RuntimeError(PRIVATE)
    error.saved = ("dictation settings",)
    error.failed = "vocabulary"
    error.pending = ("start at login",)
    assert save_failure(error) == save_failure(RuntimeError(PRIVATE))


def test_error_message_and_cause_are_never_formatted():
    class UnprintableError(RuntimeError):
        def __str__(self):
            pytest.fail("Recovery copy must not stringify exceptions")

    class UnprintableSaveError(SettingsSaveError):
        def __str__(self):
            pytest.fail("Recovery copy must not stringify save exceptions")

    generic = UnprintableError(PRIVATE)
    structured = UnprintableSaveError(
        ("dictation settings",), "vocabulary", ("start at login",), PRIVATE
    )
    structured.__cause__ = generic
    assert save_failure(generic) == save_failure(RuntimeError(PRIVATE))
    assert save_failure(structured) == save_failure(
        failure(("dictation settings",), "vocabulary", ("start at login",))
    )


def test_metadata_is_not_coerced_or_compared_via_custom_types():
    class UnsafeLabel(str):
        def __eq__(self, other):
            pytest.fail("Malformed metadata must not be compared")

        def __str__(self):
            pytest.fail("Malformed metadata must not be formatted")

    for field, value in (
        ("saved", (UnsafeLabel("dictation settings"),)),
        ("failed", UnsafeLabel("vocabulary")),
        ("pending", (UnsafeLabel("start at login"),)),
    ):
        error = failure(("dictation settings",), "vocabulary", ("start at login",))
        setattr(error, field, value)
        assert save_failure(error) == save_failure(RuntimeError(PRIVATE))


@pytest.mark.parametrize("error", [RuntimeError(PRIVATE), failure(("dictation settings",), "vocabulary", ("start at login",))])
def test_worker_not_started_has_explicit_attempt_scope(error):
    result = save_failure(error, started=False)
    assert result.title == result.status == "Save did not start"
    assert result.message == (
        "This save attempt made no changes.\n\n"
        "Your form entries are kept. Try Save again."
    )
    assert PRIVATE not in public_text(result)


@pytest.mark.parametrize("error,started", [
    (failure(), True),
    (failure(("dictation settings",), "vocabulary", ("start at login",)), True),
    (RuntimeError(PRIVATE), True),
    (RuntimeError(PRIVATE), False),
])
def test_reload_notice_adds_guidance_without_replacing_progress(error, started):
    original = save_failure(error, started=started)
    result = save_failure(error, started=started, reload_failed=True)
    assert result.title == original.title
    assert result.status == original.status
    assert result.message == original.message + (
        "\n\nThe running app could not be notified. "
        "After saving, quit and reopen Utterleaf."
    )
    assert PRIVATE not in public_text(result)
    assert "applied" not in public_text(result).lower()
