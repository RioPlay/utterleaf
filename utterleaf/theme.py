"""Utterleaf's shared dark palette and accessible native-widget styles."""

from __future__ import annotations

from utterleaf.host import ui_font


def _fonts() -> tuple[str, tuple, tuple, tuple, tuple]:
    family = ui_font()
    return family, (family, 22, "bold"), (family, 10), (family, 9), (family, 10, "bold")

# Dark by default, with the same green identity as the tray leaf.
PRIMARY = "#83DA9A"
PRIMARY_HOVER = "#A0E9B2"
ON_PRIMARY = "#102A1B"
PRIMARY_CONTAINER = "#203C2D"
ON_PRIMARY_CONTAINER = "#C1F2CD"
SURFACE = "#171E20"
SURFACE_LOW = "#101617"
SURFACE_CONTAINER = "#283335"
ON_SURFACE = "#E5EEE8"
ON_VARIANT = "#AABCB1"
OUTLINE = "#71897B"
OUTLINE_VARIANT = "#35483D"
ERROR = "#FFB4AB"

# Dark surfaces for the always-on overlay.
PILL_SURFACE = "#1C1B1F"
PILL_TEXT = "#E6E1E5"
PILL_MUTED = "#CAC4D0"


from utterleaf.brand import STATE_COLORS, leaf_image, leaf_master


def apply(root) -> None:
    """Paint Settings and artwork windows with the default dark theme."""
    from tkinter import ttk

    _family, font_title, font_body, font_hint, font_button = _fonts()
    root.configure(bg=SURFACE)
    # A global *Font overrides ttk's named styles, erasing title hierarchy.
    root.option_add("*Text.Font", font_body)
    root.option_add("*TCombobox*Listbox.background", SURFACE_CONTAINER)
    root.option_add("*TCombobox*Listbox.foreground", ON_SURFACE)
    root.option_add("*TCombobox*Listbox.selectBackground", PRIMARY_CONTAINER)
    root.option_add("*TCombobox*Listbox.selectForeground", ON_PRIMARY_CONTAINER)
    # Preserve the platform's scaling so text respects the user's display size.

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(".", background=SURFACE, foreground=ON_SURFACE, font=font_body)
    style.configure("TFrame", background=SURFACE)
    style.configure("Page.TFrame", background=SURFACE_LOW)
    style.configure("Page.TLabel", background=SURFACE_LOW)
    style.configure("Card.TFrame", background=SURFACE_CONTAINER, relief="flat")
    style.configure("TLabel", background=SURFACE, foreground=ON_SURFACE, font=font_body)
    style.configure("Title.TLabel", background=SURFACE_LOW, foreground=ON_SURFACE, font=font_title)
    style.configure("Subtitle.TLabel", background=SURFACE_LOW, foreground=ON_VARIANT, font=font_body)
    style.configure("Hint.TLabel", background=SURFACE, foreground=ON_VARIANT, font=font_hint)
    style.configure("Card.TLabel", background=SURFACE_CONTAINER, foreground=ON_SURFACE, font=font_body)
    style.configure(
        "TCheckbutton",
        background=SURFACE,
        foreground=ON_SURFACE,
        font=font_body,
        focuscolor=PRIMARY,
    )
    style.map("TCheckbutton", background=[("active", SURFACE)])
    for control in ("TCheckbutton", "TRadiobutton"):
        style.configure(control, background=SURFACE, foreground=ON_SURFACE,
                        focuscolor=PRIMARY,
                        indicatorbackground=SURFACE_CONTAINER, indicatorforeground=ON_PRIMARY)
        style.map(control, background=[("active", SURFACE)],
                  foreground=[("disabled", OUTLINE)],
                  indicatorbackground=[("selected", PRIMARY), ("active", SURFACE_CONTAINER)])
    style.configure("TScrollbar", background=SURFACE_CONTAINER, troughcolor=SURFACE_LOW,
                    arrowcolor=ON_VARIANT, bordercolor=SURFACE)
    style.map("TScrollbar", background=[("active", OUTLINE_VARIANT)])
    style.configure("TNotebook", background=SURFACE, bordercolor=OUTLINE_VARIANT)
    style.configure("TNotebook.Tab", background=SURFACE_CONTAINER, foreground=ON_VARIANT, padding=(10, 6))
    style.map("TNotebook.Tab", background=[("selected", PRIMARY_CONTAINER)],
              foreground=[("selected", ON_PRIMARY_CONTAINER)])
    style.configure(
        "TCombobox",
        fieldbackground=SURFACE_LOW,
        background=SURFACE_LOW,
        foreground=ON_SURFACE,
        arrowcolor=ON_VARIANT,
        bordercolor=OUTLINE_VARIANT,
        lightcolor=OUTLINE_VARIANT,
        darkcolor=OUTLINE_VARIANT,
        padding=6,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", SURFACE_LOW)],
        foreground=[("readonly", ON_SURFACE)],
        bordercolor=[("focus", PRIMARY)],
        lightcolor=[("focus", PRIMARY)],
        darkcolor=[("focus", PRIMARY)],
    )
    style.configure(
        "TEntry",
        fieldbackground=SURFACE_LOW,
        foreground=ON_SURFACE,
        padding=6,
        bordercolor=OUTLINE_VARIANT,
        lightcolor=OUTLINE_VARIANT,
        darkcolor=OUTLINE_VARIANT,
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", PRIMARY)],
        lightcolor=[("focus", PRIMARY)],
        darkcolor=[("focus", PRIMARY)],
    )
    style.configure(
        "TButton",
        background=SURFACE_CONTAINER,
        foreground=ON_SURFACE,
        font=font_body,
        padding=(16, 8),
        relief="flat",
        borderwidth=0,
        focuscolor=PRIMARY,
    )
    style.map("TButton", background=[("active", OUTLINE_VARIANT)],
              foreground=[("disabled", OUTLINE)])
    style.configure(
        "Primary.TButton",
        background=PRIMARY,
        foreground=ON_PRIMARY,
        font=font_button,
        padding=(20, 8),
        relief="flat",
        borderwidth=0,
        focuscolor=ON_PRIMARY,
    )
    style.map("Primary.TButton", background=[("disabled", SURFACE_CONTAINER), ("active", PRIMARY_HOVER)],
              foreground=[("disabled", OUTLINE), ("!disabled", ON_PRIMARY)])
    style.configure("Section.TLabel", font=(_family, 13, "bold"))
    style.configure("Eyebrow.TLabel", background=SURFACE_LOW, foreground=PRIMARY, font=(_family, 9, "bold"))
    style.configure("Nav.TButton", anchor="w", padding=(16, 12), background=SURFACE_LOW)
    style.map("Nav.TButton", background=[("active", SURFACE_CONTAINER)])
    style.configure("Selected.Nav.TButton", background=PRIMARY_CONTAINER,
                    foreground=ON_PRIMARY_CONTAINER, font=font_button)
    style.map("Selected.Nav.TButton", background=[("active", PRIMARY_CONTAINER)])
    style.configure("TSeparator", background=OUTLINE_VARIANT)
    style.configure("TProgressbar", background=PRIMARY, troughcolor=SURFACE_CONTAINER,
                    borderwidth=0, thickness=6)
