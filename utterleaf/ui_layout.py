"""Small native-Tk layout primitives for resizable auxiliary windows."""

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
