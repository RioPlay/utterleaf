"""Real Tk interaction checks for the shared visual primitives."""
import tkinter as tk
from tkinter import ttk

from test_settings_ui import tk_root
from utterleaf import theme
from utterleaf.ui_layout import Card, Divider, Field, PillNav, SectionHeader, SegmentedControl, inset


import pytest
pytestmark = pytest.mark.ui  # needs a real display; excluded from the default headless run

def test_card_keeps_native_children_and_decorations_out_of_tab_order(tk_root):
    root = tk.Toplevel(tk_root)
    theme.apply(root)
    try:
        card = Card(root)
        card.pack(fill='both', expand=True)
        header = SectionHeader(card.body, 'Your voice')
        header.pack()
        field = Field(card.body)
        field.pack()
        divider = Divider(card.body)
        divider.pack(fill='x')
        button = ttk.Button(card.body, text='Next')
        button.pack()
        root.update()
        assert field.winfo_class() == 'TEntry'
        assert field.tk_focusNext() is button
        assert str(header.cget('takefocus')) == '0'
        assert str(divider.cget('takefocus')) == '0'
        assert card.art.find_all()
        assert field.winfo_reqheight() >= 30
        assert inset() == 16
        assert ttk.Style(root).lookup('Field.TEntry', 'bordercolor', ('focus',)) == theme.FOCUS_RING
    finally:
        root.destroy()


def test_segments_keyboard_selection_disabled_rejection_and_focus_ring(tk_root):
    root = tk.Toplevel(tk_root)
    theme.apply(root)
    try:
        choice = tk.StringVar(root, 'hold')
        first = SegmentedControl(root, text='Hold', variable=choice, value='hold')
        second = SegmentedControl(root, text='Toggle', variable=choice, value='toggle')
        first.pack()
        second.pack()
        root.update()
        first.focus_force()
        first.event_generate('<Right>')
        root.update()
        assert choice.get() == 'toggle'
        assert root.focus_get() is second
        assert second.winfo_class() == 'TRadiobutton'
        assert second._art.itemcget(second._art.find_all()[0], 'outline') == theme.FOCUS_RING
        first.configure(state='disabled')
        first.invoke()
        assert choice.get() == 'toggle'
        second.event_generate('<Left>')
        root.update()
        assert root.focus_get() is second
        assert second.tk_focusNext() is second  # disabled segment is skipped
    finally:
        root.destroy()


def test_pill_pointer_and_keyboard_use_native_button_and_disabled_blocks_activation(tk_root):
    root = tk.Toplevel(tk_root)
    theme.apply(root)
    calls = []
    try:
        button = PillNav(root, text='Dictation', command=lambda: calls.append('activated'))
        button.pack()
        root.update()
        button._art.event_generate('<Enter>')
        button._art.event_generate('<ButtonPress-1>', x=15, y=15)
        button._art.event_generate('<ButtonRelease-1>', x=15, y=15)
        root.update()
        assert calls == ['activated']
        button.focus_force()
        button.event_generate('<KeyPress-space>')
        button.event_generate('<KeyRelease-space>')
        root.update()
        assert calls == ['activated', 'activated']
        button.configure(state='disabled')
        button.invoke()
        assert len(calls) == 2
        assert button.winfo_class() == 'TButton'
    finally:
        root.destroy()
