# Windows desktop prerelease

## Goal

Ship a Windows x64 CPU preview of the completed desktop dictation improvements,
then continue the desktop and original Android completion gauntlet. The user
selected Windows desktop first on September 12, 2026. This is a bounded preview,
not completion of either platform roadmap.

## Area and constraints

Candidate version: `0.4.6rc1`; preview tag: `desktop-v0.4.6-rc.1`. Prepare an
isolated release branch from `origin/main` and copy only desktop source, tests,
packaging and applicable documentation from the working tree. Preserve Android
work and existing installed/dist/build files. Reuse the existing Python environment
without redirecting its editable installation. Keep build outputs local and ignored.

Use the canonical CPU build. No speech weights, FFmpeg/PyAV native codecs or CUDA
libraries in the archive. Include reviewed VAD resources and complete dependency
notices. No microphone capture, consumer clipboard changes or automatic model
downloads during package verification. Internal OBS components are not an available
feature; no OBS enrollment, plugin or live transcription is promised by this preview.

## Acceptance

- Exact desktop source revision, matching Python versions and accurate release notes.
- Full desktop tests pass on that checkout; skips and device limitations are explicit.
- Fresh canonical package passes frozen help, diagnostics, formatting and offline
  fixture transcription checks, with notices, resource scans and SHA-256 checksums.
- Independent review covers release scope, test evidence, package contents and notes.
- Windows-only publication is explicitly a prerelease and does not replace the
  existing stable release. Use the separate `desktop-v*` preview tag namespace:
  existing `v*` automation publishes three-platform stable releases.

## Verification

From the isolated checkout, use the existing environment through a local `.venv`
junction, with `PYTHONPATH` scoped to that checkout:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\packaging\build.ps1
.\dist\Utterleaf\utterleaf-cli.exe --help
.\dist\Utterleaf\utterleaf-cli.exe --doctor
```

Record exact offline fixture arguments, source revision, dependency inventory,
artifact hashes and independent review results here before publishing.

## Non-goals and stop

Do not finish OBS, Android language features, other desktop releases, or broad
physical-device certification inside this package. Stop release edits when the
named preview checks pass and publication is verified; resume the full gauntlet.
Unsigned status and remaining live-microphone/editor/endurance evidence must be
clear. No stable or enterprise-readiness claim follows from this prerelease.

## Progress

The isolated candidate is based on main `566839d`, with the desktop working-tree
changes copied separately from Android. Both Python versions are `0.4.6rc1`.
Reviewed OBS groundwork and its pinned dependency/notices remain an atomic source
slice with no app entry point. Windows preview CI builds the exact `desktop-v*`
tag, validates its version, runs tests and uploads an artifact; it cannot publish
a release. Publication follows a separate exact-revision/artifact review.

The first candidate suite found a foreground-dependent Settings test: `focus_set`
did not emit FocusIn when Windows foreground belonged elsewhere. The test now
generates FocusIn on the real control, retaining the actual binding and visibility
assertions without stealing focus. The focused Settings suite passed 33 tests.
The full candidate run then passed **1,431 tests, 14 skipped in 39.94 seconds**:
11 external-codec fixture cases, one absent local public-speech fixture, one
symlink privilege case and the opt-in names-only clipboard isolation probe.

The fresh canonical local CPU build passed with 35 notice entries. Frozen help,
doctor and punctuation formatting passed; an empty clipboard-worker request
returned unavailable without requesting clipboard access. Archive inspection
confirmed version `0.4.6rc1`, the new capture/review/delivery modules, and absence
of transcription weights, FFmpeg native libraries and NVIDIA libraries.

Frozen offline file recognition passed on an 88-second repeated public JFK PCM
fixture with the existing verified `base.en` model, CPU/int8 and isolated test
preferences. The command used `--transcribe-file <fixture> --audio-track 1
--output <new-file.srt> --offline`, completed in 21.31 seconds and produced 13
subtitle cues through 87.41 seconds. Composite SHA-256:
`ea785dcfe09f596d84acc95dfcdb811edb277ff7b77dc5acc1cc305b14b726fe`.
This is a bounded frozen-path check, not general accuracy or microphone evidence.

Build/test versions and compatible wheel SHA-256 hashes are pinned in
`packaging/requirements-windows-preview.txt`; CI requires hashes and wheels only.
The three workflow actions use immutable commit SHAs verified from their official
repositories. Registry hashes identify admitted inputs; they are not independent
reproduction or certification of upstream code. Final CI artifact identity,
offline transcription of that downloaded artifact and publication remain pending.
Existing user dist/build and installed applications have not been replaced.

Independent release review caught and corrected hidden test-evidence paths that
the artifact uploader would omit, inaccurate download-checksum naming and missing
executable-checksum validation. CI now runs frozen formatting and rejects an
empty worker request as well. The CI archive must still pass the local offline
fixture transcription gate before publication; the earlier local build is a
separate receipt.
