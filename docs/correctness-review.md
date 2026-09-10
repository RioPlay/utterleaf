# Current correctness review

Status: automated checks passed; physical-device acceptance remains open.
This is a focused engineering pass, not a complete audit.

## Current pass

- **QA pass, subsequently released in alpha13:** revision `d942098` passed
  [CI 34513111803](https://github.com/RioPlay/utterleaf/actions/runs/34513111803):
  76 API 35 emulator tests (zero failures/skips), 8 JVM tests, lint, builds and
  3 release contracts. Includes slider accessibility values/reset, conditional
  gesture waits and live-IME editing/stale-action checks. Initial test synchronization
  failures were fixed before the complete rerun; see [details](android-keyboard-design.md#released-in-alpha13).
  Release revision `45da18a` also passed [CI 34516072857](https://github.com/RioPlay/utterleaf/actions/runs/34516072857)
  and [signed publication](https://github.com/RioPlay/utterleaf/actions/runs/34517132892).
  Physical-device and TalkBack acceptance remain open.

- **Android alpha12:** revision `aec275b` passed
  [74 API 35 emulator tests (zero failures/skips), JVM tests, lint and 3 release contracts](https://github.com/RioPlay/utterleaf/actions/runs/34498263015).
  [Signed publication](https://github.com/RioPlay/utterleaf/actions/runs/34499446037)
  verified package/version identity, certificate continuity and emulator upgrade/reinstallation.
  Downloaded APK SHA-256: `c327c5b6d11544f53d2f7da5e503bd18e781939e047091628aad0e3ff2a524d2`.
  [Quick-action evidence and limits](android-quick-actions.md) do not establish
  physical-device or accessibility acceptance. The QA follow-up above is
  separate from this released alpha12 pass.

- **Android alpha11:** revision `55e7173` passed
  [71 API 35 emulator tests, 8 JVM tests, lint and release contracts](https://github.com/RioPlay/utterleaf/actions/runs/34486083030).
  [Signed publishing checks](https://github.com/RioPlay/utterleaf/actions/runs/34487215244)
  verified the persistent signing identity, increasing version code 11, signed
  alpha03-to-alpha11 upgrade, reinstallation and setup launch. The downloaded APK
  matched published SHA-256 `110361e5fd1e0ff33b2cb46da725d9a83b1560cf608b49f3b593e6d3559c804d`.
  This does not establish physical-device behavior or model/preference retention
  during upgrade. [Current UI and limits](android-keyboard-design.md#released-in-alpha11).

- **Desktop v0.4.5:** cancellation during formatting and edit-window retargeting
  are covered by the 11-case regression set. Windows, macOS and Linux CI are
  green; the release is fully published. The local archive checksum and contents
  were also verified. The local full repeat passed 731 tests with 13 skips
  (11 optional FFmpeg, one symlink-privilege and one Tk-availability case).
  An initial transient Tcl failure passed isolated reruns; no new skip was added.
- **Android alpha10 source:** revision `cd009b1` passed build, lint, 8 JVM,
  67 API 35 emulator and 3 release-contract tests in [CI run 34480299407](https://github.com/RioPlay/utterleaf/actions/runs/34480299407).
  Emulator checks had zero failures and zero skips. Coverage includes Shift-space
  selection, held deletion, forward Delete, punctuation, independent sizing and
  practice reset, explicit mic entry, local transcript editing and hold-to-insert
  cancellation/late-result handling. Added checks cover held Ctrl+Backspace in
  EditText, modifier cancellation, configurable repeat, retained imports,
  legacy models and busy/stale model-selector callbacks. Existing privacy checks
  remain included. The tested revision is on main. Signed publication passed in
  [run 34481384006](https://github.com/RioPlay/utterleaf/actions/runs/34481384006),
  including upgrade/reinstall/setup checks. The downloaded APK's SHA-256 is
  `12c7b490100f0689b6cc17f6cd701aac1c5821a1f6cc11dff2196fd3f4ce493d`,
  matching the published checksum; version code is 10 with the existing certificate.

Injected gestures passed in the live synthetic editor. Voice edit/review captures
were visually reviewed. Touch, overlay and import manual acceptance remain open;
emulator success does not establish real-phone usability or accessibility.

## Manual QA before release validation closes

- Pixel 8 Pro: real editors, field changes and selection replacement; verify
  cancellation during formatting/recognition and no edit-window retargeting.
- TalkBack and real editors: type, correct, submit, switch keyboard, open
  accents, cancel a hold, and complete cancellation with multitouch.
- 320 dp portrait and landscape: inspect key bounds, Spacebar cursor movement,
  hold/slide/release accents, tap-route fallback and secure in-window overlay.
- Model import: import each valid model through a selector-independent path;
  try a wrong file, malformed/oversized file, cancellation, rotation and an
  interrupted replacement; verify the previous model and ordinary typing remain
  usable.
- Repeat the desktop cancellation and retargeting cases after any formatting or
  editor-session change; record build, device, OS and result for each gate.
