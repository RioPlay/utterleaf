"""Hold-to-talk loop: record, transcribe, polish, paste."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, replace
from logging.handlers import RotatingFileHandler
import os
import socket
import sys
import threading
import time
from typing import Callable
from utterleaf.host import is_wayland, pin_tray_backend

# Linux tray backend must be selected before pystray imports (see host.pin_tray_backend).
pin_tray_backend()
from pystray import Icon, Menu, MenuItem

from utterleaf.beep import beep
from utterleaf import edit_target, ipc
from utterleaf.audio import TAIL_SECONDS, Recorder, list_devices, microphone_error_hint
from utterleaf.capture_store import CaptureStore, CaptureStorageError
from utterleaf.audio_batching import audio_windows
from utterleaf.transcript import TranscriptionCancelled
from utterleaf.config import Config, config_path, dictionary_path, log_path
from utterleaf.hotkey import HotkeyWatcher, parse_hotkey
from utterleaf.indicator import Indicator
from utterleaf.inject import copy_text, foreground_app, foreground_id, paste
from utterleaf.polish import polish, infer_style
from utterleaf.dictation_spacing import prepare_delivery
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
CAPTURE_CHECK_SECONDS = 0.5
ENDPOINT_POLL_SECONDS = 0.25
ENDPOINT_FRESH_SAMPLES = 8000


@dataclass(frozen=True)
class _InterruptedTake:
    """An unsolicited stop may recover text but must never target an editor."""

    reason: str


@dataclass(frozen=True)
class _EndpointTake:
    """An automatic stop with take-start settings and an original target."""

    target: object
    app_name: str
    action: str  # review | insert
    config: Config
    continuation: object = None
    field: object = None
    format_command: str | None = None


@dataclass
class _ReviewState:
    generation: int
    recovery_generation: int
    text: str
    target: object
    app_name: str
    config: Config
    continuation: object = None
    field: object = None
    format_command: str | None = None
    handle: object = None


# How long a result pill stays up. Failures linger longer than successes.
# engine is omitted on purpose: that pill stays until the model loads.
LINGER = {
    "pasted": 2.0,
    "clipboard": 2.0,
    "missed": 1.2,
    "too_short": 1.2,
    "transcribe": 3.5,
    "no_paste": 3.5,
    "uncertain": 8.0,
    "no_mic": 8.0,
    "capture_error": 8.0,
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
        self.recorder = Recorder(device=cfg.microphone, continuous=True)
        self.state: State = "idle"
        self.last_text = ""
        self._recent_generation = 0
        self.recent_dictation = RecentDictation(on_expire=self._expire_recovery_context)
        self.last_app = ""
        self.last_target = None
        self.last_paste_at = 0.0
        self._edit_receipt = None
        self._last_prefix = ""
        self._last_suffix = ""
        self._edit_expiry: threading.Timer | None = None
        self._edit_generation = 0
        self._queued_audio = None
        self._queued_target = None
        self._queued_continuation = None
        self._queued_takes = deque()
        self._take_continuation = None
        self._cancel_job = False
        # Rotate on cancellation; never clear a signal held by an older job.
        self._delivery_cancel = threading.Event()
        self._job_running = False
        self._preview_stop = threading.Event()
        self._cut_id = 0
        self._tail_done_for = -1
        self._tail_timer: threading.Timer | None = None
        self._tail_args = None
        self._limit_timer: threading.Timer | None = None
        self._countdown_timer: threading.Timer | None = None
        self._capture_timer: threading.Timer | None = None
        self._endpoint_timer: threading.Timer | None = None
        self._endpoint = None
        self._endpoint_generation = 0
        self._endpoint_cut_id = -1
        self._endpoint_target = None
        self._endpoint_unavailable = False
        self._endpoint_detector = None
        self._endpoint_detector_loaded = False
        self._endpoint_detector_loading = False
        self._review: _ReviewState | None = None
        self._review_generation = 0
        self._review_lock = threading.RLock()
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
        self._close_review()
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
        take_config = replace(self.cfg)
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
            self.recorder.start(max_seconds=None)
            start_field = edit_target.read_field() if take_config.speech_end_enabled else None
            self._recording_deadline = 0.0
            self._recording_draft = ""
            log.info("Recording")
            self._set_icon("recording", "listening", badge="listening",
                           caption=self._recording_caption())
            beep("start", self.cfg.beep)
            self._schedule_capture_check(self._cut_id)
            self._start_speech_endpoint(self._cut_id, start_target, start_app,
                                        continuation, take_config, start_field)
            if self.cfg.live_preview and self.indicator.enabled:
                self._preview_stop.clear()
                threading.Thread(target=self._preview_loop, args=(self._cut_id,), daemon=True).start()
        except Exception as exc:
            log.exception("Microphone failed")
            self._cancel_limit_timer()
            try:
                self.recorder.close()
            except Exception:
                log.warning("Could not release failed capture", exc_info=True)
            if self.hotkey is not None:
                self.hotkey.reset_active()
            beep("err", self.cfg.beep)
            with self._lock:
                self.state = "idle"
            if isinstance(exc, CaptureStorageError):
                self._show_error("transcribe", "audio storage unavailable", str(exc))
            else:
                self._show_error("no_mic", NO_MIC, microphone_error_hint(exc))

    def _ensure_endpoint_detector(self) -> None:
        if (not self.cfg.speech_end_enabled or self._endpoint_detector_loaded
                or self._endpoint_detector_loading or self._stop.is_set()):
            return
        self._endpoint_detector_loading = True

        def load() -> None:
            try:
                from utterleaf.speech_endpoint import local_silero_detector

                detector = local_silero_detector()
            except Exception:
                log.warning("Local speech-end detector unavailable", exc_info=True)
                detector = None
            with self._capture_lock:
                self._endpoint_detector = detector
                self._endpoint_detector_loaded = True
                self._endpoint_detector_loading = False

        try:
            worker = threading.Thread(target=load, daemon=True,
                                      name="utterleaf-speech-end-load")
            worker.start()
        except Exception:
            log.warning("Could not start local speech-end detector loader", exc_info=True)
            self._endpoint_detector_loading = False

    def _start_speech_endpoint(self, cut_id: int, target, app_name: str,
                               continuation, take_config: Config, target_field=None) -> None:
        self._cancel_speech_endpoint()
        self._endpoint_unavailable = False
        if not take_config.speech_end_enabled:
            return
        if not self._endpoint_detector_loaded:
            self._ensure_endpoint_detector()
        detector = self._endpoint_detector
        snapshot = getattr(self.recorder, "endpoint_snapshot", None)
        if detector is None or not callable(snapshot):
            self._mark_endpoint_unavailable()
            return
        from utterleaf.speech_endpoint import EndpointOptions, SpeechEndpoint

        take = _EndpointTake(
            target,
            app_name,
            "insert" if take_config.speech_end_insert and target_field is not None else "review",
            take_config,
            continuation,
            target_field,
        )
        generation_box = [0]
        try:
            options = EndpointOptions(take_config.speech_end_pause_seconds)
        except (TypeError, ValueError):
            self._mark_endpoint_unavailable()
            return
        endpoint = None
        try:
            endpoint = SpeechEndpoint(
                detector,
                lambda end_sample: self._speech_endpoint_end(
                    endpoint, generation_box[0], cut_id, end_sample, take),
                options=options,
                on_error=lambda: self._speech_endpoint_error(
                    endpoint, generation_box[0], cut_id, take.target),
            )
            generation = endpoint.start()
        except Exception:
            log.warning("Speech-end detection could not start for this take", exc_info=True)
            if endpoint is not None:
                endpoint.cancel()
            self._mark_endpoint_unavailable()
            return
        generation_box[0] = generation
        self._endpoint = endpoint
        self._endpoint_generation = generation
        self._endpoint_cut_id = cut_id
        self._endpoint_target = target
        self._schedule_endpoint_poll(endpoint, generation, cut_id)

    def _recording_caption(self, draft: str = "") -> str:
        stop_hint = "Press shortcut to finish" if self.cfg.mode == "toggle" or is_wayland() else "Release shortcut to finish"
        caption = stop_hint if is_wayland() else f"{stop_hint} · Esc cancels"
        if draft:
            caption += f" · {draft}"
        if self._endpoint_unavailable:
            caption += " · Automatic stop unavailable; stop manually"
        return caption

    def _mark_endpoint_unavailable(self) -> None:
        self._endpoint_unavailable = True
        caption = self._recording_caption(self._recording_draft)
        self._set_icon(
            "recording",
            "listening — automatic stop unavailable; stop manually",
            badge="listening",
            caption=caption,
        )

    def _schedule_endpoint_poll(self, endpoint, generation: int, cut_id: int) -> None:
        if self._stop.is_set() or endpoint is not self._endpoint or not endpoint.active:
            return
        timer = threading.Timer(ENDPOINT_POLL_SECONDS, self._poll_speech_endpoint,
                                args=(endpoint, generation, cut_id))
        timer.daemon = True
        self._endpoint_timer = timer
        timer.start()

    def _poll_speech_endpoint(self, endpoint, generation: int, cut_id: int) -> None:
        with self._capture_lock:
            if (self.state != "recording" or cut_id != self._cut_id
                    or endpoint is not self._endpoint or generation != self._endpoint_generation
                    or self._stop.is_set()):
                return
            self._endpoint_timer = None
            if foreground_id() != self._endpoint_target:
                self._cancel_speech_endpoint()
                self._mark_endpoint_unavailable()
                return
            try:
                audio, end_sample = self.recorder.endpoint_snapshot()
                endpoint.submit(audio, generation, end_sample=end_sample)
            except Exception:
                log.warning("Speech-end detection unavailable for this take", exc_info=True)
                self._cancel_speech_endpoint()
                self._mark_endpoint_unavailable()
                return
            self._schedule_endpoint_poll(endpoint, generation, cut_id)

    def _speech_endpoint_error(self, endpoint, generation: int, cut_id: int,
                               target) -> None:
        with self._capture_lock:
            if (endpoint is not self._endpoint or generation != self._endpoint_generation
                    or cut_id != self._cut_id or self.state != "recording"):
                return
            self._cancel_speech_endpoint()
            self._mark_endpoint_unavailable()

    def _speech_endpoint_end(self, endpoint, generation: int, cut_id: int,
                             analyzed_end: int, take: _EndpointTake) -> None:
        with self._capture_lock:
            if (endpoint is not self._endpoint or generation != self._endpoint_generation
                    or cut_id != self._cut_id or self.state != "recording"
                    or self._stop.is_set()):
                return
            if foreground_id() != take.target:
                self._cancel_speech_endpoint()
                self._mark_endpoint_unavailable()
                return
            try:
                _, current_end = self.recorder.endpoint_snapshot()
            except Exception:
                current_end = analyzed_end + ENDPOINT_FRESH_SAMPLES + 1
            if current_end - analyzed_end > ENDPOINT_FRESH_SAMPLES:
                self._cancel_speech_endpoint()
                self._mark_endpoint_unavailable()
                return
            self._stop_recording(endpoint_take=take)

    def _cancel_speech_endpoint(self) -> None:
        timer, self._endpoint_timer = self._endpoint_timer, None
        if timer is not None:
            timer.cancel()
        endpoint, self._endpoint = self._endpoint, None
        self._endpoint_generation = 0
        self._endpoint_cut_id = -1
        self._endpoint_target = None
        if endpoint is not None:
            endpoint.cancel()

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
                    self.indicator.set("listening", self._recording_caption(draft))

    def _update_countdown(self, cut_id: int) -> None:
        with self._capture_lock:
            if self.state != "recording" or cut_id != self._cut_id or self._stop.is_set():
                return
            self.indicator.set("listening", self._recording_caption(self._recording_draft))

    def _recording_limit(self, cut_id: int) -> None:
        self.stop_recording(limit_cut_id=cut_id)

    def _schedule_capture_check(self, cut_id: int) -> None:
        # Alternate recorder adapters may omit liveness reporting. Recorder
        # implements it; do not start a monitor that cannot check its adapter.
        if self._stop.is_set() or not callable(getattr(self.recorder, "capture_error", None)):
            return
        timer = threading.Timer(CAPTURE_CHECK_SECONDS, self._check_capture, args=(cut_id,))
        timer.daemon = True
        self._capture_timer = timer
        timer.start()

    def _check_capture(self, cut_id: int) -> None:
        with self._capture_lock:
            if self.state != "recording" or cut_id != self._cut_id or self._stop.is_set():
                return
            self._capture_timer = None
            reason = self.recorder.capture_error()
            if reason:
                log.warning("Microphone capture interrupted")
                self._stop_recording(limit_cut_id=cut_id, interruption=reason)
            else:
                self._schedule_capture_check(cut_id)

    def _cancel_limit_timer(self) -> None:
        capture, self._capture_timer = self._capture_timer, None
        if capture is not None:
            capture.cancel()
        countdown, self._countdown_timer = self._countdown_timer, None
        if countdown is not None:
            countdown.cancel()
        timer, self._limit_timer = self._limit_timer, None
        if timer is not None:
            timer.cancel()

    def stop_recording(self, *, limit_cut_id: int | None = None) -> None:
        with self._capture_lock:
            self._stop_recording(limit_cut_id=limit_cut_id)

    def _stop_recording(self, *, limit_cut_id: int | None = None,
                        interruption: str | None = None,
                        endpoint_take: _EndpointTake | None = None) -> None:
        with self._lock:
            if self.state != "recording" or (limit_cut_id is not None and limit_cut_id != self._cut_id):
                return
            follow_on = self._job_running
            if not follow_on:
                self._job_running = True
            self.state = "busy"
        if interruption is None:
            check = getattr(self.recorder, "capture_error", None)
            if callable(check):
                interruption = check()
        self._cancel_speech_endpoint()
        self._preview_stop.set()
        self._cancel_limit_timer()
        if (limit_cut_id is not None or interruption or endpoint_take is not None) and self.hotkey is not None:
            self.hotkey.reset_active()
        request_final()
        caption = "Recording limit reached. Start another take to continue." if limit_cut_id is not None else ""
        if interruption:
            caption = f"{interruption} Recovering captured speech."
        self._set_icon("busy", "recovering interrupted dictation" if interruption else "transcribing",
                       badge="transcribing", caption=caption)
        beep("stop", self.cfg.beep)
        cut_id = self._cut_id
        continuation = self._take_continuation
        if interruption:
            # No trailing capture or automatic field delivery after device loss.
            self._cut(_InterruptedTake(interruption), follow_on, cut_id)
            return
        if endpoint_take is not None:
            # The detector has already observed the requested quiet interval.
            # Release capture immediately; no trailing microphone tail is needed.
            self._cut(endpoint_take, follow_on, cut_id, endpoint_take.continuation)
            return
        target = foreground_id()
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
        if not isinstance(target, _InterruptedTake):
            # Release-time health is not enough: the stream can fail during
            # the trailing capture after the periodic monitor has stopped.
            check = getattr(self.recorder, "capture_error", None)
            reason = check() if callable(check) else None
            if reason:
                log.warning("Microphone capture interrupted during recording tail")
                target = _InterruptedTake(reason)
                continuation = None
        audio = self.recorder.stop()
        try:
            self.recorder.close()
        except Exception:
            # A disconnected device must not discard audio already captured.
            log.warning("Microphone release failed", exc_info=True)
        seconds = self.recorder.seconds(audio)
        if seconds < self.cfg.min_seconds:
            if isinstance(audio, CaptureStore):
                audio.close()
            log.info("Ignored short tap (%.2fs)", seconds)
            with self._lock:
                if follow_on and self._job_running:
                    return
                self._cancel_job = False
                self._job_running = False
            clear_final()
            if isinstance(target, _InterruptedTake):
                self._flash("capture_error", f"{target.reason} Too little audio to recover.")
            else:
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
        with self._lock:
            self._delivery_cancel.set()
            self._delivery_cancel = threading.Event()
            cut_id = self._cut_id
            if self._job_running or self.state == "busy":
                self._cancel_job = True
            self._discard_queued_stores()
            self._queued_audio = None
            self._queued_target = None
            self._queued_continuation = None
            self._queued_takes.clear()
        with self._capture_lock:
            # A delayed cancel must not stop a newer deliberate recording.
            if cut_id == self._cut_id:
                self._cancel_recording()

    def _delivery_guard(self) -> Callable[[], bool]:
        with self._lock:
            event = self._delivery_cancel
        return lambda: event.is_set() or self._cancel_job or self._stop.is_set()

    def _discard_queued_stores(self) -> None:
        if isinstance(self._queued_audio, CaptureStore):
            self._queued_audio.close()
        for audio, _, _ in self._queued_takes:
            if isinstance(audio, CaptureStore):
                audio.close()

    def _cancel_recording(self) -> None:
        self._cancel_speech_endpoint()
        self._cancel_limit_timer()
        self._preview_stop.set()
        clear_final()
        with self._lock:
            self._discard_queued_stores()
            self._queued_audio = None
            self._queued_target = None
            self._queued_continuation = None
            self._queued_takes.clear()
            if self.state == "recording":
                self.state = "idle"
                discarded = self.recorder.stop()
                if isinstance(discarded, CaptureStore):
                    discarded.close()
                self.recorder.close()
                log.info("Cancelled")
                self._set_icon("idle", badge="hide")
                beep("err", self.cfg.beep)
                return
            if self.state == "busy":
                # Public cancel already signaled the job before waiting for
                # capture ownership. Re-arming here can cancel the next job.
                log.info("Will skip this paste")
                return
        # Idle Esc is left to the focused app (close pickers, leave fullscreen).

    def _finish(self, audio, target=None, continuation=None) -> None:
        cancelled = self._delivery_guard()
        try:
            endpoint_take = target if isinstance(target, _EndpointTake) else None
            if endpoint_take is not None:
                target = endpoint_take.target
                continuation = endpoint_take.continuation
            take_config = endpoint_take.config if endpoint_take is not None else self.cfg
            if cancelled():
                self._cancel_job = False
                log.info("Paste skipped")
                self._after_job()
                return
            if isinstance(audio, CaptureStore):
                audio.wait_ready(cancelled)
                if audio.error:
                    target = _InterruptedTake(audio.error)
                    endpoint_take = None
                    continuation = None
            app_name = (endpoint_take.app_name if endpoint_take is not None else
                        "" if isinstance(target, _InterruptedTake) else foreground_app())
            decode_started = time.perf_counter()
            if isinstance(audio, CaptureStore):
                parts = []
                for chunk in audio_windows(audio.chunks(cancelled), cancel=cancelled):
                    if cancelled():
                        raise TranscriptionCancelled("Recording cancelled")
                    parts.append(transcribe(chunk, take_config).strip())
                    if cancelled():
                        raise TranscriptionCancelled("Recording cancelled")
                raw = " ".join(part for part in parts if part)
            else:
                raw = transcribe(audio, take_config)
            log.info("Dictation timing: audio=%.2fs decode=%.3fs",
                     len(audio) / 16000, time.perf_counter() - decode_started)
            # Esc may arrive during a long decode. Check again before editing
            # or pasting into the user's app, not just before transcription.
            if cancelled():
                self._cancel_job = False
                self._after_job()
                return
            log.debug("Transcription received (%d characters)", len(raw))
            if isinstance(target, _InterruptedTake):
                # A partial take can contain a spoken edit command. Recover the
                # model output literally, without editing or reading any field.
                # Cancel takes this same lock. It must not win between the
                # earlier post-decode check and retaining the recovered result.
                with self._capture_lock:
                    if cancelled():
                        self._cancel_job = False
                        self._after_job()
                        return
                    text = raw.strip()
                    if text:
                        self._remember_result(text)
                        hint = "Captured speech is ready. Use Copy last dictation in the tray within two minutes."
                    else:
                        hint = "No speech was recovered from this take."
                    self._after_job("capture_error", f"{target.reason} {hint}")
                return
            if not raw:
                self._after_job("missed")
                return
            if endpoint_take is not None:
                # Automatic stops never execute spoken editor commands. The
                # formatting pass is pure; editor-action commands remain literal.
                formatted = polish(
                    raw,
                    app_name=endpoint_take.app_name,
                    remove_fillers=take_config.remove_fillers,
                    fix_corrections=take_config.fix_corrections,
                    text_cleanup=take_config.text_cleanup,
                    output_format=take_config.output_format,
                )
                text = (raw.strip() if formatted.command in {
                    "discard", "replace", "shorter", "professional"
                } else formatted.text)
                safe_command = (formatted.command if formatted.command in {
                    "heading", "bullets", "numbered", "newline", "paragraph"
                } else None)
                endpoint_take = replace(endpoint_take, format_command=safe_command)
                if not text:
                    self._after_job("missed")
                    return
                if endpoint_take.action == "review":
                    with self._capture_lock:
                        if cancelled():
                            self._after_job()
                            return
                        self._remember_result(text)
                        # An older queued decode must not raise a window over a
                        # newer take that the user deliberately started.
                        shown = self.state != "recording" and self._present_review(text, endpoint_take)
                    self._after_job("hide" if shown else "no_paste",
                                    "Review could not open. Use Copy last dictation in the tray within two minutes."
                                    if not shown else "")
                    return
                with self._capture_lock:
                    self._deliver_endpoint_text(text, endpoint_take,
                                                fallback_review=True, cancelled=cancelled)
                return
            format_started = time.perf_counter()
            result = polish(
                raw,
                app_name=app_name,
                remove_fillers=self.cfg.remove_fillers,
                fix_corrections=self.cfg.fix_corrections,
                text_cleanup=self.cfg.text_cleanup,
                output_format=self.cfg.output_format,
            )
            log.info("Dictation timing: formatting=%.3fs", time.perf_counter() - format_started)
            # Formatting/vocabulary work can outlast an Esc or shutdown request.
            # The post-decode check alone does not cover this stage.
            if cancelled():
                self._cancel_job = False
                self._after_job()
                return
            if result.command == "replace":
                replacement = prepare_delivery(result.text, text_cleanup=self.cfg.text_cleanup,
                                               code_mode=infer_style(app_name) == "code",
                                               markdown=self.cfg.output_format == "markdown")
                self._remember_result(replacement.text)
                if (not self.last_text or not self.last_target or target != self.last_target
                        or foreground_id() != self.last_target
                        or (time.time() - self.last_paste_at) >= self.recent_dictation.ttl):
                    self._after_job("no_paste", "Replacement ready. Select the old entry, then use Copy last dictation and paste.")
                    return
                if cancelled():
                    self._cancel_job = False
                    self._after_job()
                    return
                outcome, receipt = edit_target.replace(
                    self._edit_receipt, self._last_prefix + replacement.payload)
                if cancelled():
                    self._delivery_interrupted("uncertain")
                    return
                self._edit_receipt = receipt
                if outcome != "replaced":
                    message = ("Replacement ready. Select the old entry, then use Copy last dictation and paste."
                               if outcome == "unavailable" else
                               "Could not verify the replacement. Check the field; Copy last dictation still has your correction.")
                    self._after_job("no_paste", message)
                    return
                self.last_text = replacement.text
                self._last_suffix = replacement.suffix
                self.last_app = app_name
                self.last_target = target
                self.last_paste_at = time.time()
                self._schedule_edit_expiry()
                beep("ok", self.cfg.beep)
                self._after_job("pasted", replacement.payload)
                return
            if result.command_only and self.last_text and (
                not self.last_target
                or target != self.last_target
                or foreground_id() != self.last_target
                or (time.time() - self.last_paste_at) >= self.recent_dictation.ttl
            ):
                self._after_job("no_paste", "Return to your last dictation to use an edit command.")
                return
            if result.discarded:
                if result.command_only and self.last_text:
                    if cancelled():
                        self._cancel_job = False
                        self._after_job()
                        return
                    outcome, receipt = edit_target.replace(self._edit_receipt, None)
                    if cancelled():
                        self._delivery_interrupted("uncertain")
                        return
                    self._edit_receipt = receipt
                    if outcome != "replaced":
                        self._after_job("no_paste", "Select your last dictation and delete it manually. This field could not be verified.")
                        return
                    self.last_text = ""
                    self.last_app = ""
                    self.last_target = None
                    self.last_paste_at = 0.0
                    self._last_prefix = ""
                    self._last_suffix = ""
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
                    revision = prepare_delivery(text, text_cleanup=self.cfg.text_cleanup,
                                                code_mode=infer_style(app_name) == "code",
                                                markdown=self.cfg.output_format == "markdown")
                    self._remember_result(revision.text)
                    if cancelled():
                        self._cancel_job = False
                        self._after_job()
                        return
                    outcome, receipt = edit_target.replace(self._edit_receipt, self._last_prefix + revision.payload)
                    if cancelled():
                        self._delivery_interrupted("uncertain")
                        return
                    self._edit_receipt = receipt
                    if outcome != "replaced":
                        beep("err", self.cfg.beep)
                        if outcome == "unavailable" and copy_text(text):
                            self._after_job("clipboard", "Revised text copied. Select the old dictation and paste to replace it.")
                        else:
                            self._after_job("no_paste", "Could not verify the edit. Check your text before trying again.")
                        return
                    self.last_text = text
                    self._last_suffix = revision.suffix
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
            previous = self.last_text + self._last_suffix if same_place else ""
            delivery_started = time.perf_counter()
            before = edit_target.read_field()
            neighbors = edit_target.insertion_neighbors(before)
            delivery = prepare_delivery(text, previous_delivered=previous,
                                        text_cleanup=self.cfg.text_cleanup,
                                        code_mode=infer_style(app_name) == "code", command=result.command,
                                        neighbors=neighbors, markdown=self.cfg.output_format == "markdown")
            to_paste = delivery.payload
            if cancelled():
                self._cancel_job = False
                self._after_job()
                return
            self._remember_result(delivery.prefix + delivery.text)
            outcome = paste(
                to_paste,
                restore_clipboard=self.cfg.restore_clipboard,
                target=target,
                cancel=cancelled,
            )
            log.info("Dictation timing: delivery=%.3fs outcome=%s",
                     time.perf_counter() - delivery_started, outcome)
            if self._delivery_interrupted(outcome):
                return
            if outcome == "pasted":
                self._edit_receipt = edit_target.capture(before, to_paste)
                self._last_prefix = delivery.prefix
                self._last_suffix = delivery.suffix
                self.last_text = delivery.text
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
        except TranscriptionCancelled:
            self._after_job()
            return
        except Exception:
            log.exception("Transcription failed")
            beep("err", self.cfg.beep)
            self._after_job("transcribe", "Try another take. If this repeats, open Settings → Help & diagnostics.")
            return
        finally:
            if isinstance(audio, CaptureStore):
                audio.close()

    def _deliver_endpoint_text(self, text: str, take: _EndpointTake, *,
                               fallback_review: bool = False,
                               cancelled: Callable[[], bool] | None = None) -> None:
        """Insert literal endpoint text through the ordinary target guards."""
        cancelled = cancelled or self._delivery_guard()
        if cancelled():
            self._after_job()
            return
        same_place = bool(
            self.last_text
            and take.target == self.last_target
            and take.app_name == self.last_app
            and (take.continuation is not None or time.time() - self.last_paste_at < 20)
        )
        previous = self.last_text + self._last_suffix if same_place else ""
        current_target = foreground_id()
        if cancelled():
            self._after_job()
            return
        if current_target != take.target:
            self._endpoint_delivery_failed(text, take, fallback_review,
                                           "The original window changed. Use Copy to place the text safely.")
            return
        before = edit_target.read_field()
        if cancelled():
            self._after_job()
            return
        if take.field is None or before != take.field:
            self._endpoint_delivery_failed(text, take, fallback_review,
                                           "The original field or caret changed. Use Copy to place the text safely.")
            return
        neighbors = edit_target.insertion_neighbors(before)
        delivery = prepare_delivery(text, previous_delivered=previous,
                                    text_cleanup=take.config.text_cleanup,
                                    code_mode=infer_style(take.app_name) == "code",
                                    command=take.format_command,
                                    neighbors=neighbors,
                                    markdown=take.config.output_format == "markdown")
        to_paste = delivery.payload
        self._remember_result(delivery.prefix + delivery.text)
        if cancelled():
            self._after_job()
            return
        outcome = paste(to_paste, restore_clipboard=take.config.restore_clipboard,
                        target=take.target, cancel=cancelled)
        if self._delivery_interrupted(outcome):
            return
        if outcome == "pasted":
            self._edit_receipt = edit_target.capture(before, to_paste)
            self._last_prefix = delivery.prefix
            self._last_suffix = delivery.suffix
            self.last_text = delivery.text
            self.last_app = take.app_name
            self.last_target = take.target
            self.last_paste_at = time.time()
            self._schedule_edit_expiry()
            beep("ok", take.config.beep)
            self._after_job("pasted", to_paste)
        elif outcome == "clipboard":
            beep("err", take.config.beep)
            self._after_job("clipboard", to_paste)
        else:
            beep("err", take.config.beep)
            self._after_job("no_paste", "Use Copy last dictation in the tray menu to recover your text.")

    def _delivery_interrupted(self, outcome: str) -> bool:
        if self._stop.is_set() or outcome == "cancelled":
            self._cancel_job = False
            self._after_job()
            return True
        if outcome == "uncertain":
            self._cancel_job = False
            self._clear_edit_context()
            self._after_job("uncertain", "Delivery could not be confirmed. Check the field before using Copy last dictation; text may already be inserted.")
            return True
        return False

    def _endpoint_delivery_failed(self, text: str, take: _EndpointTake,
                                  fallback_review: bool, message: str) -> None:
        if fallback_review and self.state == "busy" and not self._stop.is_set() and not self._cancel_job:
            self._remember_result(text)
            shown = self._present_review(text, replace(take, action="review"))
            self._after_job("hide" if shown else "no_paste",
                            message if not shown else "")
            return
        self._after_job("no_paste", message)

    def _remember_result(self, text: str) -> None:
        with self._review_lock:
            if self._stop.is_set():
                return
            state, self._review = self._review, None
            self._review_generation += 1
            self._recent_generation = self.recent_dictation.put(text)
        if state is not None and state.handle is not None:
            state.handle.close()

    def _present_review(self, text: str, take: _EndpointTake) -> bool:
        from utterleaf.review_ui import launch_review

        self._close_review()
        with self._review_lock:
            if self._stop.is_set():
                return False
            self._review_generation += 1
            generation = self._review_generation
            state = _ReviewState(generation, self._recent_generation, text, take.target,
                                 take.app_name, take.config, take.continuation, take.field,
                                 take.format_command)
            self._review = state
            handle = launch_review(
                text,
                lambda action: self._review_action(generation, action),
                lambda: self._review_failed(generation),
                allow_insert=take.field is not None,
            )
            if handle is None:
                self._review = None
                return False
            if self._review is state:
                state.handle = handle
            return True

    def _close_review(self) -> None:
        with self._review_lock:
            state, self._review = self._review, None
            self._review_generation += 1
        if state is not None and state.handle is not None:
            state.handle.close()

    def _review_action(self, generation: int, action: str) -> None:
        cancelled = self._delivery_guard()
        if action not in {"copy", "insert", "discard", "dismiss"}:
            return
        with self._review_lock:
            state = self._review
            if state is None or state.generation != generation:
                return
            self._review = None
        if (self._recent_generation != state.recovery_generation
                or self.recent_dictation.get() != state.text):
            return
        if action == "dismiss":
            return
        if action == "discard":
            if self._recent_generation == state.recovery_generation:
                self.recent_dictation.clear()
            if self.state == "idle":
                self._idle()
            return
        if action == "copy":
            if copy_text(state.text):
                if self.state == "idle":
                    self._flash("clipboard", "Reviewed dictation copied. Return to your field and paste.")
            else:
                self._show_error("no_paste", "copy unconfirmed",
                                 "Copy could not be confirmed. Your reviewed text remains available in Copy last dictation.")
            return
        take = _EndpointTake(state.target, state.app_name, "insert", state.config,
                             state.continuation, state.field, state.format_command)
        with self._capture_lock:
            if self.state != "idle" or cancelled():
                return
            # The child closes after reporting the choice. Give the OS a short,
            # bounded interval to restore focus, then require the exact native
            # field contents and selection captured when recording began.
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                if cancelled():
                    return
                if foreground_id() == take.target and edit_target.read_field() == take.field:
                    break
                time.sleep(0.05)
            self._deliver_endpoint_text(state.text, take, cancelled=cancelled)

    def _review_failed(self, generation: int) -> None:
        with self._review_lock:
            if self._review is None or self._review.generation != generation:
                return
            self._review = None
        if self.state == "idle":
            self._flash("no_paste", "Review could not open. Use Copy last dictation in the tray within two minutes.")

    def _expire_recovery_context(self, generation: int) -> None:
        state = None
        with self._review_lock:
            if self._recent_generation != generation:
                return
            if self._review is not None and self._review.recovery_generation == generation:
                state, self._review = self._review, None
                self._review_generation += 1
            self._clear_edit_context()
        if state is not None and state.handle is not None:
            state.handle.close()

    def copy_last_dictation(self) -> bool:
        text = self.recent_dictation.get()
        if not text:
            self._show_error("no_paste", "nothing to recover", "No recent dictation. Recovery text expires after two minutes.")
            return False
        if not copy_text(text):
            self._show_error("no_paste", "copy unconfirmed", "Copy could not be confirmed. Your recent text is still available in Copy last dictation.")
            return False
        # Copying from the tray must not reset an active recording or decode.
        if self.state == "idle":
            self._flash("clipboard", "Last dictation copied. Click your text field and paste.")
        return True

    def forget_last_dictation(self) -> None:
        self._close_review()
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
        self._last_suffix = ""

    def _schedule_edit_expiry(self) -> None:
        if self._edit_expiry is not None:
            self._edit_expiry.cancel()
        self._edit_generation += 1
        generation = self._edit_generation
        def expire():
            if self._edit_generation == generation:
                self._edit_receipt = None
                self._edit_expiry = None
        timer = threading.Timer(self.recent_dictation.ttl, expire)
        timer.daemon = True
        self._edit_expiry = timer
        timer.start()

    def _after_job(self, badge: str = "hide", caption: str = "") -> None:
        with self._lock:
            if self._cancel_job:
                self._cancel_job = False
            if self._stop.is_set():
                self._discard_queued_stores()
                self._queued_audio = None
                self._queued_target = None
                self._queued_continuation = None
                self._queued_takes.clear()
                self._job_running = False
                return
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
            status = {
                "no_mic": "microphone interrupted — check microphone and recovery",
                "capture_error": "recording interrupted — check the capture error and recovery",
                "uncertain": "delivery unconfirmed — check the field before retrying",
            }.get(badge, status_hint(self.cfg))
            self._set_icon("idle", status, badge="no_paste" if badge == "uncertain" else badge, caption=caption)
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
        if badge in {"no_mic", "capture_error", "engine", "transcribe", "no_paste"}:
            color = "error"
        if self.icon is not None:
            self.icon.icon = leaf_image(color)
            self.icon.title = tray_title(self._status)
        if badge is not None:
            self._indicator_generation += 1
            self.indicator.set(badge, caption)

    def quit(self) -> None:
        self._stop.set()
        self._cancel_speech_endpoint()
        with self._review_lock:
            self._close_review()
            self.recent_dictation.clear()
            self._clear_edit_context()
        self._cancel_limit_timer()
        if self._edit_expiry is not None:
            self._edit_expiry.cancel()
        self._edit_receipt = None
        if self.hotkey is not None:
            self.hotkey.stop()
        if self.state == "recording":
            discarded = self.recorder.stop()
            if isinstance(discarded, CaptureStore):
                discarded.close()
        self.recorder.close()
        with self._lock:
            self._discard_queued_stores()
            self._queued_audio = None
            self._queued_takes.clear()
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
                self._cancel_speech_endpoint()
                if self.state == "recording":
                    self._endpoint_unavailable = True
                self.recorder.set_device(new.microphone)
        if new.speech_end_enabled:
            self._ensure_endpoint_detector()
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
                try:
                    with conn.makefile("rb") as reader:
                        line = reader.readline(1025)
                    command = ipc.authenticated_command(line)
                    reply = self._handle_ipc(command) if command is not None else "unauthorized"
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
        self._ensure_endpoint_detector()

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
                MenuItem("Transcribe a file…", lambda *_: self._launch_files()),
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

    @staticmethod
    def _launch_files() -> None:
        from utterleaf.file_ui import launch_files

        launch_files()


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
