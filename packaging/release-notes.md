**v0.3.8** protects your microphone choice and starts the privacy-first convenience roadmap. The speech engine and dependencies are unchanged.

- A missing selected microphone now blocks capture instead of silently opening the system default.
- Saved names must match exactly. If you previously entered a partial name manually, select the full name in Settings → Dictation and Save.
- Refresh devices preserves your selection and explains when it is unavailable or ready to test. System default remains an explicit choice.
- Updated roadmap milestones cover recovery, safe delivery, readiness, long dictation, speed choices, vocabulary, selective backup, and file transcription.

This does not yet add native hotplug refresh or recovery during a take. Some backends require restarting the app after reconnecting. Identical microphone names cannot distinguish physical devices.

Quit the older app before extracting and reopening the update. Local control authentication and the privacy-preserving defaults reset from v0.3.7 remain included.

## Download and open

| Computer | Archive | After extracting the whole archive |
| --- | --- | --- |
| Windows x64 | `Utterleaf-windows-x64-cpu.zip` | Open `Utterleaf/utterleaf.exe` |
| macOS Apple Silicon | `Utterleaf-macos-arm64.tar.gz` | Run `./Utterleaf/utterleaf` |
| Linux x64 (Ubuntu 24.04 or compatible) | `Utterleaf-linux-x64.tar.gz` | Run `./Utterleaf/utterleaf` |

Python is bundled. Keep `_internal` beside the executable. The selected speech
model downloads on first launch; recognition then runs locally. Model weights
and optional CUDA libraries are separate. `SHA256SUMS.txt` lists archive checksums.

## Platform setup

- **Windows:** Ctrl+Win is the default shortcut. GPU acceleration needs compatible CUDA libraries; the CPU build works without them.
- **macOS:** Apple Silicon only, with CPU inference. Grant Microphone and Accessibility permissions. The portable build is unsigned and not notarized.
- **Linux:** X11 needs a paste helper. Wayland requires XWayland, a desktop shortcut to the absolute executable path plus `--toggle`, `wl-clipboard`, and a compatible/configured paste helper. Native Wayland dictation still needs desktop-specific validation.

These are portable archives, not installers. All builds are unsigned. Source tests
and packaged smoke checks do not establish native microphone and editor delivery
on every desktop. Long dictation, meetings, system-audio captions, and translation
remain planned features.

[Installation](https://github.com/RioPlay/utterleaf/blob/main/docs/installation.md) ·
[Wayland help](https://github.com/RioPlay/utterleaf/blob/main/docs/wayland.md) ·
[Screenshots](https://github.com/RioPlay/utterleaf/blob/main/docs/screenshots.md) ·
[Earlier releases](https://github.com/RioPlay/utterleaf/releases)
