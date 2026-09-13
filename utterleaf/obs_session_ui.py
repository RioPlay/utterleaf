"""Local, nonblocking OBS session controls and transcript preview.

The view owns no credentials, pairing key, capture object, model, or result. It
renders supplied snapshots and forwards explicit user intent to an injected
adapter. Construction and polling never invoke an action.
"""

from __future__ import annotations

import ntpath
import tkinter as tk
from tkinter import filedialog, ttk

from utterleaf import theme
from utterleaf.host import ui_font


POLL_MS = 100
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
_EXPORT_STATES = frozenset({"complete", "incomplete", "failed"})
_RUNNING_STATES = frozenset({"connecting", "preparing", "armed", "active", "stopping", "finalizing"})
_PAIR_STATES = frozenset({"disabled", "busy", "ready", "complete", "incomplete", "empty", "error", "cancelled"})

_STATE_TITLES = {
    "disabled": "Connect to OBS",
    "connecting": "Verifying local OBS",
    "busy": "OBS is already streaming",
    "ready": "Ready for the next stream",
    "preparing": "Preparing a private session",
    "armed": "Armed for the next stream",
    "active": "Transcribing locally",
    "stopping": "Finishing accepted audio",
    "finalizing": "Finishing the transcript",
    "complete": "Transcript complete",
    "incomplete": "Recovered transcript available",
    "empty": "No audio was captured",
    "error": "OBS transcription needs attention",
    "cancelling": "Discarding this session",
    "cancelled": "Session discarded",
}


def _value(value) -> str:
    value = getattr(value, "value", value)
    return value if isinstance(value, str) else "unknown"


