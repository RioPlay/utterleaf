"""Desktop and Android stay isolated. See docs/development-boundaries.md."""

from pathlib import Path
import os
import re
import pytest
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
GUIDE = "See docs/development-boundaries.md."
_ANDROID_FROM_DESKTOP = re.compile(
    r"(?:^|\n)\s*(?:from|import)\s+mobile\b|org\.utterleaf\.voice",
    re.IGNORECASE,
)
_DESKTOP_FROM_ANDROID = re.compile(r"(?:^|\n)\s*(?:from|import)\s+utterleaf\b")


def _android_source_paths(root):
    # Build outputs include fetched upstream examples and can be locked by Gradle.
    # Prune before descending; source read failures must still fail the check.
    generated = {".gradle", ".cxx", ".externalNativeBuild", "__pycache__", ".git"}
    def fail(error):
        raise error
    for folder, directories, files in os.walk(root, onerror=fail):
        in_source = bool({"src", "tools"}.intersection(Path(folder).relative_to(root).parts))
        directories[:] = [name for name in directories
                          if name not in generated and (name != "build" or in_source)]
        for name in files:
            path = Path(folder) / name
            if path.suffix.lower() in {".kt", ".java", ".py"}:
                yield path


def test_desktop_package_discovery_is_utterleaf_only():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = data["tool"]["setuptools"]["packages"]["find"]["include"]
    assert include == ["utterleaf*"], (
        "Desktop package discovery must include only utterleaf*, not mobile/. " + GUIDE
    )
    paths = data["tool"]["pytest"]["ini_options"]["testpaths"]
    assert paths == ["tests"], (
        "Desktop pytest must collect tests/, not mobile/android. " + GUIDE
    )


def test_desktop_python_does_not_import_android():
    hits = []
    for folder in (ROOT / "utterleaf", ROOT / "tests", ROOT / "packaging"):
        for path in folder.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if _ANDROID_FROM_DESKTOP.search(text):
                hits.append(str(path.relative_to(ROOT)))
    assert hits == [], (
        "Desktop code imported Android packages. Move the dependency behind a "
        "desktop module or keep it in mobile/android. " + GUIDE + " Files: "
        + ", ".join(hits)
    )


def test_android_sources_do_not_import_desktop_python():
    hits = []
    root = ROOT / "mobile" / "android"
    if not root.is_dir():
        return
    for path in _android_source_paths(root):
        text = path.read_text(encoding="utf-8")
        if _DESKTOP_FROM_ANDROID.search(text):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == [], (
        "Android code imported the desktop utterleaf package. Keep Gradle and "
        "Python dependencies separate. " + GUIDE + " Files: " + ", ".join(hits)
    )


def test_android_boundary_ignores_generated_dependencies_but_checks_source(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    android = tmp_path / "mobile" / "android"
    for relative in ("app/.cxx/debug/dependency/Example.java", "app/build/generated/Example.kt"):
        generated = android / relative
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("import utterleaf.forbidden", encoding="utf-8")
    test_android_sources_do_not_import_desktop_python()
    source = android / "app" / "src" / "main" / "build" / "Example.kt"
    source.parent.mkdir(parents=True)
    source.write_text("import utterleaf.forbidden", encoding="utf-8")
    with pytest.raises(AssertionError, match="Android code imported"):
        test_android_sources_do_not_import_desktop_python()
