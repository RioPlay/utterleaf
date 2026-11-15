"""Utterleaf's shared dark palette and accessible native-widget styles."""

from __future__ import annotations

from utterleaf.host import ui_font


def _fonts() -> tuple[str, tuple, tuple, tuple, tuple]:
    family = ui_font()
    return family, font("page_title"), font("body"), font("hint"), (family, 10, "bold")

# Dark by default, with the same green identity as the tray leaf.
PRIMARY = "#83DA9A"
PRIMARY_HOVER = "#A0E9B2"
ON_PRIMARY = "#102A1B"
PRIMARY_CONTAINER = "#203C2D"
ON_PRIMARY_CONTAINER = "#C1F2CD"
SURFACE = "#1B2425"
SURFACE_LOW = "#0E1515"
SURFACE_CONTAINER = "#283335"
ON_SURFACE = "#E5EEE8"
ON_VARIANT = "#AABCB1"
OUTLINE = "#71897B"
OUTLINE_VARIANT = "#35483D"
ERROR = "#FFB4AB"

# Shared tokens. Font sizes are points, leaving Tk display scaling intact.
SPACING = (4, 8, 12, 16, 24, 32)
TYPE_SCALE = {"page_title": (22, "bold"), "section_label": (12, "bold"),
              "body": (10,), "hint": (9,), "caption": (9, "bold")}
RADII = (6, 10, 14)
SURFACE_BASE = "#131B1C"
SURFACE_CARD = SURFACE
SURFACE_RAISED = SURFACE_CONTAINER
HAIRLINE = "#334443"
FOCUS_RING = PRIMARY
FOCUS_WIDTH = 2
STATE_HOVER = "#2D3E39"
STATE_PRESSED = "#182F25"
STATE_SELECTED = PRIMARY_CONTAINER
DISABLED_CONTENT = "#8B9C92"


def font(role="body"):
    """Return a point-based font token using the platform's UI family."""
    return (ui_font(), *TYPE_SCALE[role])


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
    style.configure("Page.TFrame", background=SURFACE_BASE)
    style.configure("Page.TLabel", background=SURFACE_BASE)
    style.configure("Card.TFrame", background=SURFACE_CONTAINER, relief="flat")
    style.configure("TLabel", background=SURFACE, foreground=ON_SURFACE, font=font_body)
    style.configure("Title.TLabel", background=SURFACE_BASE, foreground=ON_SURFACE, font=font_title)
    style.configure("Subtitle.TLabel", background=SURFACE_BASE, foreground=ON_VARIANT, font=font_body)
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
                  foreground=[("disabled", DISABLED_CONTENT)],
                  indicatorbackground=[("selected", PRIMARY), ("active", SURFACE_CONTAINER)])
    style.configure("TScrollbar", background=HAIRLINE, troughcolor=SURFACE_BASE,
                    arrowcolor=ON_VARIANT, bordercolor=SURFACE_BASE,
                    lightcolor=SURFACE_BASE, darkcolor=SURFACE_BASE,
                    borderwidth=0, arrowsize=12, gripcount=0)
    style.map("TScrollbar", background=[("pressed", STATE_PRESSED), ("active", STATE_HOVER)])
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
        padding=(12, 10),
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
        padding=(12, 10),
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
    style.map("TButton", background=[("pressed", STATE_PRESSED), ("active", STATE_HOVER)],
              foreground=[("disabled", DISABLED_CONTENT)])
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
    style.configure("Section.TLabel", font=font("section_label"))
    style.configure("Eyebrow.TLabel", background=SURFACE_BASE, foreground=PRIMARY, font=(_family, 9, "bold"))
    style.configure("Nav.TButton", anchor="w", padding=(16, 12), background=SURFACE_BASE)
    style.map("Nav.TButton", background=[("active", SURFACE_CONTAINER)])
    style.configure("Selected.Nav.TButton", background=PRIMARY_CONTAINER,
                    foreground=ON_PRIMARY_CONTAINER, font=font_button)
    style.map("Selected.Nav.TButton", background=[("active", PRIMARY_CONTAINER)])
    style.configure("TSeparator", background=OUTLINE_VARIANT)
    style.configure("TProgressbar", background=PRIMARY, troughcolor=SURFACE_CONTAINER,
                    borderwidth=0, thickness=6)

    style.configure("Segmented.TRadiobutton", padding=(12, 8), font=font_body)
    style.configure("Field.TEntry", padding=(12, 10), borderwidth=FOCUS_WIDTH)
    style.configure("TCombobox", borderwidth=FOCUS_WIDTH, arrowsize=14)
    style.map("TCombobox", foreground=[("disabled", DISABLED_CONTENT), ("readonly", ON_SURFACE)],
              arrowcolor=[("disabled", DISABLED_CONTENT), ("!disabled", ON_VARIANT)])
    style.map("TEntry", foreground=[("disabled", DISABLED_CONTENT)])
