**Utterleaf 0.4.6 RC1 is a Windows desktop preview** for trying the new dictation
and long-recording workflows. The stable release remains v0.4.5.

- **Keep speaking:** manually started recording has no scheduled duration cutoff.
  Audio is temporarily stored on local disk and recognized in bounded batches
  after you stop. Stop, Esc and quit remain available.
- **Transcribe long files:** import recordings without an application total-duration
  limit, choose an available audio track, review the text and export TXT, SRT or VTT.
  Common compressed formats require an explicitly selected external decoder;
  PCM WAV works directly. Separate track exports are not synchronized timelines.
- **Stop at the end of speech:** optionally enable a local 0.5–3 second pause
  detector. Each take still starts manually. Review is the default; automatic
  insertion is a separate choice.
- **Choose Markdown:** Vocabulary → Output style adds local formatting for explicit
  headings and lists. Prose remains the default; raw/code input stays literal.
- **Cleaner delivery:** fixes cover sentence/list boundaries, caret-adjacent spacing
  in supported native Windows fields, cancellation and uncertain paste results.

## Download and try

Download `Utterleaf-windows-x64-cpu.zip`, extract the entire archive into a new
folder, then open `Utterleaf/utterleaf.exe`. Quit the older app first. Keep the
`_internal` folder beside the executables. Settings and previously downloaded
models remain in their existing local locations; keep the old app folder if you
want to return to v0.4.5. Default shortcut: **Ctrl+Win**.

This is a portable Windows x64 CPU build; Python is included. Speech recognition
runs locally. Speech-model weights and optional CUDA libraries are separate;
model setup may download the selected model. FFmpeg and PyAV native codecs are
not included. Third-party notices and executable checksums are inside the archive;
the separate `Utterleaf-windows-x64-cpu.zip.sha256` verifies the download.

**The preview is unsigned.** Windows may show a SmartScreen reputation warning.
This release does not include new macOS, Linux or Android binaries.

## Preview limits

Continuous recording uses temporary, unencrypted local audio files, approximately
220–660 MiB per hour depending on the input rate. They are removed on completion
or cancellation; this is not secure erasure. Free disk space and system resources
still limit session length, and transcript text grows with the recording.

The two-minute text recovery/review window remains separate from recording length.
Verified review insertion and caret-aware corrections require a supported native
Windows Edit field. Browsers and other unsupported review targets use Copy.
Ordinary dictation paste remains guarded at the window level. Check the target
field before retrying any delivery reported as uncertain.

Live OBS transcription is not available yet. Real microphone endurance, broad
editor coverage, accessibility and performance on additional hardware remain
under validation. Source and packaged fixture checks are not certification of
every microphone or application.

[User guide](https://github.com/RioPlay/utterleaf/blob/desktop-v0.4.6-rc.1/docs/user-guide.md) ·
[Long-file transcription](https://github.com/RioPlay/utterleaf/blob/desktop-v0.4.6-rc.1/docs/desktop-file-transcription.md) ·
[Earlier releases](https://github.com/RioPlay/utterleaf/releases)
