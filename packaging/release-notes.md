**v0.3.7** improves Settings usability following a product design and QA audit. The speech engine and dependencies are unchanged.

**Privacy and security:** local control commands now require a per-launch secret,
oversized requests are rejected, and stalled clients no longer terminate the
listener. Quit the older app and reopen the updated version after extracting;
updated clients refuse to send control commands using the old protocol.

- Direct task headings and smaller mascots leave more space for controls.
- Contrasting selection marks and keyboard focus colors improve control visibility.
- Long status messages wrap without crowding Save and Close.
- Invalid settings return you to the relevant field; an invalid vocabulary line is selected for correction before anything is saved.
- Restoring defaults preserves your download and clipboard preferences, including offline mode.
- Hardware and noise controls show readable labels. Draft captions are clearly labeled as dictation preview.
- Updated screenshots and a documented quality audit distinguish verified checks from remaining native-platform, accessibility, and display-scaling work.

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
