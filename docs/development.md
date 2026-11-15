# Developing Utterleaf

[Back to Utterleaf](../README.md) · [Source installation](installation.md)

This guide covers desktop development. Android has its own [build guide](../mobile/android/README.md).
See [development boundaries](development-boundaries.md) for source ownership,
independent dependencies, CI routing and release conventions.
Agents start from [AGENTS.md](../AGENTS.md); Aden is required when it is connected.

Use the [production-readiness standard](production-readiness.md) for proposed
reliability metrics, security gates and evidence required before stable releases.

When Aden CLI/MCP is available, use a scoped symbol tree, bounded search and
symbol understanding to locate callers and affected code before editing. Give
subagents the same navigation guidance and the relevant source ownership limits.
Verify returned anchors against source: heuristic or missing graph relationships
are not proof of behavior. Git history, actual source and tests remain the
authority for changes and validation.

## Local checks

The interface uses native Tk widgets with no web runtime. UI tests use sample settings and mocked devices. On headless Linux, run the UI tests under a virtual display (such as Xvfb).
Follow the [interface guidelines](interface.md) and [brand guide](branding.md)
when changing layout, copy, or artwork.

Settings, vocabulary, and login registration use atomic file replacement. If a
later save step fails, the error identifies what saved and what was not
attempted, and keeps your form entries for retry. The three steps are not a
single transaction.

