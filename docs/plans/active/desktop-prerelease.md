# Windows desktop prerelease

## Goal

Ship a Windows x64 CPU preview of the completed desktop dictation improvements,
then continue the desktop and original Android completion gauntlet. The user
selected Windows desktop first on September 12, 2026. This is a bounded preview,
not completion of either platform roadmap.

## Area and constraints

Candidate version: `0.4.6rc2`; preview tag: `desktop-v0.4.6-rc.2`. Prepare an
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

RC2 was published on September 13, 2026. RC1 was not published: independent inspection of
its downloaded CI artifact found missing runtime license texts and an unused
ASIO DLL. The [runtime notice correction](desktop-runtime-notices.md) adds full
versioned texts, native payload identity checks and fail-closed notice handling.
The separate RC1 tag and artifact remain unchanged for audit. The receipts below
describe RC1 unless a later entry explicitly names RC2.

RC2's canonical local CPU build passes with 43 notice entries, full reviewed
native terms, no ASIO DLL and no metadata-only license placeholders. The final
local suite passes **1,445 tests, 14 skipped in 43.23 seconds** after independently
reviewed test-only Tk cleanup. Frozen help, offline diagnostics, formatting and
an empty worker request behave as expected. The existing 88-second PCM fixture
exports SRT offline in 18.455 seconds with the verified local base.en model.
Exact RC2 tag CI, downloaded-artifact checks and publication also passed, as
recorded below.

### Published RC2 evidence

- Source/tag revision: `90d2e147c6c84af2639317b427a2f5135b3ff997`,
  `desktop-v0.4.6-rc.2`, version `0.4.6rc2`.
- [Exact-tag CI run 34740809768](https://github.com/RioPlay/utterleaf/actions/runs/34740809768):
  **1,446 passed, 13 skipped**, no failures or errors. Actions artifact
  `10311699407` was independently downloaded and inspected.
- Public ZIP: `Utterleaf-windows-x64-cpu.zip`, 112,087,662 bytes, SHA-256
  `3ff16b600fe83b88d1cc384c920098a7a85771a66099bbff50ccc40257917e07`.
  Both archive layers passed integrity and safe-path checks; manifest, all three
  executable hashes, dependency inventory and retained native notices matched.
  No ASIO, FFmpeg-family, NVIDIA/CUDA or transcription weights were present.
- The downloaded frozen build passed help, offline diagnostics and formatting.
  Its empty worker request returned unavailable without requesting clipboard
  access. The same verified 88-second fixture described below, using
  `--transcribe-file <fixture> --audio-track 1 --output <new-file.srt> --offline`,
  completed in 23.6954 seconds with 11 subtitle cues through 87.41 seconds and
  176 words. This is a bounded path check, not general accuracy evidence.
- [Public prerelease](https://github.com/RioPlay/utterleaf/releases/tag/desktop-v0.4.6-rc.2)
  published at `2026-09-13T06:07:01Z` with the reviewed ZIP, checksum, manifest,
  dependencies and pinned requirements. GitHub's asset digest matched the
  verified ZIP. Stable v0.4.5 remained latest after publication.

The preview acceptance gates are complete. Preserve the immutable tag/artifact;
PR #26 integrates the reviewed source and publication records. Physical microphone,
editor, accessibility and endurance limits remain explicit in the release notes.

### Historical RC1 preparation

The historical RC1 candidate is based on main `566839d`, with the desktop working-tree
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
