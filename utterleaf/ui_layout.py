"""Small native-Tk layout primitives for resizable auxiliary windows."""

import math
import tkinter as tk
from tkinter import ttk

from utterleaf import theme


def wrapped_label(parent, **options):
    """Wrap to allocated width without imposing a text-sized minimum width."""
    label = ttk.Label(parent, width=1, wraplength=1, **options)
    label.bind("<Configure>", lambda event: label.configure(wraplength=max(1, event.width)))
    return label


class ActionRow(ttk.Frame):
    """Keep natural control sizes, wrapping in creation/focus order as needed."""

    def __init__(self, parent):
        super().__init__(parent)
        self.controls = []
        self._layout_key = None
        self.bind("<Configure>", self._layout)

    def add(self, widget):
        self.controls.append(widget)
        widget.bind("<Configure>", self._layout, add="+")
        self._layout_key = None
        self._layout()
        return widget

    def _layout(self, _event=None):
        width = self.winfo_width()
        sizes = tuple((w.winfo_reqwidth(), w.winfo_reqheight()) for w in self.controls)
        key = (width, sizes)
        if key == self._layout_key:
            return
        self._layout_key = key
        x = y = row_height = 0
        for widget, (requested_width, height) in zip(self.controls, sizes):
            if x and x + requested_width > width:
                x = 0
                y += row_height + 8
                row_height = 0
            widget.place(x=x, y=y, width=requested_width, height=height)
            x += requested_width + 8
            row_height = max(row_height, height)
        self.configure(height=max(1, y + row_height))


