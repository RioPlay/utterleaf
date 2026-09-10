# Developing Utterleaf

[Back to Utterleaf](../README.md) · [Source installation](installation.md)

This guide covers desktop development. Android has its own [build guide](../mobile/android/README.md).
See [development boundaries](development-boundaries.md) for source ownership,
independent dependencies, CI routing and release conventions.

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
and the --pill subprocess are all frozen-aware. Sign the exes (signtool) before
shipping — unsigned builds trip SmartScreen.

`packaging\build.ps1` is the canonical Windows build entry point. It runs PyInstaller, writes executable checksums, ships `README.md` at the top of the dist folder, and collects third-party notices; invoking PyInstaller directly skips those release steps. Install the development dependencies above before running it. The script installs PyInstaller if needed.

CI (`.github/workflows/build.yml`) runs pytest on Windows, macOS, and Linux, and builds native binaries for all three: the Windows CPU build via the same `packaging\build.ps1` script, and macOS/Linux bundles via the shared PyInstaller spec plus third-party notice collection. Pushes to `main` and pull requests run the full matrix except changes confined to mobile source, mobile guides, or Android CI. Only `v*` tags publish a desktop GitHub Release with all three archives. The CUDA release is prepared manually with the CUDA bundle flag. Signing is a manual pre-publish step.

## Platform verification

The shared dictation cleanup and platform branches have regression tests. Windows has local native pill and frozen-build checks. macOS and Linux have best-effort source review and CI jobs configured; real microphone, permissions, tray, hotkey, and paste checks on those desktops are still required. The Tk status window on macOS/Linux has a simpler rectangular outline, with captions wrapped to fit.

On Linux, X11 prefers `xdotool`; Wayland prefers `wtype`, with `ydotool` as a fallback when configured. The current pynput backend also needs XWayland and a working `DISPLAY` on Wayland; pure Wayland without that backend is not verified. [pynput documents these limits](https://pynput.readthedocs.io/en/latest/limitations.html). Wayland compositor support varies: use the desktop shortcut described above, and confirm paste with `--doctor` and a test field. On macOS, the source app uses the main thread for its tray and a separate process for Tk settings/indicator windows.
