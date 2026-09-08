"""Hold-to-talk loop: record, transcribe, polish, paste."""

from __future__ import annotations

import logging
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
from utterleaf import ipc
from utterleaf.audio import TAIL_SECONDS, Recorder, list_devices
from utterleaf.config import Config, config_path, dictionary_path, log_path
from utterleaf.hotkey import HotkeyWatcher, parse_hotkey
from utterleaf.indicator import Indicator
from utterleaf.inject import foreground_app, foreground_id, paste, undo_last
from utterleaf.polish import polish, stitch_to_previous
from utterleaf.hardware import describe, ov_model_id, pick, probe
from utterleaf.models import ct2_dir, ct2_ready, ov_dir, ov_ready, status_lines
from utterleaf.host import doctor_host_lines, login_label
from utterleaf.settings import launch_settings
from utterleaf.theme import mic_image
from utterleaf.startup import enabled as startup_enabled, set_enabled as set_startup
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
ENGINE_FAILED = "engine not ready — see log"
NO_MIC = "microphone unavailable"
DOWNLOADING = "Downloading the speech model (~500 MB)…"

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
        self.last_app = ""
        self.last_target = None
        self.last_paste_at = 0.0
        self._queued_audio = None
        self._queued_target = None
        self._queued_continuation = None
        self._take_continuation = None
        self._cancel_job = False
        self._job_running = False
        self._preview_stop = threading.Event()
        self._cut_id = 0
        self._tail_done_for = -1
        self._tail_timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.icon: Icon | None = None
        self.hotkey: HotkeyWatcher | None = None
        self._server: socket.socket | None = None
        self._status = LOADING
        self.indicator = Indicator(enabled=cfg.indicator and cfg.tray)

    def _needs_download(self, chosen) -> bool:
        """True when the picked backend still has to fetch its weights."""
        name = resolve_name(self.cfg)
        if chosen.backend == "openvino":
            repo = ov_model_id(name)
            return not (repo and ov_ready(ov_dir(repo)))
        return not ct2_ready(ct2_dir(name))

    def start_recording(self) -> None:
        self._harvest_pending_tail()
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
        log.info("Recording")
        self._set_icon("recording", "listening", badge="listening")
        beep("start", self.cfg.beep)
        try:
            self.recorder.start()
            if self.cfg.live_preview:
                self._preview_stop.clear()
                threading.Thread(target=self._preview_loop, daemon=True).start()
        except Exception:
            log.exception("Microphone failed")
            beep("err", self.cfg.beep)
            with self._lock:
                self.state = "idle"
            self._show_error(
                "no_mic",
                NO_MIC,
                "Another app may be using it, or pick a different mic in Settings.",
            )

    def _preview_loop(self) -> None:
        while not self._preview_stop.wait(0.75):
            if self.state != "recording":
                return
            audio = self.recorder.snapshot(max_seconds=4.0)
            if self.recorder.seconds(audio) < 0.65:
                continue
            try:
                draft = transcribe_preview(audio, self.cfg)
            except Exception:
                log.debug("Live preview failed", exc_info=True)
                continue
            if draft and self.state == "recording" and not self._preview_stop.is_set():
                self.indicator.set("listening", draft)

    def stop_recording(self) -> None:
        self._preview_stop.set()
        with self._lock:
            if self.state != "recording":
                return
            follow_on = self._job_running
            if not follow_on:
                self._job_running = True
            self.state = "busy"
        request_final()
        self._set_icon("busy", "transcribing", badge="transcribing")
        beep("stop", self.cfg.beep)
        target = foreground_id()
        cut_id = self._cut_id
        continuation = self._take_continuation
        timer = threading.Timer(
            TAIL_SECONDS, self._cut, args=(target, follow_on, cut_id, continuation)
        )
        self._tail_timer = timer
        timer.start()

    def _harvest_pending_tail(self) -> None:
        timer = self._tail_timer
        if timer is None:
            return
        self._tail_timer = None
        timer.cancel()
        self._cut(
            foreground_id(), self._job_running, self._cut_id, self._take_continuation
        )

    def _cut(self, target, follow_on: bool, cut_id: int, continuation=None) -> None:
        with self._lock:
            if cut_id != self._cut_id or self._tail_done_for == cut_id:
                return
            self._tail_done_for = cut_id
            self._tail_timer = None
        audio = self.recorder.stop()
        seconds = self.recorder.seconds(audio)
        if seconds < self.cfg.min_seconds:
            log.info("Ignored short tap (%.2fs)", seconds)
            if follow_on:
                return
            with self._lock:
                self._cancel_job = False
                self._job_running = False
            clear_final()
            self._job_running = False
            self._flash("too_short")
            return
        if seconds > self.cfg.max_seconds:
            audio = audio[: int(self.cfg.max_seconds * 16000)]
        if follow_on:
            self._queued_audio = audio
            self._queued_target = target
            self._queued_continuation = continuation
            log.info("Queued next take")
            return
        threading.Thread(
            target=self._finish, args=(audio, target, continuation), daemon=True
        ).start()

    def cancel_recording(self) -> None:
        self._preview_stop.set()
        clear_final()
        self._queued_audio = None
        self._queued_target = None
        self._queued_continuation = None
        with self._lock:
            if self.state == "recording":
                self.state = "idle"
                self.recorder.stop()
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
                log.info("Paste skipped")
                self._after_job()
                return
            app_name = foreground_app()
            raw = transcribe(audio, self.cfg)
            # Esc may arrive during a long decode. Check again before editing
            # or pasting into the user's app, not just before transcription.
            if self._cancel_job or self._stop.is_set():
                self._cancel_job = False
                self._queued_audio = None
                self._queued_target = None
                self._queued_continuation = None
                self._after_job()
                return
            log.debug("Heard (%s): %s", app_name or "?", raw)
            if not raw:
                self._after_job("missed")
                return
            result = polish(
                raw,
                app_name=app_name,
                remove_fillers=self.cfg.remove_fillers,
                fix_corrections=self.cfg.fix_corrections,
            )
            if result.command_only and self.last_text and (
                not self.last_target
                or foreground_id() != self.last_target
                or (time.time() - self.last_paste_at) >= 20
            ):
                self._after_job("no_paste", "Return to your last dictation to use an edit command.")
                return
            if result.discarded:
                if result.command_only and self.last_text:
                    undo_last()
                    self.last_text = ""
                    self.last_app = ""
                    self.last_target = None
                    self.last_paste_at = 0.0
                log.info("Discarded")
                self._after_job("hide")
                return
            if result.command_only and result.command and self.last_text:
                from utterleaf.polish import apply_edit, polish_local

                text = apply_edit(self.last_text, result.command)
                if result.command == "professional":
                    text = polish_local(text, app_name="outlook").text or text
                if text and text != self.last_text:
                    undo_last()
                    time.sleep(0.05)
                    paste(text, restore_clipboard=self.cfg.restore_clipboard, target=target)
                    self.last_text = text
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
            if result.command in {"bullets", "numbered", "paragraph", "newline"}:
                to_paste = ("\n" + text) if previous else text
            else:
                to_paste = stitch_to_previous(previous, text)
            outcome = paste(
                to_paste,
                restore_clipboard=self.cfg.restore_clipboard,
                target=target,
            )
            if outcome == "pasted":
                self.last_text = text.strip()
                self.last_app = app_name
                self.last_target = target
                self.last_paste_at = time.time()
                log.debug("Pasted: %s", to_paste)
                beep("ok", self.cfg.beep)
                self._after_job("pasted", to_paste)
                return
            if outcome == "clipboard":
                beep("err", self.cfg.beep)
                self._after_job("clipboard", to_paste)
                return
            # Heard fine, could not deliver it. Never blame the user's voice.
            beep("err", self.cfg.beep)
            self._after_job("no_paste", "The target app refused the paste.")
            return
        except Exception:
            log.exception("Transcription failed")
            beep("err", self.cfg.beep)
            self._after_job("transcribe", "Transcription failed — see the log.")
            return

    def _after_job(self, badge: str = "hide", caption: str = "") -> None:
        queued = self._queued_audio
        queued_target = self._queued_target
        queued_continuation = self._queued_continuation
        self._queued_audio = None
        self._queued_target = None
        self._queued_continuation = None
        if queued is not None:
            threading.Thread(
                target=self._finish,
                args=(queued, queued_target, queued_continuation),
                daemon=True,
            ).start()
            return
        with self._lock:
            self._job_running = False
            still_recording = self.state == "recording"
        if still_recording:
            return
        self._flash(badge, caption)

    def _hide_after(self, seconds: float) -> None:
        """Daemon timer: a pending pill must never hold up quit()."""

        def hide() -> None:
            if self.state == "idle":
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
        if self.icon is not None:
            self.icon.icon = mic_image(color)
            self.icon.title = tray_title(self._status)
        if badge is not None:
            self.indicator.set(badge, caption)

    def quit(self) -> None:
        self._stop.set()
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
        if command == "toggle":
            if self.hotkey is None:
                return "error"
            self.hotkey.toggle()
            return "ok"
        if command == "start":
            self.start_recording()
            return "ok"
        if command == "stop":
            self.stop_recording()
            return "ok"
        if command == "cancel":
            self.cancel_recording()
            return "ok"
        if command == "quit":
            threading.Thread(target=self.quit, daemon=True).start()
            return "ok"
        if command == "ping":
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
            self.recorder.set_device(new.microphone)
            if self.state != "recording":
                try:
                    self.recorder.prepare()
                except Exception:
                    log.exception(
                        "Could not open microphone %s",
                        new.microphone or "(system default)",
                    )
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
                        "Dictation is unavailable. Check the log for details.",
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
            mic_ready = True
            try:
                self.recorder.prepare()
            except Exception:
                mic_ready = False
                log.exception("Microphone failed to open")
                self._show_error("no_mic", NO_MIC,
                                 "Choose a working microphone in Settings.")
            try:
                self.indicator.set("loading")
                chosen = pick(self.cfg)
                log.info("Device: %s via %s (%s)", chosen.kind, chosen.backend, chosen.name)
                if self._needs_download(chosen):
                    self.indicator.set("loading", DOWNLOADING)
                load_model(self.cfg, chosen)
                log.info("Model ready")
                self._set_icon("idle", status_hint(self.cfg) if mic_ready else NO_MIC,
                               badge="hide" if mic_ready else "no_mic")
            except Exception:
                log.exception("Model failed to load")
                self._show_error(
                    "engine",
                    ENGINE_FAILED,
                    "Dictation is unavailable. Check the log for details.",
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

        def toggle_startup(_icon=None, item=None) -> None:
            try:
                set_startup(not startup_enabled())
            except Exception:
                log.exception("Could not change start at login")

        menu = Menu(
            MenuItem(lambda item: f"Utterleaf — {status_hint(self.cfg)}", None, enabled=False),
            Menu.SEPARATOR,
            # default=True: a left-click on the tray icon opens Settings.
            MenuItem("Settings…", lambda *_: launch_settings(), default=True),
            MenuItem(
                login_label(),
                toggle_startup,
                checked=lambda _: startup_enabled(),
            ),
            Menu.SEPARATOR,
            MenuItem("Open dictionary", lambda *_: open_path(dictionary_path())),
            MenuItem("Open log", lambda *_: open_path(log_path())),
            MenuItem("Quit", lambda *_: self.quit()),
        )
        color = "busy" if self._status == LOADING else "idle"
        self.indicator.start()
        self.icon = Icon("Utterleaf", mic_image(color), tray_title(self._status), menu)
        if first_run:
            launch_settings()
        def setup(icon):
            icon.visible = True
            log.info("Tray ready (%s)", tray_backend())

        self.icon.run(setup=setup)
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
    )
    return result.text
