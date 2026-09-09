# Platform testing

## Current validation — September 9, 2026

Version 0.3.5 local validation: Windows **328 passed, 1 skipped**;
AlmaLinux/WSL **327 passed, 2 skipped**, plus CLI help. Regression checks cover
excluding X11 paste fallback on Wayland, retaining clipboard text after failed
helpers, refusing stale XWayland focus information, cross-process Settings reuse,
crash lock recovery, and staged default restoration including advanced settings.
The Help screen was captured from real Windows Tk widgets and visually reviewed.
Native compositor delivery
is still unverified; see [Wayland setup and troubleshooting](wayland.md).

Local results for the v0.3.4 microphone-recovery changes:

| Environment | Result | Scope |
| --- | --- | --- |
| Windows, Python 3.14 | 319 passed, 1 skipped | Full suite, including real Tk widgets and a test-owned native Edit control. Windows symlink privilege limitation is the skip. |
| AlmaLinux 10, WSL2, Python 3.12.12, WSLg | 318 passed, 2 skipped; CLI help passed | Full suite; the two Windows-native checks are skipped. |
| Windows default microphone | Two simultaneous streams active at 48 kHz | Both streams closed after a brief test; samples discarded. Does not test every calling app, exclusive access, hotplug, or device loss. |

Published release validation is recorded in [GitHub Actions](https://github.com/RioPlay/utterleaf/actions/workflows/build.yml).
The release workflow tests and builds Windows, macOS, and Linux on native runners;
publication is gated on all five jobs. The Linux package also runs extracted-app
startup and IPC checks under Xvfb with X11 and Wayland session selection. This is
not a real Wayland compositor, microphone, or external-editor test.

macOS microphone permission, Accessibility, and real-app paste still need human
validation. Source test success and frozen CLI success do not substitute for it.
The older research and review documents retain their dated results as historical
snapshots; this page records the current validation scope.

### Local Linux environment

WSL reported a mirrored-network initialization error and fell back to no network.
Python dependencies were downloaded through Windows into `artifacts/linux-wheels`
and installed in `/tmp/utterleaf-test-venv`. Missing native libraries were downloaded
from AlmaLinux and an EPEL mirror and unpacked into `/tmp/utterleaf-native`.
No WSL network settings or system packages were changed.

The local launcher sets library, Python, Tcl/Tk, and fontconfig paths for that
temporary tree. Because its PortAudio library is outside the system linker cache,
the test launcher resolves that one library to its actual temporary path. It loads
real PortAudio; it does not substitute a fake audio library. The tests themselves
mock recording. This setup validates source behavior, not a clean Linux install.

Local rerun after this preparation:

```powershell
.\.venv\Scripts\python.exe -m pytest -rs
wsl -d AlmaLinux-10 -- bash /mnt/c/Users/unknown/Projects/Mindict/artifacts/run_linux_tests.sh
```

The temporary dependencies and ignored launcher are machine-specific. For normal
Linux/macOS preparation, use the source-install instructions in the README or the
checked-in `.github/workflows/build.yml`.

## Real-device checklist, including friends testing on macOS

Use the exact build intended for release and a scratch document with harmless test
text. Record the app version/commit, OS version, CPU/architecture, microphone,
model, and processing device. On Linux also record the desktop and X11/Wayland
session. Record actual results and mark anything not attempted as untested.

1. **Launch and setup:** extract the whole distribution, launch it, and complete
   first-run setup. Record any launch/security prompt verbatim. Settings should
   remain responsive while the model loads. Run `utterleaf --doctor` (Windows:
   `utterleaf-cli.exe --doctor`) and retain the report for diagnosis.
2. **Permissions:** on macOS exercise Microphone and Accessibility access. Test
   denial first, then enable access through System Settings and retry, restarting
   Utterleaf if needed. Report what happens; this checklist does not assume
   automatic permission recovery already works.
3. **Basic dictation:** speak ten short sentences in a native editor and browser
   field. On macOS use TextEdit, Safari, and optionally Chrome. Include a name,
   number, punctuation, and non-English text if relevant. Record recognition
   errors separately from text that failed to arrive.
4. **Recording controls:** test hold and toggle modes, Esc cancellation, a pause,
   silence, and two quick successive takes. Listening feedback should agree with
   microphone activity. No text should arrive from a cancelled take.
5. **Focus and delivery:** start in a scratch field, then switch apps while decoding.
   Verify it does not automatically type into the new app. Recover through
   **Copy last dictation**. Also try changing fields inside one app and record the
   behavior; same-window targeting remains a known limitation.
6. **Clipboard:** begin with a harmless plain-text copy, dictate, and inspect the
   clipboard afterward. Repeat while making a new copy during decoding. Report
   any unexpected replacement. Rich text/images remain a separate unresolved
   preservation requirement.
7. **Text control and recovery:** disable **Clean up dictated text**, say “scratch
   that,” and confirm it is treated as transcript text. Verify recent-text copying,
   explicit forgetting, and expiry after two minutes without another dictation.
8. **Offline and devices:** after weights are installed, disconnect networking,
   relaunch, and dictate. Unplug/reconnect the mic or change the input device and
   report whether recovery is understandable. Restore the normal device afterward.
9. **Accessibility and lifecycle:** navigate settings by keyboard, try large display
   scaling, and use VoiceOver on macOS if available. Quit and confirm the process
   and microphone activity end. If testing start-at-login, restore the preference
   afterward.

Suggested report format:

```text
Build / OS / CPU / microphone / model / device:
Editor and version:
Checklist item:
Steps:
Expected:
Actual:
Frequency (for example, 2 of 10):
```

Do not call a platform release-ready from unit-test counts alone. Live microphone
accuracy/latency, external-app insertion, permission prompts, packaging, tray
integration, and screen-reader behavior still need the real-device checks above.
WSLg cannot substitute for native GNOME/KDE and different Wayland compositors.
