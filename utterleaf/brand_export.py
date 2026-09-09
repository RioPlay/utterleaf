"""One asset catalog for repository exports and the in-app ZIP download."""
from functools import lru_cache
from importlib.resources import files
from io import BytesIO
from pathlib import Path
import json
import os
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from . import brand

SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def wordmark_svg(inverse=False):
    ink = "#FFFFFF" if inverse else brand.DARK
    green = "#FFFFFF" if inverse else "#137D40"
    muted = "#FFFFFF" if inverse else "#526671"
    body = brand.mark_svg(green) + f'<text x="110" y="65" font-family="Segoe UI,Arial,sans-serif" font-size="56" font-weight="700" fill="{ink}">utter<tspan fill="{green}">leaf</tspan></text><text x="113" y="90" font-family="Segoe UI,Arial,sans-serif" font-size="12" letter-spacing="4" fill="{muted}">LET IDEAS SPEAK</text>'
    return brand.svg_document(body, width=390, height=105)


@lru_cache(maxsize=4)
def wordmark_image(inverse=False, width=390):
    """Read the packaged PNG exported from the SVG, preserving real alpha."""
    from PIL import Image
    name = "wordmark-inverse.png" if inverse else "wordmark.png"
    with files("utterleaf").joinpath("assets", name).open("rb") as f, Image.open(f) as source:
        return source.convert("RGBA").resize((width, round(width*105/390)), Image.Resampling.LANCZOS)


def _png(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def asset_catalog():
    """Yield every documented asset, including the complete size variants."""
    for surface in ("dark", "light", "green"):
        for size in SIZES:
            yield f"app-{surface}-{size}.png", _png(brand.render_icon(surface=surface, size=size))
    for state in brand.STATE_COLORS:
        yield f"tray-{state}.png", _png(brand.leaf_image(state))
        for background in ("light", "dark"):
            for size in SIZES:
                yield f"cutout-{state}-for-{background}-{size}.png", _png(brand.cutout_icon(state, background=background, size=size))
    for variant, color in brand.MARK_COLORS.items():
        yield f"mark-{variant}.svg", brand.svg_document(brand.mark_svg(color)).encode()
        for size in SIZES:
            yield f"mark-{variant}-{size}.png", _png(brand.mark_image(variant, size))
    for inverse in (False, True):
        stem = "wordmark-inverse" if inverse else "wordmark"
        yield f"{stem}.svg", wordmark_svg(inverse).encode()
        yield f"{stem}.png", files("utterleaf").joinpath("assets", f"{stem}.png").read_bytes()
    for expression in brand.MASCOT_LABELS:
        name = f"utterling-{expression}.png"
        yield name, files("utterleaf").joinpath("assets", name).read_bytes()
    for format, name in (("ICO", "utterleaf.ico"), ("ICNS", "utterleaf.icns")):
        buffer = BytesIO()
        options = {"sizes": [(s, s) for s in SIZES if s <= 256]} if format == "ICO" else {}
        brand.render_icon(size=1024).save(buffer, format=format, **options)
        yield name, buffer.getvalue()
    manifest = {"sizes": SIZES, "states": brand.STATE_LABELS, "mascots": brand.MASCOT_LABELS,
                "alpha": "PNG files are RGBA. Badge fills and the speech balloon interior are intentional. Cutout marks and mascots have transparent backgrounds.",
                "usage": "Choose for-light cutouts on light backgrounds and for-dark on dark backgrounds. Use inverse white marks and wordmark on dark backgrounds. Preview all assets in Help > Icons & artwork. Offline is Ready; speaking and typing mascots are illustrations, not app capabilities."}
    yield "usage.json", json.dumps(manifest, indent=2).encode()


def export_pack(destination):
    """Write atomically so a failed export cannot replace an existing archive."""
    destination = Path(destination)
    handle, temporary = tempfile.mkstemp(prefix=".utterleaf-artwork-", suffix=".zip", dir=destination.parent)
    os.close(handle)
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            for name, data in asset_catalog():
                archive.writestr(name, data)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
