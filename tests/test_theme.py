from utterleaf.theme import ON_PRIMARY, PRIMARY, SURFACE, apply


def test_primary_is_teal() -> None:
    assert PRIMARY.lower() == "#0f766e"
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
