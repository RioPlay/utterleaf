# Optional desktop speech-end stopping

Completed implementation, independently reviewed and shipped in the
[Windows 0.4.6 RC2 preview](https://github.com/RioPlay/utterleaf/releases/tag/desktop-v0.4.6-rc.2)
from immutable source `90d2e147c6c84af2639317b427a2f5135b3ff997`.
The [desktop roadmap](../../desktop-roadmap.md) owns release status and remaining
platform acceptance; the [resource review](../../desktop-vad-resource.md) records
the local detector identity and fixture evidence.

## Delivered contract

- Disabled by default. Each take starts explicitly; no idle listening or automatic
  restart. Stop-after-speech and immediate insertion are separate preferences.
- A verified local detector uses at most eight seconds of recent audio on one
  coalescing worker. Sample-clock timing and validated speech onset precede a
  sustained pause; initial silence does not end a take.
- Each result belongs to its capture, endpoint instance, generation and target.
  Manual stop, cancellation, device failure and later takes invalidate old work.
  Missing or unsupported detector resources leave manual stopping available.
- Automatic stops open temporary Copy/Insert/Discard review by default.
  Automatic insertion requires the original supported native field, text and
  caret, plus the normal cancellation and clipboard guards. No Send/Enter or
  spoken editor-command execution follows an automatic stop.
- Local save, discard, reopen and staged defaults preserve preferences and user
  data. The subsequent continuous-capture work removed the old duration cap;
  explicit stop, cancellation and optional speech-end stopping remain available.

## Verification

The original independent focused review passed 223 app, review, interruption,
Settings, configuration, backup and hotkey tests. Its integrated source run
passed 827 tests with 12 explicit environment/fixture skips. Later exact-tag
[RC2 CI](https://github.com/RioPlay/utterleaf/actions/runs/34740809768)
passed 1,446 tests with 13 skips, followed by independent downloaded-artifact
verification. The original source-only receipt is superseded for packaging by
that release evidence.

Deterministic tests cover onset, pause reversal, audio gaps, duplicate clocks,
worker bounds, stale callbacks, manual cancellation, failure fallback and guarded
review/insertion. A local run with the reviewed model and public JFK speech
fixture produced one endpoint at 5.984 seconds. Release CI exercised the installed
model on silence; its public-speech endpoint test skipped because that optional
fixture is not bundled. See the resource review for the exact fixture record.

A September 13 independent source audit found no current behavioral blocker.
Relevant checks are `tests/test_speech_endpoint.py`, `tests/test_speech_end_app.py`,
`tests/test_settings_ui.py` and `tests/test_config.py`.

## Remaining limits and stop

Named physical-microphone evaluation remains open for quiet speech, thinking
pauses, noise, other speakers, accents and CPU contention, including real-time
end-to-delivery latency. Synthetic/model fixtures and frozen packaging do not
establish those results. Broad editor and assistive-technology acceptance remain
separate roadmap gates. This completed slice adds no ambient assistant, cloud
VAD, arbitrary model loader or Android behavior; further detectors or behavioral
changes need a separate measured task.
