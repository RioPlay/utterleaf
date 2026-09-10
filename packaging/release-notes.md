**v0.4.2** improves microphone recovery and makes the microphone check report interruptions accurately.

- Windows WASAPI device-busy and invalidated-device/resource errors now receive the existing single retry after the failed stream closes. Retries remain bounded and keep the selected input.
- Permission and unsupported-format failures receive specific recovery guidance instead of a generic microphone error. They are not retried.
- **Test microphone** checks stream liveness throughout the check. Earlier audio no longer produces a misleading success result after capture stops.
- [Windows microphone sharing help](https://github.com/RioPlay/utterleaf/blob/main/docs/microphone-troubleshooting.md#windows-using-discord-or-another-voice-app) explains shared access, exclusive-mode settings and call/reconnect troubleshooting.

A brief native Windows test accepted two simultaneous shared capture streams while Discord was running, without saving or transcribing audio. That does not reproduce a Discord voice-call conflict or establish its cause. Utterleaf cannot override another application's exclusive microphone access. No OS permissions, audio settings or Discord configuration are changed automatically.

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
