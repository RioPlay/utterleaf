"""Hold-to-talk loop: record, transcribe, polish, paste."""

from __future__ import annotations

import logging
from collections import deque
from logging.handlers import RotatingFileHandler
import os
import socket
import sys
import threading
import time
from utterleaf.host import is_wayland, pin_tray_backend

# Linux tray backend must be selected before pystray imports (see host.pin_tray_backend).
pin_tray_backend()
from pystray import Icon, Menu, MenuItem

from utterleaf.beep import beep
from utterleaf import edit_target, ipc
from utterleaf.audio import TAIL_SECONDS, Recorder, list_devices, microphone_error_hint
from utterleaf.config import Config, config_path, dictionary_path, log_path
from utterleaf.hotkey import HotkeyWatcher, parse_hotkey
from utterleaf.indicator import Indicator, recording_caption
from utterleaf.inject import copy_text, foreground_app, foreground_id, paste
from utterleaf.polish import polish, stitch_to_previous
from utterleaf.recovery import RecentDictation
from utterleaf.hardware import describe, ov_model_id, pick, probe
from utterleaf.models import ct2_dir, ct2_ready, ov_dir, ov_ready, status_lines
from utterleaf.host import doctor_host_lines
from utterleaf.settings import launch_settings
from utterleaf.theme import leaf_image
from utterleaf.startup import enabled as startup_enabled
from utterleaf.transcribe import (
    clear_final,
    load_model,
    request_final,
    reset_engine,
    resolve_name,
    transcribe,
    transcribe_preview,
)

log = logging.getLogger("utterleaf")

State = str  # idle | recording | busy

LOADING = "loading model"
ENGINE_FAILED = "speech model unavailable"
NO_MIC = "microphone unavailable"
DOWNLOADING = "Downloading your speech model… First use only."
MAX_PENDING_TAKES = 4

# How long a result pill stays up. Failures linger longer than successes.
# engine is omitted on purpose: that pill stays until the model loads.
LINGER = {
    "pasted": 2.0,
    "clipboard": 2.0,
    "missed": 1.2,
    "too_short": 1.2,
    "transcribe": 3.5,
    "no_paste": 3.5,
}


def status_hint(cfg: Config) -> str:
    """Tray / idle copy for the current hotkey mode."""
    if is_wayland():
        return "desktop shortcut: utterleaf --toggle"
    verb = "hold" if cfg.mode == "hold" else "press"
    return f"{verb} {cfg.hotkey}"


def tray_title(status: str) -> str:
    title = f"Utterleaf — {status}"
    if Icon.__module__ == "pystray._xorg":
        # python-xlib encodes the legacy WM_NAME property as Latin-1,
        # both when creating the icon and on every subsequent title update.
        return title.replace("—", "-").replace("…", "...").encode(
            "latin-1", errors="replace"
        ).decode("latin-1")
    return title


def tray_backend() -> str:
    """The pystray backend the import selected; the log/doctor surface for tray problems."""
    return Icon.__module__


def setup_logging() -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8"),
            *([logging.StreamHandler(sys.stderr)] if sys.stderr is not None else []),
        ],
    )


