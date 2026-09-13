# Desktop speech detector resource review

[Speech-end plan](plans/active/desktop-speech-endpoint.md) ·
[Component policy](model-resource-policy.md)

Reviewed September 12, 2026 for the optional desktop speech-end path. This is a
bounded resource/notice review, not a complete dependency or vulnerability audit.
Android does not use this Python runtime or gain any new dependency/permission.

## Identity and origin

| Item | Reviewed value |
| --- | --- |
| Package | faster-whisper 1.2.1 |
| Upstream revision | `65882eee9f5cdbeeb2d877f1131d48cf241b327d` |
| Asset | `faster_whisper/assets/silero_vad_v6.onnx` |
| Bytes | 1,245,151 |
| SHA-256 | `4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2` |
| Runtime inspected | onnxruntime 1.28.0, local CPU execution |

The installed asset matches the bytes at the
[faster-whisper release revision](https://github.com/SYSTRAN/faster-whisper/tree/65882eee9f5cdbeeb2d877f1131d48cf241b327d)
and the original V6 integration commit `dea24cbcc6cbef23ff599a63be0bbb647a0b23d6`.
The [upstream integration](https://github.com/SYSTRAN/faster-whisper/pull/1373)
identifies the Silero V6 origin and modified sequence export. The later V6.2
export has different bytes and is not silently admitted by this review.

## Redistribution and loading decision

The [faster-whisper license](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/LICENSE)
and [Silero V6 license](https://github.com/snakers4/silero-vad/blob/v6.0/LICENSE)
use MIT terms requiring retained copyright/permission notices. The reviewed
integration can be bundled with Utterleaf's Apache-2.0 source while preserving
those notices; this does not replace the rest of the distribution's obligations.

`packaging/collect_notices.py` now verifies the bundled asset and includes a
separate Silero entry and full [Silero notice](../packaging/notices/silero-vad-LICENSE.txt).
It also copies ONNX Runtime's installed `LICENSE` and `ThirdPartyNotices.txt`,
which the inspected wheel's metadata does not enumerate. Missing required texts
or unreviewed model bytes stop this collection step. Focused packaging checks
passed; a new complete frozen binary has not been built or audited here.

The endpoint loader first checks the reviewed wrapper/runtime versions, then
reads only this fixed package resource with a size bound and checks its digest
before construction. It passes those verified bytes to the runtime, avoiding a
second file read between verification and loading. Frozen builds retain both packages' metadata for this check;
notice collection also validates source and bundled versions. It creates an instance separate from
transcription's cached VAD. Unavailable or different resources leave manual
stopping usable; no hidden download, arbitrary path or weaker fallback detector.
The digest establishes expected bytes, not immunity from parser/model defects.

## Adapter evidence and limits

The wrapper resets state per call. The endpoint therefore supplies bounded recent
16 kHz context, aligned to 512-sample frames, rather than classifying isolated
32 ms fragments. A serial worker coalesces pending snapshots. It counts observed
audio samples, requires four consecutive positive frames for onset and uses
hysteresis for continuing speech. Missing intervals cannot count as silence.

Local checks exercised silence through the actual model and a pre-existing public
JFK WAV fixture (`artifacts/file-jfk-fixture.wav`, SHA-256
`59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e`).
One second of silence, four seconds of fixture speech, then two seconds of silence
produced one endpoint at sample 95,744 (5.984 s) with a 1.2 s pause preference.
The bounded fixture evaluation took 0.136 s locally; this is an offline functional
check, not microphone startup, real-time end-to-delivery latency or a percentile.
No microphone capture or model download was used.

Repeat with `.\.venv\Scripts\python -m pytest tests/test_speech_endpoint.py
tests/test_audio.py tests/test_audio_interruption.py`. The public-fixture check
explicitly skips when that local fixture is absent; CI must not download it
implicitly. The same suite separately verifies lifecycle behavior with fixed
probability sequences and real worker cancellation/coalescing.

Named physical microphones, quiet/noisy environments, thinking pauses, accents,
other speakers and sustained CPU contention still need evaluation. A speech
detector does not establish that the user intended to finish or distinguish the
user from another audible speaker. Keep stopping optional and cancellation/manual
stop available throughout each explicitly started take.
