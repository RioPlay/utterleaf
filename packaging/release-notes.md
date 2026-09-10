**v0.4.3** fixes a Windows microphone startup failure from background threads, including dictation hotkeys, tray/IPC actions and the Settings microphone check.

- Windows capture now opens, starts and releases its stream on a dedicated COM-initialized thread. The thread exits after the stream closes; no idle microphone capture is added.
- Fixes a reproduced `Error starting stream / PaErrorCode -9999` failure. PortAudio can attach stale WDM-KS error details to this WASAPI failure, making it look like an unrelated driver or sharing issue.
- Retains v0.4.2's bounded device-error retry, permission/format guidance and microphone-check liveness monitoring.
- [Windows microphone sharing help](https://github.com/RioPlay/utterleaf/blob/main/docs/microphone-troubleshooting.md#windows-using-discord-or-another-voice-app) explains shared access, exclusive-mode settings and call/reconnect troubleshooting.

The diagnosed failure occurred on a background thread while the same microphone opened successfully on the main thread. Initializing COM on the background thread eliminated that failure in native checks. This identifies an Utterleaf threading defect, not proof that Discord takes exclusive control. Utterleaf cannot override another application's exclusive microphone access. No OS permissions, audio settings or Discord configuration are changed automatically.

Includes the file-format, model setup, list/paragraph and Windows GPU diagnostic improvements from [v0.4.1](https://github.com/RioPlay/utterleaf/releases/tag/v0.4.1). The planned self-updater is not included.

Quit the older app before extracting and reopening this update.

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
