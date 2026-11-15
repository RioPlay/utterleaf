**Utterleaf 0.4.6 RC4 is a published Windows desktop preview.** [Download the Windows x64 CPU prerelease](https://github.com/RioPlay/utterleaf/releases/tag/desktop-v0.4.6-rc.4). Stable v0.4.5 remains the default release. RC4 includes the security dependency update and focused Windows dictation delivery repairs.

## Changes in this preview

- **Safer Windows dependencies:** the patched Python dependency floors and hash-checked Windows inputs from the merged security update are included. The Windows archive is CPU-only and unsigned.
- **Reliable clipboard delivery:** Windows paste now obtains its ownership receipt after synthesized clipboard formats are published, while checking that the clipboard still belongs to Utterleaf. Uncertain delivery is not retried automatically.
- **Settings recovery:** a Settings launch that encounters a briefly held instance lock retries boundedly; persistent contention is handled without an unhandled traceback.
- **T3 Code formatting:** the exact T3 Code assistant executable identities use prose spacing between dictated takes. General executable parsing remains narrow so code editors and Linux terminal-title cases keep literal formatting.

## Download and try

Download `Utterleaf-windows-x64-cpu.zip`, extract the entire archive into a new folder, then open `Utterleaf/utterleaf.exe`. Quit an older Utterleaf process first. Keep the `_internal` folder beside the executables. Existing preferences, vocabulary and downloaded models stay in their local locations. The preview does not delete user data.

This is a portable Windows x64 CPU build; Python is included. Speech recognition runs locally. Speech-model weights and optional CUDA libraries are separate. Model setup may download the selected model. FFmpeg and PyAV native codecs are not included. Third-party notices and executable checksums are inside the archive; the separate `Utterleaf-windows-x64-cpu.zip.sha256` verifies the download.

**The preview is unsigned.** Windows may show a SmartScreen reputation warning. This preview contains no new macOS, Linux or Android binaries. Stable v0.4.5 remains the default download. RC4 is published as a prerelease with `latest=false`, so it does not replace the stable release.

## Preview limits

The included Python 3.14.10 runtime still contains Expat 2.9.0, and SQLite remains 3.50.4. Known upstream advisories for these native components remain; their presence does not establish exploitability in Utterleaf. This preview is not described as fully secure or free of known vulnerabilities. See the [dependency security notes](https://github.com/RioPlay/utterleaf/blob/main/docs/plans/active/desktop-dependency-security.md) for scope and details.

Continuous recording uses temporary, unencrypted local audio files, approximately 220 to 660 MiB per hour depending on input rate. They are removed on completion or cancellation; this is not secure erasure. Free disk space and system resources limit session length, and transcript text grows with the recording.

The two-minute text recovery/review window remains separate from recording length. Verified review insertion and caret-aware corrections require a supported native Windows Edit field. Browsers and other unsupported review targets use Copy. Ordinary dictation paste remains guarded at the window level. Check the target field before retrying any delivery reported as uncertain.

Live OBS transcription is not available. Automated tests and controlled native-field checks do not establish real microphone performance, broad editor coverage, accessibility, or performance on additional hardware. The final T3 Code two-take retry after installation remains to be confirmed.

[User guide](https://github.com/RioPlay/utterleaf/blob/desktop-v0.4.6-rc.4/docs/user-guide.md) | [Long-file transcription](https://github.com/RioPlay/utterleaf/blob/desktop-v0.4.6-rc.4/docs/desktop-file-transcription.md) | [Earlier releases](https://github.com/RioPlay/utterleaf/releases)
