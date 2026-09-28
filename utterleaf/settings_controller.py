"""UI-neutral Settings draft and save orchestration.

Presentation layers own widgets and user feedback. This module owns the complete
submitted shape and the durable save/reload outcome without importing Tk, audio,
models, clipboard, or platform UI code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Callable, Mapping

from utterleaf.config import Config
from utterleaf.settings import SettingsSaveError


@dataclass(frozen=True)
class SettingsDraft:
    hotkey: str
    mode: str
    model: str
    device: str
    language: str
    denoise: str
    microphone: str
    beep: bool
    indicator: bool
    live_preview: bool
    remove_fillers: bool
    fix_corrections: bool
    restore_clipboard: bool
    allow_network: bool
    text_cleanup: bool
    output_format: str
    speech_end_enabled: bool
    speech_end_pause_seconds: str | float
    speech_end_insert: bool
    start_at_login: bool
    names: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "SettingsDraft":
        """Copy one complete presentation snapshot and reject shape drift."""

        expected = {field.name for field in fields(cls)}
        supplied = set(values)
        missing = sorted(expected - supplied)
        unexpected = sorted(supplied - expected)
        if missing or unexpected:
            details = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected: {', '.join(unexpected)}")
            raise ValueError(f"Invalid Settings draft shape ({'; '.join(details)})")
        return cls(**{name: values[name] for name in expected})

    def form_values(self) -> dict[str, object]:
        """Return an independent mapping accepted by ``settings.apply_form``."""

        return asdict(self)


@dataclass(frozen=True)
class SaveOutcome:
    config: Config | None = None
    error: Exception | None = None
    reply: str | None = None
    reload_error: Exception | None = None


@dataclass(frozen=True)
class SettingsController:
    """Injected persistence boundary shared by desktop presentation layers."""

    load_config: Callable[[], Config]
    apply_form: Callable[..., Config]
    notify: Callable[[str], str | None]

    def commit(
        self,
        draft: SettingsDraft,
        *,
        reset_defaults: bool = False,
    ) -> SaveOutcome:
        """Persist one submitted draft and report reload state without UI policy."""

        try:
            config = self.apply_form(
                Config() if reset_defaults else self.load_config(),
                **draft.form_values(),
            )
        except SettingsSaveError as error:
            reload_error = None
            if error.saved:
                try:
                    self.notify("reload")
                except Exception as notification_error:
                    reload_error = notification_error
            return SaveOutcome(error=error, reload_error=reload_error)

        try:
            return SaveOutcome(config=config, reply=self.notify("reload"))
        except Exception as error:
            return SaveOutcome(config=config, reload_error=error)


def commit_settings(
    draft: SettingsDraft,
    *,
    reset_defaults: bool,
    load_config: Callable[[], Config],
    apply_form: Callable[..., Config],
    notify: Callable[[str], str | None],
) -> SaveOutcome:
    """Compatibility function for callers that inject individual boundaries."""

    return SettingsController(load_config, apply_form, notify).commit(
        draft,
        reset_defaults=reset_defaults,
    )
