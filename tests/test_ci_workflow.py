from pathlib import Path
from types import SimpleNamespace

import conftest
import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.ui
class TestDisplayOptIn:
    def test_ui_marker_requires_explicit_permission(self, request) -> None:
        # Harmless sentinel: exercise real inherited marker collection without
        # opening a window, even if the selection safeguard regresses.
        assert request.config.getoption("--run-ui")


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

    pytest_invocations = [line for line in pr_gate.splitlines() if "pytest" in line]
    assert pytest_invocations, "PR gate must retain its focused pytest coverage"
    for invocation in pytest_invocations:
        assert "--run-ui" not in invocation
        assert '"not ui' in invocation, invocation
    assert "capture_settings.py" not in pr_gate
    assert "capture_visual.py" not in pr_gate

    full_invocations = [line for line in full_suite.splitlines() if "pytest" in line]
    assert full_invocations, "main branch must retain its full pytest suite"
    for invocation in full_invocations:
        assert "--run-ui" in invocation
        assert '-m "not integration"' in invocation


def test_default_pytest_run_is_headless_and_has_an_explicit_opt_in() -> None:
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'addopts = "-q"' in config
    assert "addopts = \"-q -m" not in config

    hook_source = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'config.getoption("--run-ui")' in hook_source
    assert '"ui" in item.keywords' in hook_source


def test_collection_guard_deselects_ui_items_without_opt_in() -> None:
    ui = SimpleNamespace(keywords={"ui": True})
    ordinary = SimpleNamespace(keywords={})
    deselected = []
    config = SimpleNamespace(
        getoption=lambda _name: False,
        hook=SimpleNamespace(pytest_deselected=lambda *, items: deselected.extend(items)),
    )
    items = [ui, ordinary]

    conftest.pytest_collection_modifyitems(config, items)

    assert items == [ordinary]
    assert deselected == [ui]


def test_collection_guard_keeps_ui_items_with_opt_in() -> None:
    ui = SimpleNamespace(keywords={"ui": True})
    ordinary = SimpleNamespace(keywords={})
    config = SimpleNamespace(getoption=lambda _name: True)
    items = [ui, ordinary]

    conftest.pytest_collection_modifyitems(config, items)

    assert items == [ui, ordinary]


def test_windows_preview_explicitly_runs_the_display_suite() -> None:
    workflow = (ROOT / ".github" / "workflows" / "desktop-preview.yml").read_text(encoding="utf-8")

    assert "[sys.executable,'-m','pytest','--run-ui','-q','-ra','--junitxml=preview-evidence/pytest.xml']" in workflow


def test_release_publisher_requires_the_current_successful_main_build() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-release.yml").read_text(encoding="utf-8")
    build = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")

    assert "tag_sha=$(git rev-parse \"refs/tags/$RELEASE_TAG^{commit}\")" in workflow
    assert "gh api \"repos/$GH_REPO/actions/runs/$BUILD_RUN\" > run.json" in workflow
    assert '.head_sha == $tag_sha' in workflow
    assert '.path == ".github/workflows/build.yml"' in workflow
    assert '.status == "completed"' in workflow
    assert '.conclusion == "success"' in workflow
    assert '.event == "push"' in workflow
    assert '.head_branch == "main"' in workflow

    operating_systems = ("windows-latest", "ubuntu-24.04", "macos-latest")
    full_suite = build.split("  full-suite:", 1)[1].split("\n  installers:", 1)[0]
    installers = build.split("  installers:", 1)[1]
    for operating_system in operating_systems:
        assert f"os: {operating_system}" in full_suite
    assert "os: [windows-latest, macos-latest, ubuntu-24.04]" in installers
    for job_group in ("full-suite", "installers"):
        assert f"name: {job_group} (${{{{ matrix.os }}}})" in build
        for operating_system in operating_systems:
            job = f"{job_group} ({operating_system})"
            assert f'"{job}"' in workflow
    for stale_job in ("macos-build", "linux-build", "macos-tests", "linux-tests"):
        assert stale_job not in workflow
    assert "z.testzip() is None" in workflow
    assert "tar -tzf Utterleaf-macos-arm64.tar.gz" in workflow
    assert "tar -tzf Utterleaf-linux-x64.tar.gz" in workflow
