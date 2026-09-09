# Platform testing

## Latest local results — September 8, 2026

These results cover the working tree, including the current uncommitted changes.

| Environment | Result | Scope |
| --- | --- | --- |
| Windows, Python 3.14 | 296 passed, 1 skipped; CLI help passed | Full automated suite, real Tk widgets and test-owned native Edit control. Linux symlink test skipped because Windows lacks the required privilege. |
| AlmaLinux 10, WSL2, Python 3.12.12, WSLg | 295 passed, 2 skipped in each session-selection run; CLI help passed | Full automated suite including Tk under WSLg, with Wayland detection and then explicit X11 selection. Only two Windows-native tests skipped. |
| macOS | Current working tree not yet run natively | Existing CI runs native macOS tests and builds. Local tests exercise AppleScript dispatch and return codes using mocks; they do not validate macOS permissions. |

Windows results: `artifacts/windows-tests.xml`. Linux results:
`artifacts/linux-tests.xml` (latest X11-selection run). These local artifacts are ignored by Git.

The [latest baseline CI run](https://github.com/RioPlay/utterleaf/actions/runs/34275651113)
passed Windows, Linux, and macOS tests/builds for commit
`8e2b30e765a8672283c13489f987f9e426e733f8`. It does not include the uncommitted
improvements. The existing build workflow will validate the next pushed revision;
no new remote run or release was triggered during this pass.

The WSL run found an environment-dependent test: recording hints assumed a
non-Wayland session. The test now explicitly covers both global-hotkey and
Wayland desktop-shortcut hints. CI also has a second Linux suite run with Wayland
session selection. That run uses Xvfb for rendering; it is not a Wayland compositor
integration test.

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
