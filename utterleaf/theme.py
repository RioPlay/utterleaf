"""Material 3 tokens for Settings and the status pill. No extra UI kit."""

from __future__ import annotations

from utterleaf.host import ui_font


def _fonts() -> tuple[str, tuple, tuple, tuple, tuple]:
    family = ui_font()
    return family, (family, 22, "bold"), (family, 10), (family, 9), (family, 10, "bold")

# Teal primary, light surface — same family as the tray leaf.
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


# State -> ring color, same family for tray, pill accents, and the exe icon.
STATE_COLORS = {
    "idle": (15, 118, 110, 255),
    "recording": (228, 105, 98, 255),
    "busy": (232, 196, 104, 255),
}

_DISC = (18, 20, 22, 255)
_LEAF_MASTER = 2048


def _bezier(p0, p1, p2, p3, steps=48) -> list[tuple[float, float]]:
    points = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]
        points.append((x, y))
    return points


def leaf_master(state: str = "idle"):
    """Supersampled brand badge: dark disc, state ring, leaf with a mouth cutout.

    The leaf blade is the intersection of two discs (tip up-right, stem to the
    lower left), with a speaking-mouth opening punched through it. Drawn large
    and downscaled so tray-size curves stay smooth.
    """
    from PIL import Image, ImageChops, ImageDraw

    ring = STATE_COLORS[state]
    size = _LEAF_MASTER
    center = size // 2
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((24, 24, size - 24, size - 24), fill=_DISC)
    draw.ellipse((64, 64, size - 64, size - 64), fill=ring)

    # Leaf group in its own canvas, leaf-local: blade + stem + vein, mouth punched.
    g = 3072
    gc = g // 2
    radius, offset = 1063, 544
    left = Image.new("L", (g, g), 0)
    ImageDraw.Draw(left).ellipse(
        (gc - offset - radius, gc - radius, gc - offset + radius, gc + radius), fill=255
    )
    right = Image.new("L", (g, g), 0)
    ImageDraw.Draw(right).ellipse(
        (gc + offset - radius, gc - radius, gc + offset + radius, gc + radius), fill=255
    )
    blade = ImageChops.multiply(left, right)
    alpha = Image.new("L", (g, g), 0)
    alpha.paste(blade, (0, 0))
    mask_draw = ImageDraw.Draw(alpha)
    mask_draw.rounded_rectangle((gc - 30, gc + 860, gc + 30, gc + 1360), radius=30, fill=255)

    leaf = Image.new("RGBA", (g, g), (0, 0, 0, 0))
    white = Image.new("RGBA", (g, g), (255, 255, 255, 255))
    leaf.paste(white, (0, 0), mask=alpha)
    vein = Image.new("L", (g, g), 0)
    ImageDraw.Draw(vein).line((gc, gc - 820, gc, gc + 830), fill=255, width=34)
    leaf.paste(Image.new("RGBA", (g, g), _DISC), (0, 0), mask=vein)

    leaf = leaf.rotate(35, resample=Image.BICUBIC, center=(gc, gc))
    image.alpha_composite(leaf, (center - gc, center - gc))

    # Mouth cutout, punched after the rotation so it stays level: cupid's-bow
    # top edge, fuller lower curve, wider than tall like real lips.
    mouth: list[tuple[float, float]] = []
    mouth += _bezier((-280, 0), (-150, -130), (-60, -80), (0, -45))
    mouth += _bezier((0, -45), (60, -80), (150, -130), (280, 0))
    mouth += _bezier((280, 0), (170, 190), (70, 230), (0, 230))
    mouth += _bezier((0, 230), (-70, 230), (-170, 190), (-280, 0))
    mouth = [(center + x, center + 150 + y) for x, y in mouth]
    hole = Image.new("L", (size, size), 255)
    ImageDraw.Draw(hole).polygon(mouth, fill=0)
    image.putalpha(ImageChops.multiply(image.getchannel("A"), hole))

    # Anything outside the disc disappears; the stem may run to the rim.
    clip = Image.new("L", (size, size), 0)
    ImageDraw.Draw(clip).ellipse((24, 24, size - 24, size - 24), fill=255)
    alpha_channel = image.getchannel("A")
    image.putalpha(ImageChops.multiply(alpha_channel, clip))
    return image


def leaf_image(state: str = "idle"):
    """The leaf badge used for the tray icon and the Settings window icon."""
    from PIL import Image

    return leaf_master(state).resize((64, 64), Image.Resampling.LANCZOS)


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
