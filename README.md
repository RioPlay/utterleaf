# Utterleaf

Hold a hotkey, speak, release. Clean text lands in whatever app is focused.

A small speech model runs on your machine. GPU if you have one, otherwise CPU. First launch downloads the selected speech model once. After that Utterleaf stays offline. No account. Speech stays on the device.

**Windows, macOS, and Linux.** Same app. Each OS gets a default hotkey that does not fight the desktop, a status pill, and start-at-login. `--doctor` prints what this machine can actually do.

## Use it

Utterleaf lives in the system tray (a teal mic). There is no main window.

1. Hold the hotkey, talk, release. Default is **Ctrl+Win** on Windows, **Ctrl+Shift+Space** on macOS and Linux.
2. A pill says **Listening**, then **Transcribing**.
3. The sentence lands in the app you were already in. Esc cancels a take.

Click the tray icon (or right-click → **Settings…**) to open the Utterleaf control center. First launch opens it automatically.

- **Dictation:** choose your shortcut, hold or press mode, microphone, recording feedback, and start at login. A five-second microphone check shows input levels without saving audio.
- **Vocabulary:** add names and custom terms, choose text cleanup options, and preview the result on a sample before saving.
- **Voice commands:** browse the built-in editing and punctuation commands.
- **Engine:** choose a model, processing device, language, noise reduction, and clipboard behavior. Missing model downloads can be disabled.
- **Help & diagnostics:** check whether the app is running, generate a device report, and save it wherever you choose.

The window resizes and scrolls, with Save always accessible. **Ctrl+S** (or **Command+S** on macOS) saves without closing; closing with unsaved changes asks before discarding them. Device checks run in the background.

On **Wayland**, Utterleaf disables global key listening. Bind a desktop shortcut to the absolute path of the executable followed by `--toggle`, for example `/home/you/Utterleaf/utterleaf --toggle`. Press once to record and again to transcribe. XWayland and a working `DISPLAY` are required for the current Tk/Xorg components. Install `wl-clipboard` and a compatible paste helper (`wtype` on supported compositors, or a configured `ydotool`); support varies by compositor. The shortcut must point to the same executable you launched.

On **macOS**, grant Microphone and Accessibility when asked. Without Accessibility, the hotkey and the paste both do nothing.

## Install

The public binary release targets Windows 11 x64. You need a microphone and internet for the first model download; an NVIDIA GPU is optional. Extract the entire release zip, then open `Utterleaf\utterleaf.exe`. Keep the `_internal` folder beside the executables. Python is not needed for the binary release.

From PowerShell in the extracted `Utterleaf` folder:

```powershell
.\utterleaf-cli.exe --doctor
.\utterleaf-cli.exe --download-model
```

