"""Material 3 tokens for Settings and the status pill. No extra UI kit."""

from __future__ import annotations

from utterleaf.host import ui_font


def _fonts() -> tuple[str, tuple, tuple, tuple, tuple]:
    family = ui_font()
    return family, (family, 22, "bold"), (family, 10), (family, 9), (family, 10, "bold")

# Teal primary, light surface — same family as the tray mic.
PRIMARY = "#0F766E"
PRIMARY_HOVER = "#0D9488"
ON_PRIMARY = "#FFFFFF"
PRIMARY_CONTAINER = "#CCFBF1"
ON_PRIMARY_CONTAINER = "#134E4A"
SURFACE = "#FFFFFF"
SURFACE_LOW = "#F5F7F8"
SURFACE_CONTAINER = "#EDF2F3"
ON_SURFACE = "#172B35"
ON_VARIANT = "#526671"
OUTLINE = "#788B94"
OUTLINE_VARIANT = "#DAE3E7"
ERROR = "#B3261E"

# Dark surfaces for the always-on overlay.
PILL_SURFACE = "#1C1B1F"
PILL_TEXT = "#E6E1E5"
PILL_MUTED = "#CAC4D0"


def mic_image(state: str = "idle"):
    """The mic badge used for the tray icon and the Settings window icon."""
    from PIL import Image, ImageDraw

    fill = {
        "idle": (15, 118, 110, 255),
        "recording": (228, 105, 98, 255),
        "busy": (232, 196, 104, 255),
    }[state]
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, 62, 62), fill=(18, 20, 22, 255))
    draw.ellipse((6, 6, 58, 58), fill=fill)
    # Mic capsule + stand
    draw.rounded_rectangle((26, 14, 38, 36), radius=7, fill=(255, 255, 255, 255))
    draw.arc((20, 24, 44, 48), start=0, end=180, fill=(255, 255, 255, 255), width=3)
    draw.rectangle((31, 46, 33, 52), fill=(255, 255, 255, 255))
    draw.rectangle((24, 51, 40, 54), fill=(255, 255, 255, 255))
    return image


def apply(root) -> None:
    """Paint a Tk root with the Material light theme."""
    from tkinter import ttk

    _family, font_title, font_body, font_hint, font_button = _fonts()
    root.configure(bg=SURFACE)
    # A global *Font overrides ttk's named styles, erasing title hierarchy.
    root.option_add("*Text.Font", font_body)
    # Preserve the platform's scaling so text respects the user's display size.

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(".", background=SURFACE, foreground=ON_SURFACE, font=font_body)
    style.configure("TFrame", background=SURFACE)
    style.configure("Card.TFrame", background=SURFACE_CONTAINER, relief="flat")
    style.configure("TLabel", background=SURFACE, foreground=ON_SURFACE, font=font_body)
    style.configure("Title.TLabel", background=SURFACE, foreground=ON_SURFACE, font=font_title)
    style.configure("Hint.TLabel", background=SURFACE, foreground=ON_VARIANT, font=font_hint)
    style.configure("Card.TLabel", background=SURFACE_CONTAINER, foreground=ON_SURFACE, font=font_body)
    style.configure(
        "TCheckbutton",
        background=SURFACE,
        foreground=ON_SURFACE,
        font=font_body,
        focuscolor=SURFACE,
    )
    style.map("TCheckbutton", background=[("active", SURFACE)])
    style.configure(
        "TCombobox",
        fieldbackground=SURFACE_LOW,
        background=SURFACE_LOW,
        foreground=ON_SURFACE,
        arrowcolor=ON_VARIANT,
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
    )
    style.map("TButton", background=[("active", SURFACE_LOW)])
    style.configure(
        "Primary.TButton",
        background=PRIMARY,
        foreground=ON_PRIMARY,
        font=font_button,
        padding=(20, 8),
        relief="flat",
        borderwidth=0,
    )
    style.map("Primary.TButton", background=[("active", PRIMARY_HOVER)])
    style.configure("Section.TLabel", font=(_family, 13, "bold"))
    style.configure("Eyebrow.TLabel", foreground=PRIMARY, font=(_family, 9, "bold"))
    style.configure("Nav.TButton", anchor="w", padding=(16, 12), background=SURFACE_LOW)
    style.map("Nav.TButton", background=[("active", SURFACE_CONTAINER)])
    style.configure("Selected.Nav.TButton", background=PRIMARY_CONTAINER,
                    foreground=ON_PRIMARY_CONTAINER, font=font_button)
    style.map("Selected.Nav.TButton", background=[("active", PRIMARY_CONTAINER)])
    style.configure("TSeparator", background=OUTLINE_VARIANT)
    style.configure("TProgressbar", background=PRIMARY, troughcolor=SURFACE_CONTAINER,
                    borderwidth=0, thickness=6)
