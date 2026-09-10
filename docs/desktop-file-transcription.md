# Local file transcription

Implemented in the development branch; compiled-platform validation and real-speech
quality remain release gates. This first version processes one explicitly selected
local file. It does not record system audio or create transcript history.

Open **Tools → Transcribe a file** from the tray, or run `utterleaf --files`.
Choose a file, select **Transcribe**, and review the preview. Choose TXT, SRT, or
VTT before **Export**. Existing destinations require a replace confirmation;
the original media file cannot be used as the export destination. **Discard**
clears the preview and **Close** cancels any work and discards the preview.
Opening the tool again brings its existing window forward. Settings keeps its
own separate window. No microphone opens merely because this tool is open.

![Local file review and export window](assets/screenshots/file-transcription.png)

Actual development window with synthetic sample text; no personal recording is shown.

Packaged builds support integer PCM WAV: mono or stereo, 8/16/24/32-bit samples,
and 8–48 kHz sample rates. Python's standard-library WAV reader and the existing
NumPy resampler decode bounded one-second blocks, with no additional codec payload.
Compressed or floating-point WAV and other formats report an actionable error.

Source installations also support the first audio track of media that the installed
PyAV/FFmpeg decoder can read. Decoding downmixes stereo to mono at 16 kHz. Media that references other
files or network sources is rejected. No audio is uploaded, downloaded, or written
to temporary storage. File mode never downloads models, even if ordinary dictation
allows downloads: install the selected model explicitly first.

The initial limits are **256 MiB input and 10 minutes of decoded audio**. Longer
audio is rejected rather than silently truncated. Decoding checks the sample budget
incrementally, independent of possibly incorrect media duration metadata. PCM is
bounded, but native decoder/model memory and execution time are not hard sandbox
limits. Model inference still holds the bounded clip in memory. Full-hour streaming
and cancellation during a native inference call are not implemented.

Use the CPU or CUDA CTranslate2 engine for timestamped files. The OpenVINO adapter
does not expose validated timestamps and returns an actionable error; it never
fabricates subtitle timing. CUDA runtime failures retry on CPU using installed
weights. Dictation's existing string recognition API is unchanged.

Model segment start/end values are retained in seconds, relative to decoded audio.
They are estimated speech boundaries, not independently verified alignment or
original container timecodes. Container timestamp gaps/offsets are not preserved.
There are no speaker labels. Spoken phrases such as “scratch that” remain literal
transcript text; dictation editing, filler removal, dictionary prompting, and
denoising are not applied to file transcripts.

Exports are explicit UTF-8 TXT, SRT, or VTT. Subtitle times round to milliseconds
with correct carry into minutes/hours. A cue that rounds to zero duration causes
an error rather than an invented duration. Subtitle text uses a single line per
cue and escapes markup characters. Plain text preserves recognized words and
internal whitespace. Existing output files require explicit overwrite. Export
publishes a completed temporary text file atomically; default no-overwrite uses a
hard link, so a filesystem without hard-link support returns an error safely.
There is no automatic save on completion, error, or cancellation.

## Integration API

```python
from utterleaf.file_transcription import transcribe_file
from utterleaf.transcript import export_transcript, TranscriptionCancelled

result = transcribe_file(selected_path, cfg, cancel=stop_event, progress=on_progress)
export_transcript(result, selected_output, format="vtt", overwrite=False)
```

`cancel` is an optional `threading.Event`. `progress(phase, fraction)` receives
`decoding`, `loading`, `recognizing`, or `complete`; unknown fractions are `None`.
Cancellation is checked between decoded frames and generated segments and while
waiting for the recognition lock. Model loading and active native calls must
return before cancellation can finish. Cancellation raises
`TranscriptionCancelled(RuntimeError)` and discards the in-flight result.
Input/format/timing errors raise `ValueError`; media and capability failures raise
`RuntimeError`; ordinary filesystem/model errors retain their original classes.

`Transcript.segments` is an immutable tuple of `Segment(start, end, text)`;
`Transcript.text` joins segment text for plain-text callers. `language` records
the engine language when available. `CTranslateEngine.transcribe_segments` also
accepts a mono 16 kHz float array and the same cancel/progress arguments.
`export_transcript` infers format from the output extension when omitted and
returns the destination `Path`. It does not create missing parent directories.

## Verification and remaining gates

Unit tests cover the actual frozen-build PyAV stub with WAV decoding, PCM widths,
truncation, bounded cancellation, timestamp validation/carry, Unicode, silence, literal editing
phrases, refusal to overwrite, temporary-text cleanup, real PyAV WAV resampling,
malformed/oversized/over-duration inputs, cancellation, offline model loading,
and unsupported-engine errors. These do not establish speech accuracy.

Packaged builds retain the project's policy excluding PyAV/FFmpeg. PCM WAV support
does not add these libraries. Before expanding packaged media support, review
bundled codecs and licenses, distribution size, clean installation,
video/audio format coverage, truncated input behavior, and real-speech timing on
supported platforms. Retain the existing packaging exclusion until those gates
are complete. No new decoder dependency is silently installed by this feature.