def _hide_console() -> None:
    """Detach from the console so tray mode is only the icon + indicator."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.FreeConsole()
    except Exception:
        pass


def open_path(path) -> None:
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)
        return
    import subprocess

    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


class Utterleaf:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.recorder = Recorder(device=cfg.microphone)
        self.state: State = "idle"
        self.last_text = ""
        self._recent_generation = 0
        self.recent_dictation = RecentDictation(on_expire=self._expire_recovery_context)
        self.last_app = ""
        self.last_target = None
        self.last_paste_at = 0.0
        self._edit_receipt = None
        self._last_prefix = ""
        self._edit_expiry: threading.Timer | None = None
        self._edit_generation = 0
        self._queued_audio = None
        self._queued_target = None
        self._queued_continuation = None
        self._queued_takes = deque()
        self._take_continuation = None
        self._cancel_job = False
        self._job_running = False
        self._preview_stop = threading.Event()
        self._cut_id = 0
        self._tail_done_for = -1
        self._tail_timer: threading.Timer | None = None
        self._tail_args = None
        self._limit_timer: threading.Timer | None = None
        self._countdown_timer: threading.Timer | None = None
        self._recording_deadline = 0.0
        self._recording_draft = ""
        self._lock = threading.Lock()
        self._capture_lock = threading.RLock()
        self._stop = threading.Event()
        self.icon: Icon | None = None
        self.hotkey: HotkeyWatcher | None = None
        self._server: socket.socket | None = None
        self._status = LOADING
        self._indicator_generation = 0
        self.indicator = Indicator(enabled=cfg.indicator and cfg.tray)
        if cfg.tray:
            # Render before installing hotkeys, never on the path to mic start.
            for color in ("idle", "recording", "busy", "error"):
                leaf_image(color)

    def _needs_download(self, chosen) -> bool:
        """True when the picked backend still has to fetch its weights."""
        name = resolve_name(self.cfg)
        if chosen.backend == "openvino":
            repo = ov_model_id(name)
            return not (repo and ov_ready(ov_dir(repo)))
        return not ct2_ready(ct2_dir(name))

    def start_recording(self) -> None:
        with self._capture_lock:
            self._start_recording()

    def _start_recording(self) -> None:
        self._harvest_pending_tail()
        with self._lock:
            full = len(self._queued_takes) + (self._queued_audio is not None) >= MAX_PENDING_TAKES
        if full:
            if self.hotkey is not None:
                self.hotkey.reset_active()
            beep("err", self.cfg.beep)
            self._set_icon("busy", "finishing queued dictation", badge="transcribing",
                           caption="Please wait for queued dictation to finish before starting another take.")
            return
        start_target = foreground_id()
        start_app = foreground_app()
        continuation = None
        if (
            self.last_text
            and start_target == self.last_target
            and start_app == self.last_app
            and (time.time() - self.last_paste_at) < 20
        ):
            # Capture this at key-down. A long decode can finish after the
            # continuation window, but it still belongs to this take.
            continuation = (start_target, start_app)
        with self._lock:
            if self.state == "recording":
                return
            self._cut_id += 1
            self.state = "recording"
            self._take_continuation = continuation
        self._set_icon("busy", "opening microphone", badge="loading", caption="Getting your microphone ready…")
        try:
            self.recorder.start(max_seconds=self.cfg.max_seconds)
            self._recording_deadline = time.monotonic() + self.cfg.max_seconds
            self._recording_draft = ""
            log.info("Recording")
            self._set_icon("recording", "listening", badge="listening",
                           caption=recording_caption(self.cfg.max_seconds))
            beep("start", self.cfg.beep)
            timer = threading.Timer(self.cfg.max_seconds, self._recording_limit, args=(self._cut_id,))
            timer.daemon = True
            self._limit_timer = timer
            timer.start()
            self._update_countdown(self._cut_id)
            if self.cfg.live_preview and self.indicator.enabled:
                self._preview_stop.clear()
                threading.Thread(target=self._preview_loop, args=(self._cut_id,), daemon=True).start()
        except Exception as exc:
            log.exception("Microphone failed")
            self._cancel_limit_timer()
            if self.hotkey is not None:
                self.hotkey.reset_active()
            beep("err", self.cfg.beep)
            with self._lock:
                self.state = "idle"
            self._show_error(
                "no_mic",
                NO_MIC,
                microphone_error_hint(exc),
            )

    def _preview_loop(self, cut_id: int) -> None:
        while not self._preview_stop.wait(0.75):
            if self.state != "recording" or cut_id != self._cut_id:
                return
            if not self.indicator.enabled:
                continue
            audio = self.recorder.snapshot(max_seconds=4.0)
            if self.recorder.seconds(audio) < 0.65:
                continue
            try:
                draft = transcribe_preview(audio, self.cfg)
            except Exception:
                log.debug("Live preview failed", exc_info=True)
                continue
            with self._capture_lock:
                if draft and self.state == "recording" and cut_id == self._cut_id and not self._preview_stop.is_set():
                    self._recording_draft = draft
                    self.indicator.set("listening", recording_caption(
                        self._recording_deadline - time.monotonic(), draft))

    def _update_countdown(self, cut_id: int) -> None:
        with self._capture_lock:
            if self.state != "recording" or cut_id != self._cut_id or self._stop.is_set():
                return
            remaining = self._recording_deadline - time.monotonic()
            self.indicator.set("listening", recording_caption(remaining, self._recording_draft))
            if remaining > 0 and self.indicator.enabled:
                timer = threading.Timer(min(1.0, remaining), self._update_countdown, args=(cut_id,))
                timer.daemon = True
                self._countdown_timer = timer
                timer.start()

    def _recording_limit(self, cut_id: int) -> None:
        self.stop_recording(limit_cut_id=cut_id)

    def _cancel_limit_timer(self) -> None:
        countdown, self._countdown_timer = self._countdown_timer, None
        if countdown is not None:
            countdown.cancel()
        timer, self._limit_timer = self._limit_timer, None
        if timer is not None:
            timer.cancel()

    def stop_recording(self, *, limit_cut_id: int | None = None) -> None:
        with self._capture_lock:
            self._stop_recording(limit_cut_id=limit_cut_id)

    def _stop_recording(self, *, limit_cut_id: int | None = None) -> None:
        with self._lock:
            if self.state != "recording" or (limit_cut_id is not None and limit_cut_id != self._cut_id):
                return
            follow_on = self._job_running
            if not follow_on:
                self._job_running = True
            self.state = "busy"
        self._preview_stop.set()
        self._cancel_limit_timer()
        if limit_cut_id is not None and self.hotkey is not None:
            self.hotkey.reset_active()
        request_final()
        self._set_icon("busy", "transcribing", badge="transcribing",
                       caption="Recording limit reached. Start another take to continue." if limit_cut_id is not None else "")
        beep("stop", self.cfg.beep)
        target = foreground_id()
        cut_id = self._cut_id
        continuation = self._take_continuation
        self._tail_args = (target, follow_on, cut_id, continuation)
        timer = threading.Timer(TAIL_SECONDS, self._cut, args=self._tail_args)
        self._tail_timer = timer
        timer.start()

    def _harvest_pending_tail(self) -> None:
        timer = self._tail_timer
        if timer is None:
            return
        self._tail_timer = None
        timer.cancel()
        # Preserve the release-time target and whether this tail owns the
        # worker reservation. _job_running alone also includes that reservation.
        args = self._tail_args
        if args is not None:
            self._cut(*args)

    def _cut(self, target, follow_on: bool, cut_id: int, continuation=None) -> None:
        with self._capture_lock:
            self._cut_recording(target, follow_on, cut_id, continuation)

    def _cut_recording(self, target, follow_on: bool, cut_id: int, continuation=None) -> None:
        with self._lock:
            if cut_id != self._cut_id or self._tail_done_for == cut_id:
                return
            self._tail_done_for = cut_id
            self._tail_timer = None
        audio = self.recorder.stop()
        try:
            self.recorder.close()
        except Exception:
            # A disconnected device must not discard audio already captured.
            log.warning("Microphone release failed", exc_info=True)
        seconds = self.recorder.seconds(audio)
        if seconds < self.cfg.min_seconds:
            log.info("Ignored short tap (%.2fs)", seconds)
            with self._lock:
                if follow_on and self._job_running:
                    return
                self._cancel_job = False
                self._job_running = False
            clear_final()
            self._flash("too_short")
            return
        with self._lock:
            if follow_on and self._job_running:
                if self._queued_audio is not None:
                    self._queued_takes.append((audio, target, continuation))
                else:
                    self._queued_audio = audio
                    self._queued_target = target
                    self._queued_continuation = continuation
                log.info("Queued next take")
                return
            # The previous decode may have finished during the recording tail.
            self._job_running = True
        threading.Thread(
            target=self._finish, args=(audio, target, continuation), daemon=True
        ).start()

    def cancel_recording(self) -> None:
        with self._capture_lock:
            self._cancel_recording()

    def _cancel_recording(self) -> None:
        self._cancel_limit_timer()
        self._preview_stop.set()
        clear_final()
        self._queued_audio = None
        self._queued_target = None
        self._queued_continuation = None
        self._queued_takes.clear()
        with self._lock:
            if self.state == "recording":
                self.state = "idle"
                self.recorder.stop()
                self.recorder.close()
                log.info("Cancelled")
                self._set_icon("idle", badge="hide")
                beep("err", self.cfg.beep)
                return
            if self.state == "busy":
                self._cancel_job = True
                log.info("Will skip this paste")
                return
        # Idle Esc is left to the focused app (close pickers, leave fullscreen).

    def _finish(self, audio, target=None, continuation=None) -> None:
        try:
            if self._cancel_job:
                self._cancel_job = False
                self._queued_audio = None
                self._queued_target = None
                self._queued_continuation = None
                self._queued_takes.clear()
                log.info("Paste skipped")
                self._after_job()
                return
            app_name = foreground_app()
            decode_started = time.perf_counter()
            raw = transcribe(audio, self.cfg)
            log.info("Dictation timing: audio=%.2fs decode=%.3fs",
                     len(audio) / 16000, time.perf_counter() - decode_started)
            # Esc may arrive during a long decode. Check again before editing
            # or pasting into the user's app, not just before transcription.
            if self._cancel_job or self._stop.is_set():
                self._cancel_job = False
                self._queued_audio = None
                self._queued_target = None
                self._queued_continuation = None
                self._queued_takes.clear()
                self._after_job()
                return
            log.debug("Transcription received (%d characters)", len(raw))
            if not raw:
                self._after_job("missed")
                return
            format_started = time.perf_counter()
            result = polish(
                raw,
                app_name=app_name,
                remove_fillers=self.cfg.remove_fillers,
                fix_corrections=self.cfg.fix_corrections,
                text_cleanup=self.cfg.text_cleanup,
            )
            log.info("Dictation timing: formatting=%.3fs", time.perf_counter() - format_started)
            if result.command_only and self.last_text and (
                not self.last_target
                or foreground_id() != self.last_target
                or (time.time() - self.last_paste_at) >= 20
            ):
                self._after_job("no_paste", "Return to your last dictation to use an edit command.")
                return
            if result.discarded:
                if result.command_only and self.last_text:
                    outcome, self._edit_receipt = edit_target.replace(self._edit_receipt, None)
                    if outcome != "replaced":
                        self._after_job("no_paste", "Select your last dictation and delete it manually. This field could not be verified.")
                        return
                    self.last_text = ""
                    self.last_app = ""
                    self.last_target = None
                    self.last_paste_at = 0.0
                    self.recent_dictation.clear()
                log.info("Discarded")
                self._after_job("hide")
                return
            if result.command_only and result.command and self.last_text:
                from utterleaf.polish import apply_edit, polish_local

                text = apply_edit(self.last_text, result.command)
                if result.command == "professional":
                    text = polish_local(text, app_name="outlook").text or text
                if text and text != self.last_text:
                    self._remember_result(text)
                    outcome, self._edit_receipt = edit_target.replace(self._edit_receipt, self._last_prefix + text)
                    if outcome != "replaced":
                        beep("err", self.cfg.beep)
                        if outcome == "unavailable" and copy_text(text):
                            self._after_job("clipboard", "Revised text copied. Select the old dictation and paste to replace it.")
                        else:
                            self._after_job("no_paste", "Could not verify the edit. Check your text before trying again.")
                        return
                    self.last_text = text
                    self.last_app = app_name
                    self.last_target = target
                    self.last_paste_at = time.time()
                    self._schedule_edit_expiry()
                    beep("ok", self.cfg.beep)
                self._after_job("pasted", text)
                return
            text = result.text
            if not text:
                self._after_job("missed")
                return
            if continuation is None:
                same_place = (
                    app_name
                    and app_name == self.last_app
                    and target == self.last_target
                    and (time.time() - self.last_paste_at) < 20
                )
            else:
                continuation_target, continuation_app = continuation
                same_place = (
                    target == continuation_target == self.last_target
                    and app_name == continuation_app == self.last_app
                )
            previous = self.last_text if same_place else ""
            if not self.cfg.text_cleanup:
                to_paste = text
            elif result.command in {"bullets", "numbered", "paragraph", "newline"}:
                to_paste = ("\n" + text) if previous else text
            else:
                to_paste = stitch_to_previous(previous, text)
            delivery_started = time.perf_counter()
            before = edit_target.read_field()
            self._remember_result(to_paste)
            outcome = paste(
                to_paste,
                restore_clipboard=self.cfg.restore_clipboard,
                target=target,
            )
            log.info("Dictation timing: delivery=%.3fs outcome=%s",
                     time.perf_counter() - delivery_started, outcome)
            if outcome == "pasted":
                self._edit_receipt = edit_target.capture(before, to_paste)
                self._last_prefix = to_paste[:-len(text)] if text and to_paste.endswith(text) else ""
                self.last_text = text.strip()
                self.last_app = app_name
                self.last_target = target
                self.last_paste_at = time.time()
                self._schedule_edit_expiry()
                log.debug("Text delivered (%d characters)", len(to_paste))
                beep("ok", self.cfg.beep)
                self._after_job("pasted", to_paste)
                return
            if outcome == "clipboard":
                beep("err", self.cfg.beep)
                self._after_job("clipboard", to_paste)
                return
            # Heard fine, could not deliver it. Never blame the user's voice.
            beep("err", self.cfg.beep)
            self._after_job("no_paste", "Use Copy last dictation in the tray menu to recover your text.")
            return
        except Exception:
            log.exception("Transcription failed")
            beep("err", self.cfg.beep)
            self._after_job("transcribe", "Try another take. If this repeats, open Settings → Help & diagnostics.")
            return

    def _remember_result(self, text: str) -> None:
        self._recent_generation = self.recent_dictation.put(text)

    def _expire_recovery_context(self, generation: int) -> None:
        if self._recent_generation == generation:
            self._clear_edit_context()

    def copy_last_dictation(self) -> bool:
        text = self.recent_dictation.get()
        if not text:
            self._show_error("no_paste", "nothing to recover", "No recent dictation. Recovery text expires after two minutes.")
            return False
        if not copy_text(text):
            self._show_error("no_paste", "clipboard unavailable", "Could not copy. Your recent text is still available; try again.")
            return False
        # Copying from the tray must not reset an active recording or decode.
        if self.state == "idle":
            self._flash("clipboard", "Last dictation copied. Click your text field and paste.")
        return True

    def forget_last_dictation(self) -> None:
        self.recent_dictation.clear()
        self._clear_edit_context()
        if self.state == "idle":
            self._idle()

    def _clear_edit_context(self) -> None:
        self.last_text = ""
        self.last_app = ""
        self.last_target = None
        self.last_paste_at = 0.0
        self._edit_receipt = None
        self._last_prefix = ""

    def _schedule_edit_expiry(self) -> None:
        if self._edit_expiry is not None:
            self._edit_expiry.cancel()
        self._edit_generation += 1
        generation = self._edit_generation
        def expire():
            if self._edit_generation == generation:
                self._edit_receipt = None
                self._edit_expiry = None
        timer = threading.Timer(20, expire)
        timer.daemon = True
        self._edit_expiry = timer
        timer.start()

    def _after_job(self, badge: str = "hide", caption: str = "") -> None:
        with self._lock:
            queued = self._queued_audio
            queued_target = self._queued_target
            queued_continuation = self._queued_continuation
            if self._queued_takes:
                self._queued_audio, self._queued_target, self._queued_continuation = self._queued_takes.popleft()
            else:
                self._queued_audio = None
                self._queued_target = None
                self._queued_continuation = None
            if queued is None:
                self._job_running = False
            still_recording = self.state == "recording"
            pending_tail = self._tail_timer is not None
        if queued is not None:
            threading.Thread(
                target=self._finish,
                args=(queued, queued_target, queued_continuation),
                daemon=True,
            ).start()
            return
        if still_recording or pending_tail:
            return
        self._flash(badge, caption)

    def _hide_after(self, seconds: float) -> None:
        """Daemon timer: a pending pill must never hold up quit()."""

        generation = self._indicator_generation

        def hide() -> None:
            if self.state == "idle" and generation == self._indicator_generation:
                self.indicator.set("hide")

        timer = threading.Timer(seconds, hide)
        timer.daemon = True
        timer.start()

    def _show_error(
        self,
        badge: str,
        status: str,
        caption: str,
        seconds: float | None = 4.0,
    ) -> None:
        """Put a failure on screen instead of leaving the user guessing."""
        self._set_icon("idle", status, badge=badge, caption=caption)
        if seconds is not None:
            self._hide_after(seconds)

    def _flash(self, badge: str, caption: str = "") -> None:
        with self._lock:
            if self.state != "recording":
                self.state = "idle"
        linger = LINGER.get(badge)
        if linger is not None:
            self._set_icon("idle", status_hint(self.cfg), badge=badge, caption=caption)
            self._hide_after(linger)
            return
        self._idle()

    def _idle(self) -> None:
        with self._lock:
            self.state = "idle"
        if self._status == LOADING:
            self._set_icon("idle", LOADING, badge="loading")
            return
        if self._status == ENGINE_FAILED:
            self._set_icon("idle", ENGINE_FAILED, badge="engine")
            return
        self._set_icon("idle", status_hint(self.cfg), badge="hide")

    def _set_icon(
        self,
        color: str,
        status: str | None = None,
        badge: str | None = None,
        caption: str = "",
    ) -> None:
        if status is not None:
            self._status = status
        if color == "idle" and self._status == LOADING:
            color = "busy"
        if badge in {"no_mic", "engine", "transcribe", "no_paste"}:
            color = "error"
        if self.icon is not None:
            self.icon.icon = leaf_image(color)
            self.icon.title = tray_title(self._status)
        if badge is not None:
            self._indicator_generation += 1
            self.indicator.set(badge, caption)

    def quit(self) -> None:
        self._stop.set()
        self.recent_dictation.clear()
        self._cancel_limit_timer()
        if self._edit_expiry is not None:
            self._edit_expiry.cancel()
        self._edit_receipt = None
        if self.hotkey is not None:
            self.hotkey.stop()
        if self.state == "recording":
            self.recorder.stop()
        self.recorder.close()
        ipc.clear()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
        self.indicator.close()
        if self.icon is not None:
            self.icon.stop()

    def _handle_ipc(self, command: str) -> str:
        command = command.strip().lower()
        # Recording commands can block for seconds inside PortAudio probing
        # (broken or device-less audio stacks). Reply first and run the side
        # effects in a thread, or the client's timeout turns a live instance
        # into a false "Utterleaf is not running."
        if command == "toggle":
            if self.hotkey is None:
                return "error"
            threading.Thread(target=self.hotkey.toggle, daemon=True).start()
            return "ok"
        if command == "start":
            threading.Thread(target=self.start_recording, daemon=True).start()
            return "ok"
        if command == "stop":
            threading.Thread(target=self.stop_recording, daemon=True).start()
            return "ok"
        if command == "cancel":
            threading.Thread(target=self.cancel_recording, daemon=True).start()
            return "ok"
        if command == "quit":
            threading.Thread(target=self.quit, daemon=True).start()
            return "ok"
        if command == "ping":
            return "ok"
        if command == "copy-last":
            return "ok" if self.copy_last_dictation() else "error"
        if command == "forget-last":
            self.forget_last_dictation()
            return "ok"
        if command == "reload":
            threading.Thread(target=self.reload_config, daemon=True).start()
            return "ok"
        return "unknown"

    def reload_config(self) -> None:
        from utterleaf.config import load

        old = self.cfg
        new = load()
        self.cfg = new
        log.info("Reloaded settings")
        if (
            new.hotkey != old.hotkey
            or new.mode != old.mode
            or new.suppress_hotkey != old.suppress_hotkey
        ):
            parse_hotkey(new.hotkey)
            if self.hotkey is not None:
                self.hotkey.stop()
            self.hotkey = HotkeyWatcher(
                new.hotkey,
                mode=new.mode,
                suppress=new.suppress_hotkey,
                on_start=self.start_recording,
                on_stop=self.stop_recording,
                on_cancel=self.cancel_recording,
            )
            self.hotkey.start()
            log.info("Dictation control: %s", status_hint(new))
        if new.microphone != old.microphone:
            with self._capture_lock:
                self.recorder.set_device(new.microphone)
        model_changed = (
            new.model != old.model
            or new.device != old.device
            or new.language != old.language
            or new.compute_type != old.compute_type
        )
        self._sync_indicator()
        if model_changed:
            reset_engine()
            self._set_icon("busy", LOADING, badge="loading")

            def warmup() -> None:
                try:
                    chosen = pick(self.cfg)
                    if self._needs_download(chosen):
                        self.indicator.set("loading", DOWNLOADING)
                    load_model(self.cfg, chosen)
                    log.info("Model ready after settings change")
                    self._set_icon("idle", status_hint(self.cfg), badge="hide")
                except Exception:
                    log.exception("Model failed to reload")
                    self._show_error(
                        "engine",
                        ENGINE_FAILED,
                        "Open Settings → Help & diagnostics to check your device and model.",
                        seconds=None,
                    )

            threading.Thread(target=warmup, daemon=True).start()
        elif self._status == ENGINE_FAILED:
            self._set_icon("idle", ENGINE_FAILED, badge="engine")
        else:
            self._set_icon("idle", status_hint(self.cfg), badge="hide")
        if self.icon is not None:
            self.icon.update_menu()

    def _sync_indicator(self) -> None:
        """Start or stop the pill to match Settings. Init-only flags must follow reload."""
        want = bool(self.cfg.indicator and self.cfg.tray)
        running = bool(self.indicator.enabled)
        if want == running:
            return
        self.indicator.close()
        self.indicator = Indicator(enabled=want)
        self.indicator.start()

    def toggle_indicator(self) -> None:
        """Change only the overlay preference; preserve other saved settings."""
        from dataclasses import replace
        from utterleaf.config import load, save
        try:
            enabled = not self.cfg.indicator
            save(replace(load(), indicator=enabled))
        except Exception:
            log.exception("Could not save the floating indicator preference")
            self._set_icon("error", "Could not save display preference; open Settings")
            return
        with self._capture_lock:
            self.cfg.indicator = enabled
            self._sync_indicator()
            if enabled:
                if self.state == "recording":
                    if self._countdown_timer is not None:
                        self._countdown_timer.cancel()
                    self._update_countdown(self._cut_id)
                elif self.state == "busy":
                    self.indicator.set("transcribing")
            if self.icon is not None:
                self.icon.update_menu()

    def _ipc_loop(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, _addr = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                continue
            conn.settimeout(2.0)
            with conn:
                line = conn.makefile().readline()
                reply = self._handle_ipc(line)
                try:
                    conn.sendall((reply + "\n").encode("utf-8"))
                except OSError:
                    pass

    def run(self, first_run: bool = False) -> None:
        existing = ipc.send("ping")
        if existing == "ok":
            raise SystemExit("Utterleaf is already running. Use: python -m utterleaf --toggle")

        parse_hotkey(self.cfg.hotkey)
        if self.cfg.tray:
            _hide_console()
        self._server = ipc.bind()
        threading.Thread(target=self._ipc_loop, daemon=True).start()

        def warmup() -> None:
            try:
                self.indicator.set("loading")
                chosen = pick(self.cfg)
                log.info("Device: %s via %s (%s)", chosen.kind, chosen.backend, chosen.name)
                if self._needs_download(chosen):
                    self.indicator.set("loading", DOWNLOADING)
                load_model(self.cfg, chosen)
                log.info("Model ready")
                if self.state == "idle":
                    self._set_icon("idle", status_hint(self.cfg), badge="hide")
            except Exception:
                log.exception("Model failed to load")
                self._show_error(
                    "engine",
                    ENGINE_FAILED,
                    "Open Settings → Help & diagnostics to check your device and model.",
                    seconds=None,
                )

        threading.Thread(target=warmup, daemon=True).start()

        self.hotkey = HotkeyWatcher(
            self.cfg.hotkey,
            mode=self.cfg.mode,
            suppress=self.cfg.suppress_hotkey,
            on_start=self.start_recording,
            on_stop=self.stop_recording,
            on_cancel=self.cancel_recording,
        )
        self.hotkey.start()
        log.info("Dictation control: %s", status_hint(self.cfg))

        if not self.cfg.tray:
            try:
                while not self._stop.is_set():
                    time.sleep(0.25)
            except KeyboardInterrupt:
                pass
            self.quit()
            return

        menu = Menu(
            MenuItem(lambda item: f"Utterleaf — {self._status}", None, enabled=False),
            Menu.SEPARATOR,
            # default=True: a left-click on the tray icon opens Settings.
            MenuItem("Settings…", lambda *_: launch_settings(), default=True),
            MenuItem("Copy last dictation (2 min)", lambda *_: self.copy_last_dictation()),
            MenuItem("Forget last dictation", lambda *_: self.forget_last_dictation()),
            Menu.SEPARATOR,
            MenuItem("Floating indicator", lambda *_: self.toggle_indicator(),
                     checked=lambda _: self.cfg.indicator),
            MenuItem("Tools", Menu(
                MenuItem("Open vocabulary file", lambda *_: open_path(dictionary_path())),
                MenuItem("Open diagnostic log", lambda *_: open_path(log_path())),
            )),
            Menu.SEPARATOR,
            MenuItem("Quit", lambda *_: self.quit()),
        )
        color = "busy" if self._status == LOADING else "idle"
        self.indicator.start()
        self.icon = Icon("Utterleaf", leaf_image(color), tray_title(self._status), menu)
        if first_run:
            launch_settings()
        def setup(icon):
            icon.visible = True
            log.info("Tray ready (%s)", tray_backend())

        try:
            self.icon.run(setup=setup)
        except Exception:
            # Backends tear down over D-Bus (pystray's notification hide) and
            # fail on bare sessions with no notification daemon; a quit must
            # never turn into a crash.
            log.exception("Tray loop ended with an error")
        self.quit()


def run_doctor(cfg: Config) -> int:
    for line in doctor_host_lines():
        print(line)
    print(f"tray backend: {tray_backend()}")
    print(f"config:     {config_path()}")
    print(f"dictionary: {dictionary_path()}")
    print(f"log:        {log_path()}")
    print(f"hotkey:     {cfg.hotkey} ({cfg.mode})")
    try:
        parse_hotkey(cfg.hotkey)
        print("hotkey parse: ok")
    except ValueError as exc:
        print(f"hotkey parse: FAIL ({exc})")
        return 1
    print(f"microphone: {cfg.microphone or 'system default'}")
    print("microphones:")
    try:
        for name in list_devices():
            print(f"  {name}")
    except Exception as exc:
        print(f"  FAIL ({exc})")
        return 1
    print(f"model: {cfg.model}")
    for line in status_lines(resolve_name(cfg), ov_model_id(resolve_name(cfg))):
        print(line)
    print("accelerators:")
    accels = probe()
    chosen = pick(cfg, accels)
    for line in describe(accels, chosen):
        print(line)
    print("polish: local (offline)")
    print(f"allow_network: {cfg.allow_network} (only for a missing model fetch)")
    print(f"start at login: {'on' if startup_enabled() else 'off'}")
    return 0


def run_once(text: str, cfg: Config, app_name: str = "") -> str:
    result = polish(
        text,
        app_name=app_name,
        remove_fillers=cfg.remove_fillers,
        fix_corrections=cfg.fix_corrections,
        text_cleanup=cfg.text_cleanup,
    )
    return result.text
