from utterleaf.theme import ON_PRIMARY, PRIMARY, SURFACE, apply, leaf_image, leaf_master


def test_primary_is_leaf_green() -> None:
    assert PRIMARY.lower() == "#137d40"
    assert ON_PRIMARY == "#FFFFFF"
    assert SURFACE.startswith("#")


def test_apply_theme_configures_root(monkeypatch) -> None:
    class FakeStyle:
        def __init__(self, _root) -> None:
            self.theme = ""
            self.names: list[str] = []

        def theme_use(self, name: str) -> None:
            self.theme = name

        def configure(self, name, **_kwargs) -> None:
            self.names.append(name)

        def map(self, _name, **_kwargs) -> None:
            pass

    class FakeRoot:
        def __init__(self) -> None:
            self.bg = ""
            self.options: list[tuple] = []
            self.tk = self

        def configure(self, **kwargs) -> None:
            self.bg = kwargs.get("bg", self.bg)

        def option_add(self, *args) -> None:
            self.options.append(args)

        def call(self, *args):
            return None

    import utterleaf.theme as theme

    monkeypatch.setattr("tkinter.ttk.Style", FakeStyle)
    root = FakeRoot()
    apply(root)
    assert root.bg == SURFACE
    fonts = [opt[1] for opt in root.options if opt[0] == "*Text.Font"]
    assert fonts
    assert fonts[0][0]  # family from this OS, not a missing tuple


def test_leaf_waveform_and_states_are_distinct_without_color(monkeypatch) -> None:
    from utterleaf.brand import STATE_COLORS, render_icon
    master = leaf_master()
    assert master.size == (2048, 2048)
    assert master.mode == "RGBA"
    assert master.getpixel((0, 0))[3] == 0
    assert all(leaf_image(s).size == (64, 64) for s in STATE_COLORS)
    for state in STATE_COLORS:
        monkeypatch.setitem(STATE_COLORS, state, "#FFFFFF")
    for size in (16, 24, 32, 64):
        images = [render_icon(state, size=size) for state in STATE_COLORS]
        assert all(im.size == (size, size) for im in images)
        # Shape cues survive monochrome conversion as well as color changes.
        assert len({im.convert("L").tobytes() for im in images}) == 4


def test_warm_tray_updates_do_not_render_and_images_are_independent(monkeypatch):
    import utterleaf.brand as brand
    import pytest
    original = leaf_image("idle")
    monkeypatch.setattr(brand, "render_icon", lambda *args: pytest.fail("Hotkey path must not render"))
    first = leaf_image("idle")
    first.putpixel((0, 0), (255, 0, 0, 255))
    assert leaf_image("idle").tobytes() == original.tobytes()