class ObsSessionWindow:
    """A reusable OBS session Toplevel driven only by supplied snapshots.

    ``actions`` provides nonblocking ``connect``, ``arm``, ``disarm``,
    ``cancel``, ``pair``, ``export`` and ``close`` methods. The caller retains
    every controller, coordinator, credential, pairing key and exported result.
    """

    def __init__(self, parent, controller, coordinator, actions, *, poll_ms: int = POLL_MS):
        self.parent = parent
        self.controller = controller
        self.coordinator = coordinator
        self.actions = actions
        self.poll_ms = poll_ms
        self.closed = False
        self._focused = False
        self._connect_sent = False
        self._poll_id = None
        self._last_state = ""
        self._bus_values: dict[str, int] = {}
        self._compact = False

        self.root = tk.Toplevel(parent)
        theme.apply(self.root)
        self.root.title("Utterleaf · OBS transcription")
        self.root.geometry("840x720")
        self.root.minsize(560, 520)
        self.root.transient(parent)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self._styles()

        page = ttk.Frame(self.root, style="Page.TFrame", padding=(24, 20, 24, 14))
        self.page = page
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(6, weight=1)

        self.eyebrow = ttk.Label(page, text="OBS TRANSCRIPTION", style="Eyebrow.TLabel")
        self.eyebrow.grid(row=0, column=0, sticky="w")
        self.hero = ttk.Label(page, text="Capture the stream you choose", style="Obs.Hero.TLabel")
        self.hero.grid(row=1, column=0, sticky="w", pady=(5, 2))
        self.intro = ttk.Label(
            page,
            text="Connect locally, arm once, then start streaming in OBS. The complete stream mix is always included.",
            style="Subtitle.TLabel",
            wraplength=760,
        )
        self.intro.grid(row=2, column=0, sticky="ew", pady=(0, 14))

        self._build_status(page)
        self._build_connection(page)
        self._build_session(page)
        self._build_transcript(page)

        footer = ttk.Frame(self.root, padding=(20, 11))
        footer.grid(row=1, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        self.pair_button = ttk.Button(footer, text="Pairing…", command=self._pair)
        self.pair_button.grid(row=0, column=0, sticky="w")
        self.cancel_button = ttk.Button(footer, text="Cancel & discard", command=self._cancel)
        self.cancel_button.grid(row=0, column=2, padx=(8, 0))
        self.close_button = ttk.Button(footer, text="Close", command=self.close)
        self.close_button.grid(row=0, column=3, padx=(8, 0))

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _event: self.close())
        self.root.bind("<Configure>", self._resize, add="+")
        self.root.bind("<Map>", self._mapped, add="+")
        self.root.bind("<Destroy>", self._destroyed, add="+")
        self.root.bind("<Control-Return>", self._primary_shortcut, add="+")
        for entry in (self.host_entry, self.port_entry, self.password_entry, self.executable_entry):
            entry.bind("<Return>", lambda _event: self._connect())

        self.refresh()
        if not self.closed:
            self._poll_id = self.root.after(self.poll_ms, self._poll)

    def __repr__(self) -> str:
        return f"ObsSessionWindow(state={self._last_state!r}, closed={self.closed!r})"

    def _styles(self) -> None:
        family = ui_font()
        style = ttk.Style(self.root)
        style.configure("Obs.Hero.TLabel", background=theme.SURFACE_LOW,
                        foreground=theme.ON_SURFACE, font=(family, 23, "bold"))
        style.configure("Obs.Status.TLabel", background=theme.SURFACE_CONTAINER,
                        foreground=theme.ON_SURFACE, font=(family, 15, "bold"))
        style.configure("Obs.CardTitle.TLabel", background=theme.SURFACE_CONTAINER,
                        foreground=theme.ON_SURFACE, font=(family, 11, "bold"))
        style.configure("Obs.CardHint.TLabel", background=theme.SURFACE_CONTAINER,
                        foreground=theme.ON_VARIANT, font=(family, 9))
        style.configure("Obs.Badge.TLabel", background=theme.PRIMARY_CONTAINER,
                        foreground=theme.ON_PRIMARY_CONTAINER, font=(family, 9, "bold"),
                        padding=(9, 4))
        style.configure("Obs.Error.TLabel", background=theme.SURFACE_CONTAINER,
                        foreground=theme.ERROR, font=(family, 9))
        style.configure("Obs.Danger.TButton", background=theme.PRIMARY_CONTAINER,
                        foreground=theme.ON_PRIMARY_CONTAINER, padding=(16, 8))
        style.map("Obs.Danger.TButton", background=[("active", theme.OUTLINE_VARIANT)],
                  foreground=[("disabled", theme.OUTLINE)])
        style.configure("Obs.Card.TCheckbutton", background=theme.SURFACE_CONTAINER,
                        foreground=theme.ON_SURFACE, focuscolor=theme.PRIMARY,
                        indicatorbackground=theme.SURFACE_LOW,
                        indicatorforeground=theme.ON_PRIMARY)
        style.map("Obs.Card.TCheckbutton", background=[("active", theme.SURFACE_CONTAINER)],
                  foreground=[("disabled", theme.OUTLINE)],
                  indicatorbackground=[("selected", theme.PRIMARY),
                                       ("active", theme.SURFACE_LOW)])

    def _card(self, parent, row: int):
        card = ttk.Frame(parent, style="Card.TFrame", padding=15)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 11))
        card.columnconfigure(0, weight=1)
        return card

    def _build_status(self, page) -> None:
        card = self._card(page, 3)
        self.status_card = card
        card.columnconfigure(0, weight=0)
        accent = tk.Frame(card, bg=theme.PRIMARY, width=4, highlightthickness=0)
        accent.grid(row=0, column=0, rowspan=4, sticky="nsw", padx=(0, 12))
        card.columnconfigure(1, weight=1)
        self.state_text = tk.StringVar(self.root, "Connect to OBS")
        self.message_text = tk.StringVar(self.root, "OBS transcription is off.")
        self.state_label = ttk.Label(card, textvariable=self.state_text, style="Obs.Status.TLabel")
        self.state_label.grid(row=0, column=1, sticky="ew")
        self.message_label = ttk.Label(card, textvariable=self.message_text,
                                       style="Obs.CardHint.TLabel", wraplength=700)
        self.message_label.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        self.degraded_text = tk.StringVar(self.root, "")
        self.degraded_label = ttk.Label(card, textvariable=self.degraded_text,
                                        style="Obs.Badge.TLabel")
        self.action_error = tk.StringVar(self.root, "")
        self.action_error_label = ttk.Label(card, textvariable=self.action_error,
                                            style="Obs.Error.TLabel", wraplength=700)
        self.action_error_label.grid(row=3, column=1, sticky="ew", pady=(7, 0))
        self.action_error_label.grid_remove()

    def _build_connection(self, page) -> None:
        self.connection_card = self._card(page, 4)
        ttk.Label(self.connection_card, text="Local OBS connection",
                  style="Obs.CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        self.connection_hint = ttk.Label(
            self.connection_card,
            text="Use OBS WebSocket on this computer. The executable path is checked against the connected process.",
            style="Obs.CardHint.TLabel", wraplength=700,
        )
        self.connection_hint.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(3, 11))

        self.host_var = tk.StringVar(self.root, "127.0.0.1")
        self.port_var = tk.StringVar(self.root, "4455")
        self.password_var = tk.StringVar(self.root, "")
        self.executable_var = tk.StringVar(self.root, "")
        ttk.Label(self.connection_card, text="Host", style="Obs.CardHint.TLabel").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Label(self.connection_card, text="Port", style="Obs.CardHint.TLabel").grid(
            row=2, column=1, sticky="w", padx=(10, 0)
        )
        ttk.Label(self.connection_card, text="Password", style="Obs.CardHint.TLabel").grid(
            row=2, column=2, sticky="w", padx=(10, 0)
        )
        self.host_entry = ttk.Entry(self.connection_card, textvariable=self.host_var, width=16)
        self.port_entry = ttk.Entry(self.connection_card, textvariable=self.port_var, width=8)
        self.password_entry = ttk.Entry(self.connection_card, textvariable=self.password_var,
                                        width=20, show="•")
        self.host_entry.grid(row=3, column=0, sticky="ew")
        self.port_entry.grid(row=3, column=1, sticky="ew", padx=(10, 0))
        self.password_entry.grid(row=3, column=2, sticky="ew", padx=(10, 0))
        self.connection_card.columnconfigure(2, weight=1)

        ttk.Label(self.connection_card, text="OBS executable", style="Obs.CardHint.TLabel").grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(10, 0)
        )
        self.executable_entry = ttk.Entry(self.connection_card, textvariable=self.executable_var)
        self.executable_entry.grid(row=5, column=0, columnspan=3, sticky="ew")
        self.browse_button = ttk.Button(self.connection_card, text="Browse…", command=self._browse)
        self.browse_button.grid(row=5, column=3, padx=(10, 0))
        self.connection_error = tk.StringVar(self.root, "")
        self.connection_error_label = ttk.Label(
            self.connection_card, textvariable=self.connection_error,
            style="Obs.Error.TLabel", wraplength=590,
        )
        self.connection_error_label.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(7, 0))
        self.connect_button = ttk.Button(self.connection_card, text="Connect",
                                         style="Primary.TButton", command=self._connect)
        self.connect_button.grid(row=6, column=3, sticky="e", padx=(10, 0), pady=(7, 0))

        self.connection_summary = ttk.Frame(page, style="Card.TFrame", padding=(15, 10))
        self.connection_summary.grid(row=4, column=0, sticky="ew", pady=(0, 11))
        self.connection_summary.columnconfigure(0, weight=1)
        self.connection_summary_title = tk.StringVar(self.root, "Local OBS connection")
        ttk.Label(self.connection_summary, textvariable=self.connection_summary_title,
                  style="Obs.CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self.connection_summary, text="Password cleared after the connection attempt.",
                  style="Obs.CardHint.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.connection_summary.grid_remove()

    def _build_session(self, page) -> None:
        card = self._card(page, 5)
        self.capture_card = card
        ttk.Label(card, text="Capture", style="Obs.CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.capture_hint = ttk.Label(
            card,
            text="The complete streaming mix is automatic. Optional mixes follow OBS routing and are not isolated speakers.",
            style="Obs.CardHint.TLabel", wraplength=700,
        )
        self.capture_hint.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 9))
        mix_row = ttk.Frame(card, style="Card.TFrame")
        self.mix_row = mix_row
        mix_row.grid(row=2, column=0, sticky="w")
        self.mix_vars = []
        self.mix_buttons = []
        for bus in range(6):
            variable = tk.BooleanVar(self.root, False)
            button = ttk.Checkbutton(mix_row, text=f"Mix {bus + 1}", variable=variable,
                                     style="Obs.Card.TCheckbutton")
            button.grid(row=0, column=bus, padx=(0, 8))
            self.mix_vars.append(variable)
            self.mix_buttons.append(button)
        actions = ttk.Frame(card, style="Card.TFrame")
        self.capture_actions = actions
        actions.grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.arm_button = ttk.Button(actions, text="Arm next stream", style="Primary.TButton",
                                     command=self._arm)
        self.arm_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="Stop", style="Obs.Danger.TButton",
                                      command=self._stop)
        self.stop_button.pack(side="left", padx=(8, 0))
        self.capture_meta = tk.StringVar(self.root, "Complete stream mix · waiting")
        ttk.Label(card, textvariable=self.capture_meta, style="Obs.CardHint.TLabel").grid(
            row=4, column=0, sticky="w", pady=(9, 0)
        )

    def _build_transcript(self, page) -> None:
        card = ttk.Frame(page, style="Card.TFrame", padding=15)
        self.transcript_card = card
        card.grid(row=6, column=0, sticky="nsew", pady=(0, 11))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)
        ttk.Label(card, text="Transcript preview", style="Obs.CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.progress_text = tk.StringVar(self.root, "Waiting for selected OBS audio.")
        ttk.Label(card, textvariable=self.progress_text, style="Obs.CardHint.TLabel").grid(
            row=1, column=0, sticky="ew", pady=(3, 8)
        )
        text_frame = tk.Frame(card, bg=theme.OUTLINE_VARIANT, padx=1, pady=1)
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        self.preview = tk.Text(
            text_frame, wrap="word", undo=False, height=8, borderwidth=0,
            padx=12, pady=10, bg=theme.SURFACE_LOW, fg=theme.ON_SURFACE,
            insertbackground=theme.PRIMARY, selectbackground=theme.PRIMARY_CONTAINER,
            selectforeground=theme.ON_SURFACE, exportselection=False,
        )
        self.preview.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.preview.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.preview.configure(yscrollcommand=scroll.set, state="disabled")

        export_row = ttk.Frame(card, style="Card.TFrame")
        self.export_row = export_row
        export_row.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        export_row.columnconfigure(0, weight=1)
        self.export_bus_var = tk.StringVar(self.root, "")
        self.export_format_var = tk.StringVar(self.root, "Text (.txt)")
        self.export_bus = ttk.Combobox(export_row, textvariable=self.export_bus_var,
                                       state="readonly", width=15)
        self.export_bus.grid(row=0, column=1, padx=(8, 0))
        self.export_format = ttk.Combobox(
            export_row, textvariable=self.export_format_var, state="readonly",
            values=("Text (.txt)", "JSON (.json)"), width=14,
        )
        self.export_format.grid(row=0, column=2, padx=(8, 0))
        self.export_button = ttk.Button(export_row, text="Export…", command=self._export)
        self.export_button.grid(row=0, column=3, padx=(8, 0))

    def _mapped(self, event) -> None:
        if event.widget is self.root and not self.closed and not self._focused:
            self._focused = True
            (self.host_entry if self._last_state == "disabled" else self.close_button).focus_set()

    def _resize(self, event) -> None:
        if event.widget is not self.root:
            return
        width = max(220, event.width - 120)
        self.intro.configure(wraplength=width)
        self.message_label.configure(wraplength=width)
        self.action_error_label.configure(wraplength=width)
        self.connection_error_label.configure(wraplength=width)
        self.connection_hint.configure(wraplength=width)
        compact = event.height < 620
        if compact == self._compact:
            return
        self._compact = compact
        self.page.configure(padding=(14, 9, 14, 6) if compact else (24, 20, 24, 14))
        content_padding = 12 if compact else 15
        for card in (self.status_card, self.capture_card, self.transcript_card):
            card.configure(padding=content_padding)
        if compact:
            self.eyebrow.grid_remove()
            self.hero.grid_remove()
            self.intro.grid_remove()
            self.capture_hint.grid_remove()
            if self._last_state != "disabled" or self._connect_sent:
                self.connection_summary.grid_remove()
        else:
            self.eyebrow.grid()
            self.hero.grid()
            self.intro.grid()
            self.capture_hint.grid()
            if self._show_connection_summary():
                self.connection_summary.grid()
        self._update_export_row()
        self._update_compact_copy()
        self._update_compact_sections()
        if self.degraded_text.get():
            self.degraded_text.set(
                "Controls disconnected" if compact else
                "Controls disconnected · audio remains local"
            )
            if compact:
                self.degraded_label.grid(
                    row=0, column=2, sticky="e", padx=(10, 0), pady=0
                )
            else:
                self.degraded_label.grid(
                    row=2, column=1, sticky="w", padx=0, pady=(9, 0)
                )

    def _primary_shortcut(self, _event):
        if str(self.arm_button.cget("state")) != "disabled":
            self._arm()
        elif str(self.connect_button.cget("state")) != "disabled":
            self._connect()
        return "break"

    def _browse(self) -> None:
        if self.closed:
            return
        path = filedialog.askopenfilename(
            parent=self.root, title="Choose the OBS executable",
            filetypes=(("OBS executable", "*.exe"), ("Applications", "*.exe")),
        )
        if path and not self.closed:
            self.executable_var.set(path)
            self.executable_entry.focus_set()

    def _connect(self) -> None:
        if self.closed or str(self.connect_button.cget("state")) == "disabled":
            return
        host = self.host_var.get().strip()
        port_text = self.port_var.get().strip()
        executable = self.executable_var.get().strip()
        password = self.password_var.get()
        problem = ""
        focus = None
        if host not in _LOOPBACK_HOSTS:
            problem, focus = "Use the numeric local address 127.0.0.1 or ::1.", self.host_entry
        elif not port_text.isascii() or not port_text.isdecimal() or not 1 <= int(port_text) <= 65535:
            problem, focus = "Enter the OBS WebSocket port from 1 to 65535.", self.port_entry
        elif not password:
            problem, focus = "Enter the OBS WebSocket password.", self.password_entry
        elif not ntpath.isabs(executable) or not ntpath.basename(executable):
            problem, focus = "Choose the full local path to the OBS executable.", self.executable_entry
        if problem:
            self.password_var.set("")
            self.connection_error.set(problem)
            focus.focus_set()
            return
        self.connection_error.set("")
        try:
            accepted = self.actions.connect(host, int(port_text), password, executable)
            self._connect_sent = accepted is not False
            if accepted is False:
                self.connection_error.set("The connection request was not accepted. Open a fresh session to retry.")
        except Exception:
            self._connect_sent = True
            self.action_error.set("The connection request could not be started. Open a fresh session to retry.")
        finally:
            self.password_var.set("")
        self.refresh()

    def _arm(self) -> None:
        if self.closed or str(self.arm_button.cget("state")) == "disabled":
            return
        mask = sum((1 << bus) for bus, variable in enumerate(self.mix_vars) if variable.get())
        self._invoke(self.actions.arm, mask)

    def _stop(self) -> None:
        if not self.closed and str(self.stop_button.cget("state")) != "disabled":
            self._invoke(self.actions.disarm)

    def _cancel(self) -> None:
        if not self.closed and str(self.cancel_button.cget("state")) != "disabled":
            self._invoke(self.actions.cancel)

    def _pair(self) -> None:
        if not self.closed and str(self.pair_button.cget("state")) != "disabled":
            self._invoke(self.actions.pair)

    def _export(self) -> None:
        if self.closed or str(self.export_button.cget("state")) == "disabled":
            return
        bus = self._bus_values.get(self.export_bus_var.get())
        format_name = {"Text (.txt)": "txt", "JSON (.json)": "json"}.get(
            self.export_format_var.get()
        )
        if bus is None or format_name is None:
            return
        self._invoke(self.actions.export, bus, format_name)

    def _invoke(self, callback, *args) -> None:
        try:
            callback(*args)
        except Exception:
            self.action_error.set("That action could not be started. Review the session status and try again.")
        else:
            self.action_error.set("")
        if not self.closed:
            self.refresh()

    def _poll(self) -> None:
        self._poll_id = None
        if self.closed:
            return
        self.refresh()
        if not self.closed:
            self._poll_id = self.root.after(self.poll_ms, self._poll)

    def refresh(self) -> None:
        if self.closed:
            return
        try:
            session = self.controller.snapshot()
            recognition = self.coordinator.snapshot()
            state = _value(session.state)
            recognition_state = _value(recognition.state)
        except Exception:
            state, recognition_state = "error", "failed"
            session = recognition = None

        self._last_state = state
        self.state_text.set(_STATE_TITLES.get(state, "OBS session unavailable"))
        self._session_message = getattr(
            session, "message", "The session status could not be read safely."
        )
        degraded = bool(getattr(session, "control_degraded", False))
        self.degraded_text.set(
            ("Controls disconnected" if self._compact else
             "Controls disconnected · audio remains local") if degraded else ""
        )
        if degraded:
            if self._compact:
                self.degraded_label.grid(
                    row=0, column=2, sticky="e", padx=(10, 0), pady=0
                )
            else:
                self.degraded_label.grid(
                    row=2, column=1, sticky="w", padx=0, pady=(9, 0)
                )
        else:
            self.degraded_label.grid_remove()
        if self.action_error.get():
            self.action_error_label.grid()
        else:
            self.action_error_label.grid_remove()

        details_visible = state == "disabled" and not self._connect_sent
        focused = self.root.focus_get()
        focus_will_hide = focused in {
            self.host_entry, self.port_entry, self.password_entry, self.executable_entry,
            self.browse_button, self.connect_button,
        }
        if details_visible:
            self.connection_summary.grid_remove()
            self.connection_card.grid()
        else:
            self.password_var.set("")
            self.connection_card.grid_remove()
            if not self._show_connection_summary():
                self.connection_summary.grid_remove()
            else:
                self.connection_summary.grid()
        self.connection_summary_title.set(
            "Connecting to local OBS" if state == "connecting" else "Local OBS connection"
        )

        connect_enabled = details_visible
        self.connect_button.configure(state="normal" if connect_enabled else "disabled")
        self.browse_button.configure(state="normal" if connect_enabled else "disabled")
        for entry in (self.host_entry, self.port_entry, self.password_entry, self.executable_entry):
            entry.configure(state="normal" if connect_enabled else "disabled")

        arm_enabled = state == "ready"
        stop_enabled = state in {"armed", "active", "stopping"}
        selection_enabled = state in {"disabled", "connecting", "busy", "ready"}
        self.arm_button.configure(state="normal" if arm_enabled else "disabled")
        self.stop_button.configure(state="normal" if stop_enabled else "disabled",
                                   text="Stopping…" if state == "stopping" else "Stop")
        for button in self.mix_buttons:
            button.configure(state="normal" if selection_enabled else "disabled")
        self._update_capture_sections(state, selection_enabled)
        if focus_will_hide and not details_visible:
            target = self.arm_button if arm_enabled else self.stop_button if stop_enabled else self.close_button
            target.focus_set()

        preview_value = getattr(recognition, "preview", "") if recognition is not None else ""
        retained = (
            recognition_state in _EXPORT_STATES
            and int(getattr(recognition, "track_count", 0) or 0) > 0
            and isinstance(preview_value, str)
            and bool(preview_value.strip())
        )
        cancel_enabled = state in _RUNNING_STATES or retained or state in {"complete", "incomplete", "error"}
        self.cancel_button.configure(
            state="normal" if cancel_enabled else "disabled",
            text="Discard result" if state in {"complete", "incomplete", "error"} else "Cancel & discard",
        )
        self.pair_button.configure(state="normal" if state in _PAIR_STATES else "disabled")

        primary = getattr(session, "primary_bus", None)
        buses = tuple(getattr(session, "buses", ()) or ())
        seconds = float(getattr(session, "captured_seconds", 0.0) or 0.0)
        primary_text = f"Primary: Mix {primary + 1}" if type(primary) is int and 0 <= primary < 6 else "Primary mix: waiting"
        selected_text = ", ".join(f"Mix {bus + 1}" for bus in buses if type(bus) is int and 0 <= bus < 6)
        self.capture_meta.set(
            f"{primary_text} · {selected_text or 'complete stream mix'} · {self._duration(seconds)}"
        )

        preview = preview_value if isinstance(preview_value, str) else ""
        self.preview.configure(state="normal")
        current = self.preview.get("1.0", "end-1c")
        if current != preview:
            self.preview.delete("1.0", "end")
            self.preview.insert("1.0", preview)
            self.preview.see("end")
        self.preview.configure(state="disabled")
        tracks = int(getattr(recognition, "track_count", 0) or 0)
        completed = int(getattr(recognition, "completed_tracks", 0) or 0)
        self._recognition_message = getattr(
            recognition, "message", "Waiting for selected OBS audio."
        )
        self._progress_counts = (completed, tracks)
        self._update_compact_copy()

        bus_labels = [
            (bus, f"Mix {bus + 1}" + (" · primary" if bus == primary else ""))
            for bus in buses if type(bus) is int and 0 <= bus < 6
        ]
        labels = [label for _bus, label in bus_labels]
        self._bus_values = {label: bus for bus, label in bus_labels}
        self.export_bus.configure(values=labels,
                                  state="readonly" if retained and labels else "disabled")
        if labels and self.export_bus_var.get() not in self._bus_values:
            primary_label = next((label for label in labels if "primary" in label), labels[0])
            self.export_bus_var.set(primary_label)
        if not labels:
            self.export_bus_var.set("")
        self.export_format.configure(state="readonly" if retained and labels else "disabled")
        self.export_button.configure(state="normal" if retained and labels else "disabled")
        self._retained_output = retained and bool(labels)
        self._update_export_row()
        self._update_compact_sections()

    def _update_export_row(self) -> None:
        if not hasattr(self, "export_row"):
            return
        if getattr(self, "_retained_output", False):
            self.export_row.grid()
        else:
            self.export_row.grid_remove()

    def _show_connection_summary(self) -> bool:
        return (
            not self._compact
            and ((self._connect_sent and self._last_state == "disabled") or self._last_state in {
                "connecting", "busy", "ready", "preparing", "armed",
            })
        )

    def _update_compact_copy(self) -> None:
        session_limit = 52 if self._compact else 240
        recognition_limit = 52 if self._compact else 180
        self.message_text.set(self._bounded_text(
            getattr(self, "_session_message", "The session status could not be read safely."),
            session_limit,
        ))
        recognition_message = self._bounded_text(
            getattr(self, "_recognition_message", "Waiting for selected OBS audio."),
            recognition_limit,
        )
        completed, tracks = getattr(self, "_progress_counts", (0, 0))
        self.progress_text.set(
            f"{recognition_message} · {completed}/{tracks} mixes finished"
            if tracks else recognition_message
        )

    def _update_compact_sections(self) -> None:
        if self._compact and self._last_state == "disabled":
            self.capture_card.grid_remove()
            self.transcript_card.grid_remove()
        else:
            self.capture_card.grid()
            self.transcript_card.grid()

    def _update_capture_sections(self, state: str, selection_enabled: bool) -> None:
        terminal = state in {"complete", "incomplete", "empty", "error", "cancelled"}
        compact_capture = state in {"armed", "active", "stopping", "finalizing"}
        if selection_enabled:
            self.mix_row.grid()
        else:
            self.mix_row.grid_remove()
        if terminal:
            self.capture_hint.grid_remove()
            self.capture_actions.grid_remove()
        elif compact_capture:
            self.capture_hint.grid_remove()
            self.capture_actions.grid()
            self.arm_button.pack_forget()
            if not self.stop_button.winfo_manager():
                self.stop_button.pack(side="left")
        else:
            if not self._compact:
                self.capture_hint.grid()
            self.capture_actions.grid()
            if not self.arm_button.winfo_manager():
                self.arm_button.pack(side="left", before=self.stop_button)

    @staticmethod
    def _duration(seconds: float) -> str:
        seconds = max(0, int(seconds))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:d}:{seconds:02d}"

    @staticmethod
    def _bounded_text(value, limit: int) -> str:
        if not isinstance(value, str):
            return "Status unavailable."
        value = " ".join(value.split())
        return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.password_var.set("")
        if self._poll_id is not None:
            try:
                self.root.after_cancel(self._poll_id)
            except tk.TclError:
                pass
            self._poll_id = None
        try:
            self.actions.close()
        except Exception:
            pass
        if self.root.winfo_exists():
            self.root.destroy()

    def _destroyed(self, event) -> None:
        if event.widget is not self.root or self.closed:
            return
        self.closed = True
        self.password_var.set("")
        self._poll_id = None
        try:
            self.actions.close()
        except Exception:
            pass


# A panel host can use the same concrete view contract while the app entry point
# remains intentionally absent pending live OBS metadata and distribution gates.
ObsSessionView = ObsSessionWindow