class ScrollableContent(ttk.Frame):
    """A local scroll viewport; no polling, global bindings or input collection."""

    def __init__(self, parent, padding=20):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0,
                                background=theme.SURFACE, takefocus=False)
        self.scrollbar = ttk.Scrollbar(self, command=self.canvas.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.body = ttk.Frame(self.canvas, padding=padding)
        self._item = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self._resize_id = None
        self._top = self.winfo_toplevel()
        self._bindings = []
        for sequence, callback in (
            ("<Configure>", self._queue_resize),
            ("<FocusIn>", self._focus), ("<KeyPress>", self._cursor),
            ("<KeyRelease>", self._cursor), ("<ButtonRelease-1>", self._cursor),
            ("<MouseWheel>", self._wheel), ("<Button-4>", self._wheel),
            ("<Button-5>", self._wheel),
        ):
            self._bindings.append((sequence, self._top.bind(sequence, callback, add="+")))
        for sequence in ("<Prior>", "<Next>", "<Home>", "<End>"):
            self._bindings.append((sequence, self._top.bind(sequence, self._page, add="+")))
        self.bind("<Destroy>", self._destroy)

    def _destroy(self, event):
        if event.widget is self:
            if self._resize_id is not None:
                self.after_cancel(self._resize_id)
            for sequence, identifier in self._bindings:
                self._top.unbind(sequence, identifier)

    def _queue_resize(self, event):
        if (event.widget in (self.canvas, self.body) or self._owns(event.widget)) and self._resize_id is None:
            # Wait for child wrapping/geometry requests to settle. This is a
            # coalesced response to layout events, never a recurring idle poll.
            self._resize_id = self.after_idle(self._resize)

    def _resize(self, _event=None):
        self._resize_id = None
        width = max(1, self.canvas.winfo_width())
        height = max(self.canvas.winfo_height(), self.body.winfo_reqheight())
        self.canvas.itemconfigure(self._item, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _owns(self, widget):
        return str(widget).startswith(str(self.body) + ".")

    def _focus(self, event):
        # FocusIn also propagates through ancestors: moving those can shift a
        # button under the pointer or displace a combobox popup before release.
        if not self._owns(event.widget) or event.widget.winfo_class() not in {
            "Text", "Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox",
            "Button", "TButton", "TCheckbutton", "TRadiobutton", "TScale",
        }:
            return
        self.reveal(event.widget)

    def reveal(self, widget):
        if not self._owns(widget) or not widget.winfo_ismapped():
            return
        self.update_idletasks()
        top = widget.winfo_rooty() - self.canvas.winfo_rooty()
        bottom = top + widget.winfo_height()
        viewport = self.canvas.winfo_height()
        if isinstance(widget, tk.Text) and widget.winfo_height() > viewport:
            widget.see("insert")
            self.update_idletasks()
            line = widget.dlineinfo("insert")
            if line is None:
                return
            top += line[1]
            bottom = top + line[3]
        region = max(viewport, self.body.winfo_height())
        current = self.canvas.yview()[0] * region
        target = current + top - 8 if top < 0 else current + bottom - viewport + 8 if bottom > viewport else current
        self.canvas.yview_moveto(max(0, min(region - viewport, target)) / max(1, region))

    def _cursor(self, event):
        if (isinstance(event.widget, tk.Text) and self._owns(event.widget)
                and self._top.focus_get() is event.widget
                and event.widget.winfo_height() > self.canvas.winfo_height()):
            self.reveal(event.widget)

    @staticmethod
    def _native_keys(widget):
        return widget.winfo_class() in {"Text", "Entry", "TEntry", "Spinbox", "TSpinbox",
                                        "Listbox", "TCombobox", "Scale", "TScale"}

    def _modified(self, event):
        # Aqua Mod2 means Option; on other Tk backends it is Num Lock.
        lock_mask = 0x2 if self.tk.call("tk", "windowingsystem") == "aqua" else 0x12
        return bool(event.state & ~lock_mask)

    def _page(self, event):
        if self._native_keys(event.widget):
            self._cursor(event)
            return
        if self._modified(event):
            return
        if event.widget.winfo_toplevel() is not self._top:
            return
        if event.keysym in {"Home", "End"}:
            self.canvas.yview_moveto(0 if event.keysym == "Home" else 1)
        else:
            self.canvas.yview_scroll(-1 if event.keysym == "Prior" else 1, "pages")
        return "break"

    def _wheel(self, event):
        if (not (event.widget is self.canvas or self._owns(event.widget))
                or self._native_keys(event.widget)
                or event.widget.winfo_class() in {"Scrollbar", "TScrollbar"}):
            return
        if self._modified(event):
            return
        if event.num in (4, 5):
            units = -3 if event.num == 4 else 3
        elif event.delta:
            units = -max(1, abs(event.delta) // 120) if event.delta > 0 else max(1, abs(event.delta) // 120)
        else:
            return
        self.canvas.yview_scroll(units, "units")
        return "break"


def readonly_preview(widget):
    """Make a disabled Text focusable without trapping Tab in the preview."""
    widget.configure(takefocus=True)
    widget.mark_set("insert", "1.0")

    def traverse(backward=False):
        target = widget.tk_focusPrev() if backward else widget.tk_focusNext()
        if target is not None:
            target.focus_set()
        return "break"

    widget.bind("<Tab>", lambda _event: traverse())
    widget.bind("<Shift-Tab>", lambda _event: traverse(True))
    widget.bind("<ISO_Left_Tab>", lambda _event: traverse(True))


def inset(level=3):
    """Select a shared spacing step (0 through 5)."""
    return theme.SPACING[level]


def _rounded(canvas, box, radius, **options):
    x, y, right, bottom = box
    radius = min(radius, max(0, (right - x) / 2), max(0, (bottom - y) / 2))
    points = []
    for cx, cy, start in ((right - radius, y + radius, -90),
                          (right - radius, bottom - radius, 0),
                          (x + radius, bottom - radius, 90),
                          (x + radius, y + radius, 180)):
        for step in range(13):
            angle = math.radians(start + step * 7.5)
            points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return canvas.create_polygon(*points, **options)



class Card(tk.Frame):
    """Rounded decorative surface with a normal, naturally sized content frame.

    Containers do not add tab stops. Their native child controls retain focus,
    traversal, selection and assistive-technology semantics.
    """

    def __init__(self, parent, *, padding=16, surface=theme.SURFACE_CARD,
                 background=theme.SURFACE_BASE):
        super().__init__(parent, bg=background, borderwidth=0, takefocus=False)
        self.surface = surface
        self.art = tk.Canvas(self, bg=background, highlightthickness=0,
                             borderwidth=0, takefocus=False)
        self.art.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = ttk.Frame(self, padding=padding)
        self.body.pack(fill="both", expand=True, padx=6, pady=6)
        self.art.bind("<Configure>", self._draw)

    def _draw(self, event):
        self.art.delete("all")
        _rounded(self.art, (1, 3, event.width - 1, event.height - 1),
                 theme.RADII[2], fill=theme.SURFACE_LOW, outline="")
        _rounded(self.art, (1, 1, event.width - 1, event.height - 3),
                 theme.RADII[2], fill=self.surface, outline=theme.HAIRLINE, width=1)


class SectionHeader(ttk.Label):
    """Semantic native label, intentionally excluded from keyboard traversal."""

    def __init__(self, parent, text, **options):
        super().__init__(parent, text=text, style="Section.TLabel", takefocus=False, **options)


class _RoundedControl:
    """Canvas finish on a native ttk control, preserving its bindings and class.

    Pointer events are forwarded to the native button. Keyboard activation and
    tab traversal remain ttk's, and the Canvas never receives keyboard focus.
    """

    def _finish(self, *, pill=False):
        self._pill = pill
        self._hover = False
        self._draw_id = None
        self.bind("<Destroy>", self._cancel_draw, add="+")
        self._art = tk.Canvas(self, highlightthickness=0, borderwidth=0, takefocus=False)
        self._art.place(x=0, y=0, relwidth=1, relheight=1)
        for sequence in ("<Configure>", "<FocusIn>", "<FocusOut>",
                         "<KeyPress>", "<KeyRelease>", "<ButtonRelease-1>"):
            self.bind(sequence, self._redraw_later, add="+")
        self._art.bind("<Configure>", self._draw_control)
        for sequence in ("<Enter>", "<Leave>", "<ButtonPress-1>", "<ButtonRelease-1>"):
            self._art.bind(sequence, lambda e, seq=sequence: self._forward(e, seq))

    def _forward(self, event, sequence):
        self._hover = sequence != "<Leave>"
        self.event_generate(sequence, x=event.x, y=event.y)
        self._draw_control()

    def _redraw_later(self, _event=None):
        if self._draw_id is None:
            self._draw_id = self.after_idle(self._draw_control)

    def _cancel_draw(self, event):
        if event.widget is self and self._draw_id is not None:
            self.after_cancel(self._draw_id)
            self._draw_id = None

    def configure(self, cnf=None, **options):
        result = super().configure(cnf, **options)
        if hasattr(self, "_art"):
            self._draw_control()
        return result

    config = configure

    def state(self, statespec=None):
        result = super().state(statespec)
        if statespec is not None and hasattr(self, "_art"):
            self._draw_control()
        return result

    def _draw_control(self, _event=None):
        if self._draw_id is not None:
            self.after_cancel(self._draw_id)
            self._draw_id = None
        if not self.winfo_exists():
            return
        art = self._art
        art.delete("all")
        selected = self.instate(("selected",)) or str(self.cget("style")).startswith("Selected.")
        disabled = self.instate(("disabled",))
        background = theme.SURFACE_LOW if self._pill else theme.SURFACE_CARD
        fill = theme.STATE_SELECTED if selected else background
        if not disabled:
            if self.instate(("pressed",)):
                fill = theme.STATE_PRESSED
            elif self._hover:
                fill = theme.STATE_HOVER
        focused = self.focus_get() is self
        art.configure(bg=background)
        w, h = self.winfo_width(), self.winfo_height()
        _rounded(art, (2, 2, w - 2, h - 2), h / 2 if self._pill else theme.RADII[1],
                 fill=fill, outline=theme.FOCUS_RING if focused else theme.HAIRLINE if selected or not self._pill else fill,
                 width=theme.FOCUS_WIDTH if focused else 1)
        # Selection also uses weight and a small leaf-green marker, not color alone.
        if selected and self._pill:
            art.create_oval(10, h / 2 - 2, 14, h / 2 + 2, fill=theme.PRIMARY, outline="")
        art.create_text(20 if self._pill else 12, h / 2, anchor="w", text=self.cget("text"),
                        font=(*theme.font("body"), "bold") if selected else theme.font("body"),
                        fill=theme.DISABLED_CONTENT if disabled else theme.ON_PRIMARY_CONTAINER if selected else theme.ON_SURFACE)


class PillNav(_RoundedControl, ttk.Button):
    """Native keyboard button with a rounded, restrained active surface."""

    def __init__(self, parent, **options):
        super().__init__(parent, **options)
        self._finish(pill=True)


class SegmentedControl(_RoundedControl, ttk.Radiobutton):
    """One native radio segment. Group segments using the same Tk variable.

    Segments retain creation/tab order, support Space and arrow selection, and
    can wrap or stack using the caller's existing geometry manager.
    """

    def __init__(self, parent, *, variable, **options):
        super().__init__(parent, variable=variable, style="Segmented.TRadiobutton", **options)
        self._finish()
        self._variable = variable
        self._trace = variable.trace_add("write", self._redraw_later)
        self.bind("<Destroy>", self._cleanup, add="+")
        for sequence, direction in (("<Left>", -1), ("<Up>", -1), ("<Right>", 1), ("<Down>", 1)):
            self.bind(sequence, lambda _e, delta=direction: self._step(delta))

    def _redraw_later(self, *_args):
        super()._redraw_later()

    def _cleanup(self, event):
        if event.widget is self:
            self._variable.trace_remove("write", self._trace)

    def _step(self, direction):
        peers = [w for w in self.master.winfo_children()
                 if isinstance(w, SegmentedControl) and w._variable is self._variable
                 and not w.instate(("disabled",))]
        if self in peers:
            target = peers[(peers.index(self) + direction) % len(peers)]
            target.focus_set()
            target.invoke()
        return "break"


class Field(ttk.Entry):
    """Native text editing with taller insets and a visible focus border."""

    def __init__(self, parent, **options):
        options.setdefault("style", "Field.TEntry")
        super().__init__(parent, **options)


class Divider(tk.Canvas):
    """Decorative hairline, not an extra keyboard stop."""

    def __init__(self, parent, **options):
        super().__init__(parent, height=1, bg=theme.SURFACE_CARD,
                         highlightthickness=0, takefocus=False, **options)
        self.bind("<Configure>", self._draw)

    def _draw(self, event):
        self.delete("all")
        self.create_line(0, 0, event.width, 0, fill=theme.HAIRLINE)
