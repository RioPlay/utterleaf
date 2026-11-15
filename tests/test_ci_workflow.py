from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_runs_the_frozen_smoke_before_upload() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    installers = workflow.split("  installers:", 1)[1]

    assert "packaging\\build.ps1" in installers
    assert "actions/upload-artifact@v4" in installers
    assert "tests\\smoke_release.py dist\\Utterleaf" in installers
    assert "continue-on-error: true" not in installers


def test_desktop_workflow_keeps_platform_isolation_and_bounded_jobs() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    assert "- 'mobile/**'" in workflow
    assert "- 'docs/android*.md'" in workflow
    assert workflow.count("\n  pr-gate:") == 1
    assert workflow.count("\n  full-suite:") == 1
    assert workflow.count("\n  installers:") == 1

    pr_gate = workflow.split("  pr-gate:", 1)[1].split("\n  full-suite:", 1)[0]
    full_suite = workflow.split("  full-suite:", 1)[1].split("\n  installers:", 1)[0]

    # The pull request gate stays headless and never renders screenshot frames.
    assert "-m \"not ui and not slow and not integration\" -q" in pr_gate
    assert "capture_settings.py" not in pr_gate
    assert "capture_visual.py" not in pr_gate

    # Display tests run on main, not on every pull request.
    assert "-m \"not integration\"" in full_suite
    assert "not ui" not in full_suite


def test_default_pytest_run_is_headless() -> None:
    """A plain `pytest` must not open display windows, so ui tests are deselected."""
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "addopts" in config
    assert "not ui" in config

    marked = []
    for path in (ROOT / "tests").glob("test_*.py"):
        source = path.read_text(encoding="utf-8")
        if "pytest.mark.ui" in source:
            marked.append(path.name)
    # The display-dependent modules carry the marker, so the filter is load-bearing
    # rather than a no-op guard that silently selects everything.
    assert len(marked) >= 20, f"only {len(marked)} modules marked ui: {sorted(marked)}"
