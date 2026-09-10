**v0.4.1** improves file support, model setup, window activation and repeated dictation.

- **Model readiness:** Settings → Speech & privacy separates model installation, processing and privacy. See Missing/Incomplete/Installed status and explicitly download or repair the selected model without changing the ongoing network preference.
- **Bring windows forward:** tray activation reuses the existing Settings window, restores minimized windows and requests foreground permission on Windows. Modal dialogs and unsaved edits remain intact.
- **Separate takes:** completed prose includes a separating space so pauses or window-title changes do not produce `sentence.Next`. Literal/code output and explicit line breaks retain their formatting.
- **Spoken corrections:** “scratch, that” recognizes a paused command; “scratch that, [replacement]” replaces a verified prior insertion. The edit window is two minutes. Unsupported or changed fields are not blindly deleted; the correction remains available through Copy last dictation.

- Open **Tools ? Transcribe a file ? More formats?** for platform-specific FFmpeg installation instructions, the official download page, and an executable picker.
- Select a local FFmpeg installation once to decode MP3, M4A, AAC, FLAC, OGG/Opus, MP4, MOV, WebM and MKV. Format support depends on that installation. Files remain local; Utterleaf does not download or bundle the decoder.
- Ordinary PCM WAV continues to work without setup, including when an optional decoder is moved or updated. A changed decoder requires selecting it again before use.
- Decoding has bounded output, a deadline, and cancellation that stops the child process. No FFmpeg report or recording file is created. Review and explicitly export TXT, SRT or VTT as before.

File input remains limited to 10 minutes and 256 MiB. CPU/CUDA timestamped recognition requires an already installed model. Decoding cancellation is prompt; active native recognition must return before cancellation completes. FFmpeg is a user-selected trusted executable, not a sandboxed codec service.

[Common-format setup](https://github.com/RioPlay/utterleaf/blob/main/docs/desktop-file-transcription.md#enable-common-audio-and-video-files) includes exact instructions. The selective backup, microphone recovery and clipboard safeguards from v0.4.0 remain included. Desktop and Android releases are independent.

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
