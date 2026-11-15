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
    assert "-m \"not slow and not integration\" -q" in workflow