For visual review on Windows: `python tests/capture_settings.py` writes screenshots to `artifacts/screenshots` without recording audio or changing personal settings.

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\utterleaf --polish "um I think we should, uh, ship it"
```

```bash
.venv/bin/python -m pytest
.venv/bin/python -m utterleaf --polish "um I think we should, uh, ship it"
```

## Build a binary

Windows (build and verify on a Windows box):

```powershell
.\packaging\build.ps1  # -> dist\Utterleaf\  (utterleaf.exe app, utterleaf-cli.exe diagnostics)
.\dist\Utterleaf\utterleaf-cli.exe --doctor
```

To bundle the installed CUDA libraries for NVIDIA acceleration, set `$env:UTTERLEAF_BUNDLE_CUDA = "1"` before building. This creates a substantially larger distribution; the default build omits these optional libraries. Verify the selected device with the packaged `--doctor` command.

`utterleafw.exe` is what start-at-login uses; `startup.py`, the settings relaunch,
and the --pill subprocess are all frozen-aware. Stable releases should sign the
executables before shipping. The published 0.4.6 RC4 Windows preview is an
unsigned exception and must disclose the resulting SmartScreen warning.

`packaging\build.ps1` is the canonical Windows build entry point. It runs PyInstaller, writes executable checksums, ships `README.md` at the top of the dist folder, and collects third-party notices; invoking PyInstaller directly skips those release steps. Install the development dependencies above before running it. The script installs PyInstaller if needed.

An existing reviewed build environment can be reused without copying it into the
checkout: `./packaging/build.ps1 -PythonPath $BuildPython`. Run from the owning
checkout, set `PYTHONPATH` to that checkout, and confirm the Python version and
dependency pins match the runtime manifest before building. Keep one output tree
and check volume headroom before each build or archive copy.

## CI and test budget

The desktop pull request gate has a five-minute job budget. It runs focused
headless security, capture, delivery, and settings checks on Windows and a Linux
X11-backed subset with a Wayland session value. It does not capture screenshots
or build installers. The `main` branch runs the full pytest suite, including UI
tests, on Windows, macOS, and Linux with a 15-minute budget per platform.
Installer builds and artifact uploads run only for `main` and `v*` tags. Desktop
path ignores continue to exclude mobile source and Android documentation.

The Windows desktop preview workflow runs the full pytest suite with the
explicit `--run-ui` opt-in before building its preview archive. Stable release
publication is manual and requires a completed successful `build.yml` run from
`main` at the exact commit tagged for release. Use that main run's ID: it must
contain all three successful full-suite jobs and all three successful installer
jobs. A tag-triggered build run alone is insufficient because it does not run
the full suite. The publisher also verifies the downloaded Windows, macOS, and
Linux archives before creating the release.

Android implementation, builds and releases are paused until its pipeline is
agreed. This desktop candidate retains the current-main Android workflow rather
than introducing a nightly emulator schedule or revised Android PR checks.
Deferred Android CI edits remain preserved locally; resume them in the owning
Android branch. The independent `android-release.yml` gates are unchanged.

Pytest markers describe test cost and environment:

- `ui`: exercises a desktop interface and may require Tk or a display.
- `native`: exercises an operating-system integration or native library.
- `slow`: intentionally long running and excluded from the pull request gate.
- `integration`: crosses module or process boundaries and is reserved for the
  full suite when it is not needed in the focused pull request gate.

## Running tests without opening windows

UI tests carry `pytest.mark.ui` and are deselected during collection by default.
This guard applies even when a command supplies its own `-m` expression, so
`pytest -m ui` and `pytest -m "not slow"` remain headless. To deliberately run
them, pass `--run-ui`:

- `pytest` runs the default headless suite.
- `pytest -m "not integration"` runs the non-integration headless suite.
- `pytest --run-ui -m ui` runs only UI tests.
- `pytest --run-ui -m "not integration"` includes UI tests in the selected suite.

The main-branch CI suite passes `--run-ui`; pull request pytest invocations do
not. This is a collection safeguard, not a substitute for a display on systems
that require one.

The capture harnesses are manual visual references, not behavior tests and not a
CI step. `tests/capture_settings.py` renders a number of frames to write
screenshots under `artifacts/screenshots`; it remains the documented Windows UI
check and never records microphone input. Run it by hand when you want to see the
surfaces. It is deliberately absent from the pull request gate because generating
images that no one reviews in CI is pure cost.

Security, privacy, capture-store, delivery, and settings behavior remain covered
by pytest.

Before change: **2,714 collected tests** across **108 test files**. The baseline
full-suite attempt took **17m48s**, but overlapped shared desktop UI activity
and workflow edits. It ended with five failures, so that timing is not a clean
comparison. The ten screenshot-harness assertion suites were removed.

After change: **2,607 collected tests** across **98 test files**. The full-suite
timing is pending a clean run after the shared desktop is available. A partial
post-change run was stopped at 82% when the shared-resource constraint arrived.

The count reduction is deliberately modest. The ten removed suites asserted on
the screenshot harnesses rather than on product behavior. The remaining tests
cover cleanup, audio, status encoding, delivery, settings, clipboard and the OBS
protocol, where security, privacy and capture-store behavior is asserted by
name. Trimming further would remove behavior coverage rather than repetition, so
the cost reduction comes from the pull request gate and the Android emulator
schedule rather than from a smaller total. Treat a target test count as a
symptom to measure first, not a quota to hit.

The CUDA release is prepared manually with the CUDA bundle flag. Signing is a
manual pre-publish step.

Windows preview tags use the separate `desktop-v*` namespace and a Windows-only
workflow. After the exact artifact and source revision are reviewed, publication
uses GitHub prerelease status with `latest=false`; it does not replace or relabel
the stable `v*` release. This exception does not change stable release automation.

## Platform verification

The shared dictation cleanup and platform branches have regression tests. Windows has local native pill and frozen-build checks. macOS and Linux have best-effort source review and CI jobs configured; real microphone, permissions, tray, hotkey, and paste checks on those desktops are still required. The Tk status window on macOS/Linux has a simpler rectangular outline, with captions wrapped to fit.

On Linux, X11 prefers `xdotool`; Wayland prefers `wtype`, with `ydotool` as a fallback when configured. The current pynput backend also needs XWayland and a working `DISPLAY` on Wayland; pure Wayland without that backend is not verified. [pynput documents these limits](https://pynput.readthedocs.io/en/latest/limitations.html). Wayland compositor support varies: use the desktop shortcut described above, and confirm paste with `--doctor` and a test field. On macOS, the source app uses the main thread for its tray and a separate process for Tk settings/indicator windows.
