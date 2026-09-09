from io import BytesIO
from zipfile import ZipFile

import pytest
from PIL import Image

from utterleaf import brand, brand_export


def test_mascots_have_real_alpha_and_keep_eye_highlights():
    for expression in brand.MASCOT_LABELS:
        image = brand.mascot_image(expression, 256)
        assert image.mode == "RGBA"
        histogram = image.getchannel("A").histogram()
        assert histogram[0] > 256*256*.4
        assert histogram[255] > 256*256*.1
        assert sum(histogram[1:255]) > 0
        assert image.getpixel((0, 0))[3] == 0
    default = brand.mascot_image("default", 256)
    assert any(min(r, g, b) > 245 and a == 255 for r, g, b, a in (default.getpixel((x, y)) for y in range(256) for x in range(256))), "White eye glints must not become holes"


def test_cutouts_have_no_opaque_badge_and_suit_both_backgrounds():
    for state in brand.STATE_COLORS:
        light = brand.cutout_icon(state, size=64, background="light")
        dark = brand.cutout_icon(state, size=64, background="dark")
        assert light.tobytes() != dark.tobytes()
        assert light.getchannel("A").tobytes() == dark.getchannel("A").tobytes()
        assert light.getpixel((7, 32))[3] == 0
        assert brand.render_icon(state).getpixel((7, 32))[3] == 255


def test_export_pack_contains_complete_rgba_catalog(tmp_path):
    target = tmp_path / "artwork.zip"
    brand_export.export_pack(target)
    with ZipFile(target) as archive:
        names = set(archive.namelist())
        assert {"wordmark.svg", "wordmark.png", "wordmark-inverse.png", "utterleaf.ico", "utterleaf.icns", "usage.json"} <= names
        for expression in brand.MASCOT_LABELS:
            assert f"utterling-{expression}.png" in names
        for state in brand.STATE_COLORS:
            for background in ("light", "dark"):
                for size in brand_export.SIZES:
                    assert f"cutout-{state}-for-{background}-{size}.png" in names
        for name in names:
            if name.endswith(".png"):
                with Image.open(BytesIO(archive.read(name))) as image:
                    assert image.mode == "RGBA", name
                    assert image.getchannel("A").getextrema() == (0, 255), name


def test_failed_export_preserves_existing_archive(monkeypatch, tmp_path):
    target = tmp_path / "existing.zip"
    target.write_bytes(b"previous export")
    def broken():
        yield "first.txt", b"partial"
        raise OSError("Disk full")
    monkeypatch.setattr(brand_export, "asset_catalog", broken)
    with pytest.raises(OSError):
        brand_export.export_pack(target)
    assert target.read_bytes() == b"previous export"
    assert list(tmp_path.iterdir()) == [target]
