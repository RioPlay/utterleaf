"""Private-data-free presentation of Settings save progress.

This module describes reported progress only; it does not save, retry, reload,
or imply that multiple settings files form a transaction.
"""

from dataclasses import dataclass

from utterleaf.settings import SettingsSaveError


@dataclass(frozen=True)
class SaveFailure:
    title: str
    message: str
    status: str


_SAVE_SEQUENCES = (
    ("dictation settings", "vocabulary", "start at login"),
    ("dictation settings", "start at login"),
)
_RETRY = "Your form entries are kept. Try Save again."
_RELOAD_NOTICE = (
    "The running app could not be notified. "
    "After saving, quit and reopen Utterleaf."
)


def _confirmed_progress(error: Exception):
    """Accept only a complete split of the actual persistence sequence."""
    if not isinstance(error, SettingsSaveError):
        return None
    saved = getattr(error, "saved", None)
    failed = getattr(error, "failed", None)
    pending = getattr(error, "pending", None)
    if (
        type(saved) is not tuple
        or type(pending) is not tuple
        or type(failed) is not str
        or any(type(label) is not str for label in (*saved, *pending))
    ):
        return None
    for steps in _SAVE_SEQUENCES:
        for index, label in enumerate(steps):
            if saved == steps[:index] and failed == label and pending == steps[index + 1:]:
                # Return internal labels, never values supplied by the exception.
                return steps[:index], label, steps[index + 1:]
    return None


def save_failure(
    error: Exception, *, started: bool = True, reload_failed: bool = False
) -> SaveFailure:
    """Summarize an unsuccessful attempt without exposing exception details.

    ``started=False`` is the caller's confirmation that its save worker never
    started. Unknown or malformed progress cannot establish what was written.
    ``reload_failed`` adds a separate notification warning, not an apply claim.
    """
    if not started:
        title = status = "Save did not start"
        message = f"This save attempt made no changes.\n\n{_RETRY}"
    else:
        progress = _confirmed_progress(error)
        if progress is None:
            title = status = "Couldn't finish saving"
            message = (
                "Save progress could not be confirmed. "
                "Some changes may have been saved.\n\n"
                f"{_RETRY}"
            )
        else:
            saved, failed, pending = progress
            title = "Some changes were saved" if saved else "Couldn't save settings"
            status = "Some changes saved" if saved else "Couldn't finish saving"
            message = (
                f"Saved: {', '.join(saved) or 'none'}.\n"
                f"Not saved: {failed}.\n"
                f"Not attempted: {', '.join(pending) or 'none'}.\n\n"
                f"{_RETRY}"
            )
    if reload_failed:
        message += f"\n\n{_RELOAD_NOTICE}"
    return SaveFailure(title=title, message=message, status=status)
