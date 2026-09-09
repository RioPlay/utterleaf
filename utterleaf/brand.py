"""Leaf/waveform identity, shared by vector exports and Pillow tray rendering."""
from __future__ import annotations

from functools import lru_cache

STATE_COLORS = {
    "idle": "#75E44B",
    "recording": "#E46962",
    "busy": "#49CEDB",
    "error": "#FF786B",
}
DARK = "#07191D"
MARK_COLORS = {"green": "#137D40", "black": DARK, "gray": "#5C696D", "light": "#B9C4C7", "inverse": "#FFFFFF"}
STATE_LABELS = {
    "idle": ("Ready", "Ready to dictate, including offline. No audio is being captured."),
    "recording": ("Recording", "The microphone is capturing your take. A solid dot accompanies the color."),
    "busy": ("Processing", "Opening a device, loading the model, or transcribing. The tooltip gives the exact status."),
    "error": ("Needs attention", "Microphone, engine, transcription, or delivery failure. Read the status message for details."),
}
MASCOT_LABELS = {
    "default": ("Welcome", "Dictation header and stopped microphone checks."),
    "listening": ("Listening", "Microphone check after the device opens."),
    "thinking": ("Thinking", "Help header, opening a microphone, or very little audio detected."),
    "success": ("Success", "Audio detected during the microphone check."),
    "error": ("Concern", "Microphone check failed; the message explains why."),
    "speaking": ("Speaking", "Illustration for guides. Does not indicate a speech-output feature."),
    "typing": ("Typing", "Illustration for guides. Does not confirm that text was delivered."),
}
# Cubic segments on a 100-unit canvas. An open base separates the leaf and stem.
OUTLINE = [
    ((39, 77), (9, 62), (18, 40), (35, 24)),
    ((35, 24), (43, 17), (48, 11), (50, 7)),
    ((50, 7), (52, 18), (67, 29), (76, 43)),
    ((76, 43), (90, 64), (71, 76), (61, 79)),
]
BARS = [(31, 51, 61), (40, 43, 68), (50, 31, 89), (60, 43, 68), (69, 51, 61)]


def mark_svg(color="#137D40") -> str:
    start = OUTLINE[0][0]
    path = f"M {start[0]} {start[1]} " + " ".join(
        "C " + " ".join(f"{x} {y}" for x, y in segment[1:]) for segment in OUTLINE
    )
    bars = "".join(f'<path d="M{x} {top}V{bottom}"/>' for x, top, bottom in BARS)
    return f'<g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"><path d="{path}"/>{bars}</g>'


def svg_document(body, *, width=100, height=100, title="Utterleaf"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img"><title>{title}</title>{body}</svg>\n'


def _curve(segment):
    for i in range(41):
        t, u = i / 40, 1 - i / 40
        yield tuple(u**3 * segment[0][j] + 3*u*u*t*segment[1][j] +
                    3*u*t*t*segment[2][j] + t**3*segment[3][j] for j in (0, 1))


def render_icon(state="idle", *, size=64, surface="dark", foreground=None):
    """Opaque badge for contrast on light/dark panels; non-color state cues."""
    from PIL import Image, ImageDraw
    color = STATE_COLORS[state]
    if surface not in ("dark", "light", "green", "transparent"):
        raise ValueError(f"Unknown icon surface: {surface}")
    if surface == "light" and state == "idle":
        color = "#137D40"
    if surface == "green":
        color = "#FFFFFF"
    if foreground is not None:
        color = foreground
    scale = max(min(size * 4, 2048), 512) / 100
    image = Image.new("RGBA", (round(100*scale), round(100*scale)))
    draw = ImageDraw.Draw(image)
    def box(coords):
        return tuple(round(v*scale) for v in coords)
    if surface != "transparent":
        background = {"dark": DARK, "light": "#F4F8F5", "green": "#137D40"}[surface]
        draw.rounded_rectangle(box((1, 1, 99, 99)), radius=round(22*scale), fill=background)
    # Keep a little optical padding within the rounded-square app badge.
    def point(p):
        return ((p[0]*.88+6)*scale, (p[1]*.88+6)*scale)
    width = round(6*scale)
    points = [point(p) for segment in OUTLINE for p in _curve(segment)]
    draw.line(points, fill=color, width=width)
    # Round joins explicitly: Pillow's curved joint rasterization can leave
    # visible scallops along densely sampled cubic paths.
    for px, py in points:
        r = width / 2
        draw.ellipse((px-r, py-r, px+r, py+r), fill=color)
    for x, top, bottom in BARS:
        a, b = point((x, top)), point((x, bottom))
        draw.line((a, b), fill=color, width=width)
        for px, py in (a, b):
            r = width / 2
            draw.ellipse((px-r, py-r, px+r, py+r), fill=color)
    # At tray sizes a solid dot, three dots, and an exclamation remain distinct.
    if state != "idle":
        draw.ellipse(box((65, 65, 99, 99)), fill=(0, 0, 0, 0) if surface == "transparent" else DARK)
        if state == "recording":
            draw.ellipse(box((72, 72, 92, 92)), fill=color)
        elif state == "busy":
            for x in (71, 81, 91):
                draw.ellipse(box((x-3, 79, x+3, 85)), fill=color)
        elif state == "error":
            draw.rounded_rectangle(box((79, 70, 85, 83)), radius=round(3*scale), fill=color)
            draw.ellipse(box((79, 87, 85, 93)), fill=color)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def cutout_icon(state="idle", *, size=64, background="dark"):
    if background not in {"light", "dark"}:
        raise ValueError("Choose light or dark for the intended background")
    colors = {"idle": "#137D40", "recording": "#B83B35", "busy": "#00717D", "error": "#BD3024"}
    return render_icon(state, size=size, surface="transparent",
                       foreground=colors[state] if background == "light" else STATE_COLORS[state])


def mark_image(variant="green", size=64):
    return render_icon(size=size, surface="transparent", foreground=MARK_COLORS[variant])


def leaf_master(state="idle"):
    return render_icon(state, size=2048)


@lru_cache(maxsize=4)
def _cached_leaf_image(state):
    return render_icon(state)


def leaf_image(state="idle"):
    return _cached_leaf_image(state).copy()


@lru_cache(maxsize=21)
def _mascot_image(expression, size):
    from importlib.resources import files
    from PIL import Image
    if expression not in MASCOT_LABELS:
        raise ValueError(f"Unknown mascot expression: {expression}")
    asset = files("utterleaf").joinpath("assets", f"utterling-{expression}.png")
    with asset.open("rb") as stream, Image.open(stream) as source:
        return source.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


def mascot_image(expression="default", size=104):
    """Load bundled illustration once; never depend on the repository's docs."""
    return _mascot_image(expression, size).copy()
