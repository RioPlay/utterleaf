**v0.4.0** adds local file transcription, selective backup, and safer recovery when a microphone stops mid-take.

- **Transcribe a file:** use Tools → Transcribe a file in the tray, review the transcript, then export TXT, SRT, or VTT. Includes progress, cancellation, discard, and one window per profile. Nothing is saved automatically; this flow never downloads missing models.
- **Selective backup:** export portable preferences and vocabulary from Settings, preview an import, select changes, and keep, merge, or replace vocabulary. Network, clipboard protections, devices, shortcuts, models, audio, transcripts, logs, and control tokens are excluded. Failed multi-file imports attempt rollback and report incomplete recovery.
- **Interrupted microphones:** detect a stopped stream or three seconds without audio callbacks. Stop capture and retain available speech in the two-minute recovery slot for explicit Copy last dictation. Quiet audio alone is not an interruption; no alternate microphone is selected automatically.
- **Clipboard protection:** Windows sequence checks detect intervening copies even when text matches. Shortcut failures keep recovery available. Rich-format preservation and fully atomic native restoration remain open work.

Packaged file input supports mono/stereo integer PCM WAV, 8–32-bit at 8–48 kHz, up to 10 minutes and 256 MiB. Broader media requires a source installation with PyAV. Timestamped recognition requires CPU or CUDA and an already installed model. Cancellation waits for an active native model operation to return.

Some microphone backends require restarting after reconnecting. Identical names cannot distinguish physical devices. Native hotplug, assistive-technology, and broad editor/device acceptance checks remain open. Desktop and Android releases remain independent.

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
