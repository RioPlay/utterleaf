**v0.4.4** fixes a sentence-spacing gap when dictation includes a spoken new line, new paragraph, bullet-list or numbered-list command.

For example, `That is wrong.Maybe say no.I have an idea.Whatever works new paragraph` now produces separated sentences followed by the requested paragraph break.

- Keeps intentional line breaks and list formatting while repairing likely fused sentence openings.
- Preserves recognizable URLs, email addresses, paths, decimals, code spans and common member-access expressions. Unmarked prose and identifiers can be ambiguous; literal/code modes bypass this repair.
- Includes regression coverage for multiple dictation passes, expired continuation context, layout commands and technical tokens.
- Retains the Windows microphone startup fix from [v0.4.3](https://github.com/RioPlay/utterleaf/releases/tag/v0.4.3).

This fixes a reproduced layout-command path. It does not establish the cause of every reported spacing problem. No transcript logging, network processing or preference changes are added. The planned self-updater is not included.

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
