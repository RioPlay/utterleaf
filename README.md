<p align="center">
  <img src="docs/assets/brand/utterling-default.png" width="120" alt="Utterling, your leafy dictation companion" />
</p>
<h1 align="center">Utterleaf</h1>
<p align="center"><strong>Let ideas speak.</strong><br />Private, on-device dictation for Windows, macOS, and Linux.</p>
<p align="center">
  <a href="https://github.com/RioPlay/utterleaf/releases/latest"><strong>Download</strong></a>
  · <a href="#get-started">Get started</a>
  · <a href="docs/user-guide.md">User guide</a>
</p>

Hold a shortcut, speak, and release. Utterleaf turns your speech into text and
pastes it into the app you're using. Your microphone closes between takes, and
speech recognition stays on your device. No account. No saved recording history.

![Utterleaf's dark Settings with shortcut controls, a microphone check, and Utterling](docs/assets/screenshots/dictation-dark.png)

*Current development version on Windows. The [latest release](https://github.com/RioPlay/utterleaf/releases/latest) may look different.*

## Get started

1. **[Download your build](https://github.com/RioPlay/utterleaf/releases/latest)** and extract the entire archive. Keep the `_internal` folder beside the executable; Python is included.
2. **Open Utterleaf.** Run `Utterleaf/utterleaf.exe` on Windows, or `./Utterleaf/utterleaf` on macOS/Linux. The selected speech model downloads on first use; recognition then works offline.
3. **Click a text field and dictate.** Hold **Ctrl+Win** on Windows or **Ctrl+Shift+Space** on macOS/X11 Linux, wait for the recording state or start sound, speak, then release. **Esc** cancels.

Downloads support Windows x64, macOS Apple Silicon, and Linux x64 (Ubuntu 24.04
or compatible). Builds are unsigned; macOS is not notarized. On macOS, allow
Microphone and Accessibility access. On Wayland, configure a desktop shortcut
for `utterleaf --toggle` and a compatible paste helper—see the
[platform setup guide](docs/installation.md).

## Make it yours

- **A quieter desktop.** Dark Settings and tray-only feedback by default. Enable the floating indicator when you want a countdown or live captions.
- **Your words, your way.** Add names and phrases to your vocabulary. Use spoken punctuation and list commands, or turn cleanup off to keep the model transcript.
- **A way back.** If text doesn't arrive, choose **Copy last dictation (2 min)** from the tray. Only the latest result is held temporarily in memory; **Forget last dictation** clears it. Copies may remain in your system clipboard history.
- **A friendly companion.** Utterling welcomes you, helps explain voice commands, and reacts to your microphone check. All artwork is bundled locally.

Click the tray leaf to open Settings. [Explore the current screens](docs/screenshots.md)
or follow the [user guide](docs/user-guide.md) for microphone checks, lists, and
editing commands. Follow-up edits in unsupported text fields use manual clipboard
replacement rather than changing your document automatically.

NVIDIA acceleration needs compatible CUDA libraries; selecting GPU alone doesn't
install them. The Windows CPU download works without those libraries, and macOS
currently uses CPU inference. [Installation and GPU setup](docs/installation.md).

## Keep growing

[Roadmap](docs/roadmap.md) · [Development & builds](docs/development.md) ·
[Platform testing](docs/platform-testing.md) · [Artwork](docs/branding.md) ·
[Report an issue](https://github.com/RioPlay/utterleaf/issues)

Utterleaf is [Apache-2.0 licensed](LICENSE), © 2026 RioPlay. See [NOTICE](NOTICE)
for attribution. Binary downloads include third-party notices and license texts.
Model weights download separately and are not bundled in the repository.
