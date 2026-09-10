# Install Utterleaf

[Back to Utterleaf](../README.md) · [User guide](user-guide.md)

<img src="assets/brand/utterling-default.png" width="80" alt="Utterling welcoming you to setup" />

Binary releases are built for Windows 11 x64, macOS (Apple Silicon), and Linux x64 (Ubuntu 24.04 or compatible). You need a microphone and internet for the first model download; an NVIDIA GPU is optional. Extract the entire release archive, then open `Utterleaf\utterleaf.exe` on Windows or `./Utterleaf/utterleaf` on macOS/Linux. Keep the `_internal` folder beside the executables. Python is not needed for the binary release.

From PowerShell in the extracted `Utterleaf` folder:

```powershell
.\utterleaf-cli.exe --doctor
.\utterleaf-cli.exe --download-model
```

For source installs below, use [Python 3.10+](https://www.python.org/downloads/). CI uses Python 3.14 on Windows/macOS and Ubuntu's system Python on Linux; the instructions below are for source installs.

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

For GPU use in the **packaged Windows release**, open **Settings ? Help ? Set up
NVIDIA GPU?**, or run `./utterleaf-cli.exe --cuda-setup` from its extracted folder.
The standard archive works on CPU without the optional NVIDIA math libraries.
Its CTranslate2 runtime needs compatible CUDA 12.x and cuDNN 9 for CUDA 12:
use the [CUDA 12.9 archive](https://developer.nvidia.com/cuda-12-9-0-download-archive)
and [NVIDIA's Windows cuDNN instructions](https://docs.nvidia.com/deeplearning/cudnn/installation/latest/windows.html).
Follow the Windows DLL/PATH setup, restart Utterleaf and check the diagnostic, then
try a dictation. A detected card or a loaded cuBLAS DLL alone does not prove that
cuDNN and model inference work. Installing packages in another Python environment
does not modify the packaged app.

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

Wayland requires desktop-specific setup; see the [Wayland troubleshooting guide](wayland.md). Installing `wtype` alone does not guarantee paste support. On X11 use `xdotool` with `xclip` for clipboard access. The tray icon uses StatusNotifierItem: KDE Plasma shows it natively, GNOME needs the AppIndicator extension. Source installs also need PyGObject and the Ayatana appindicator bindings (`sudo apt install gir1.2-ayatanaappindicator3-0.1` on Debian/Ubuntu); without them the tray falls back to the legacy X11 icon, which Wayland sessions do not display. `utterleaf --doctor` prints the backend it picked. NVIDIA:

```bash
.venv/bin/python -m pip install -e ".[cuda]"
```

A binary release on Linux uses the distro's NVIDIA toolkit instead: install `cuda` and `cudnn` for your distribution (Arch: `sudo pacman -S cuda cudnn`), or produce a self-contained CUDA build with `UTTERLEAF_BUNDLE_CUDA=1`.

Don't know the exact command for your distro? Run `utterleaf --cuda-setup` (or open **Settings → Help → Set up NVIDIA GPU…**) for steps matched to this machine, or run the helper script `scripts/cuda-setup.sh` from the repo, which detects the package manager and installs CUDA for you.

First launch downloads Whisper `small.en` into the app data folder (~500 MB). The tray shows loading status; the optional overlay also explains the download. After that recognition works offline.

- Windows: `%APPDATA%\Utterleaf\models`
- macOS: `~/Library/Application Support/Utterleaf/models`
- Linux: `~/.config/utterleaf/models`

`utterleaf --doctor` prints the mic list, paste helper, pill backend, model cache, and what hardware it would pick.

Start at login is off until you enable it in Settings.

For a one-key workflow, choose **F8** and **Press to start / stop** in Dictation
settings. Esc stays reserved for cancelling, so it cannot be assigned as the
recording shortcut.
