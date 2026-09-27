from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_package_requires_full_frozen_release_smoke() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    windows = workflow.split("  linux-tests:", 1)[0]

    assert "- name: Frozen Windows release smoke test" in windows
    assert ".\\.venv\\Scripts\\python.exe tests\\smoke_release.py dist\\Utterleaf" in windows
    assert "continue-on-error: true" not in windows