For source installs below, use [Python 3.10+](https://www.python.org/downloads/). The Windows release is built and tested with Python 3.14; macOS/Linux instructions are source-install paths.

### Windows

```powershell
cd Utterleaf  # your cloned repository
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
Start-Process ".\.venv\Scripts\pythonw.exe" -ArgumentList "-m","utterleaf"
```

NVIDIA GPU (driver alone is not enough):

```powershell
.\.venv\Scripts\python -m pip install -e ".[cuda]"
```

For a packaged Windows build, open `utterleaf.exe` (or the compatibility entry `utterleafw.exe`). Both are windowless. `utterleaf-cli.exe` is only for terminal diagnostics. When developing from Python, use `pythonw.exe` for normal app launches; the `utterleaf` terminal command is for debugging.

### macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m utterleaf
```

Use a Python build with Tk support. Current python.org macOS installers include it; Homebrew Python needs the matching `python-tk` package (for example `python-tk@3.14`). Grant Microphone and Accessibility the first time you record.

### Linux

Needs PortAudio and a paste helper (`wtype`, `xdotool`, or `ydotool`). Sounds use `paplay`, `aplay`, or `play`.

```bash
# Debian/Ubuntu
sudo apt install python3-venv portaudio19-dev python3-tk wtype wl-clipboard xclip xdotool
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m utterleaf
```

On Wayland use `wtype` with `wl-clipboard`. On X11 use `xdotool` with `xclip` for clipboard access. The tray icon uses StatusNotifierItem: KDE Plasma shows it natively, GNOME needs the AppIndicator extension. Source installs also need PyGObject and the Ayatana appindicator bindings (`sudo apt install gir1.2-ayatanaappindicator3-0.1` on Debian/Ubuntu); without them the tray falls back to the legacy X11 icon, which Wayland sessions do not display. `utterleaf --doctor` prints the backend it picked. NVIDIA:

```bash
.venv/bin/python -m pip install -e ".[cuda]"
```

First launch downloads Whisper `small.en` into the app data folder (~500 MB). The pill says **Downloading the speech model (~500 MB)…**. After that it is offline.

- Windows: `%APPDATA%\Utterleaf\models`
- macOS: `~/Library/Application Support/Utterleaf/models`
- Linux: `~/.config/utterleaf/models`

`utterleaf --doctor` prints the mic list, paste helper, pill backend, model cache, and what hardware it would pick.

Start at login is off until you enable it in Settings.

## Commands

These also appear in Settings so you do not need this table to start.

| You say | What happens |
|---|---|
| `scratch that` | Discard this take (or undo the last paste if said alone) |
| `new paragraph` / `new line` | Insert a break |
| `make this shorter` | Drop hedges, keep the point |
| `make it more professional` | Expand slang/contractions, tighten |
| `make a list of …` | Turn the take into bullets |

You can say **“make a bulleted list one two three”** in a longer take. Utterleaf also recognizes “bullet list” and the common transcription “bolded list.” Digits such as `1 2 3` become separate items. For longer lists, say **“end list”** before returning to prose, for example: “Make a bulleted list first open the ticket second assign it end list That is all.”

If you only say an editing command, Utterleaf can undo and reapply the last paste. Use it within 20 seconds, in the same window and text field; switching windows prevents the edit.

## Names

In Settings, one line per name:

```
utter leaf = Utterleaf
```

## Config

Created on first run. Everyday use is Settings. The toml is for people who want a model or device override.

- Windows: `%APPDATA%\Utterleaf\config.toml`
- macOS: `~/Library/Application Support/Utterleaf/config.toml`
- Linux: `~/.config/utterleaf/config.toml`

```toml
hotkey = "ctrl+win"     # macOS/Linux default is "ctrl+shift+space"
mode = "hold"           # hold | toggle
model = "small"         # tiny, base, small, distil-small.en
device = "auto"         # auto | gpu | cpu
language = "en"
microphone = ""         # empty = system default
```

Polish is local rules. There is no cloud path.

Start at login: Windows Startup folder, macOS LaunchAgent, Linux `~/.config/autostart`.

## Not in v1

- iOS / Android
- Auto-learning vocabulary
- A focus-stealing overlay
- Apple GPU (Metal/CoreML) — Mac runs the local model on CPU for now

## Dev

The interface uses native Tk widgets with no web runtime. UI tests use sample settings and mocked devices. On headless Linux, run the UI tests under a virtual display (such as Xvfb).

For visual review on Windows: `python tests/capture_settings.py` writes screenshots to `artifacts/screenshots` without recording audio or changing personal settings.

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\utterleaf --polish "um I think we should, uh, ship it"
```

```bash
.venv/bin/python -m pytest
.venv/bin/python -m utterleaf --polish "um I think we should, uh, ship it"
```

## Package as a binary

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

CI (`.github/workflows/build.yml`) uses Python 3.14 and a `.venv`, runs pytest, then calls the same build script for a Windows CPU build on pull requests, pushes to main, and `v*` tags. The CUDA release is prepared locally with the CUDA flag above. Separate CI jobs test source installs on macOS (Homebrew Python 3.14 with Tk) and Linux (Ubuntu 24.04 system Python with Xvfb). Those jobs do not produce native release bundles. CI uploads the Windows build artifact; it does not publish a GitHub Release. Signing is a manual pre-publish step.

## Screenshot

![Utterleaf dictation settings](docs/screenshots/dictation.png)

## License and notices

Utterleaf is [Apache-2.0-licensed](LICENSE), copyright 2026 RioPlay; see [NOTICE](NOTICE) for attribution. Binary distributions include `LICENSE`, `NOTICE`, `THIRD-PARTY-NOTICES.md`, and the third-party license texts in `licenses/`. Dependencies retain their own licenses.

PyAV/FFmpeg is deliberately not bundled: dictation sends microphone PCM arrays directly to faster-whisper, so file decoding is unnecessary. An import-only PyAV stub keeps FFmpeg and its GPL codec payload out of the distribution. Model weights download at runtime and are not included in this repository.
## Platform verification

The shared dictation cleanup and platform branches have regression tests. Windows has local native pill and frozen-build checks. macOS and Linux have best-effort source review and CI jobs configured; real microphone, permissions, tray, hotkey, and paste checks on those desktops are still required. The Tk status window on macOS/Linux has a simpler rectangular outline, with captions wrapped to fit.

On Linux, X11 prefers `xdotool`; Wayland prefers `wtype`, with `ydotool` as a fallback when configured. The current pynput backend also needs XWayland and a working `DISPLAY` on Wayland; pure Wayland without that backend is not verified. [pynput documents these limits](https://pynput.readthedocs.io/en/latest/limitations.html). Wayland compositor support varies: use the desktop shortcut described above, and confirm paste with `--doctor` and a test field. On macOS, the source app uses the main thread for its tray and a separate process for Tk settings/indicator windows.
