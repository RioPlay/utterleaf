# Current correctness review

Status: automated checks passed; physical-device acceptance remains open.
This is a focused engineering pass, not a complete audit.

## Current pass

- **Desktop v0.4.5:** cancellation during formatting and edit-window retargeting
  are covered by the 11-case regression set. Windows, macOS and Linux CI are
  green; the release is fully published. The local archive checksum and contents
  were also verified. The local full repeat passed 731 tests with 13 skips
  (11 optional FFmpeg, one symlink-privilege and one Tk-availability case).
  An initial transient Tcl failure passed isolated reruns; no new skip was added.
- **Android alpha09 source:** revision `ed491bd` passed build, lint, 8 JVM,
  61 API 35 emulator and 3 release-contract tests in [CI run 34475913178](https://github.com/RioPlay/utterleaf/actions/runs/34475913178).
  Emulator checks had zero failures and zero skips. Coverage includes Shift-space
  selection, held deletion, forward Delete, punctuation, independent sizing and
  practice reset, explicit mic entry, local transcript editing and hold-to-insert
  cancellation/late-result handling. Existing model-import and privacy checks
  remain included. The tested revision is on main. Signed publication passed in
  [run 34476752688](https://github.com/RioPlay/utterleaf/actions/runs/34476752688),
  including upgrade/reinstall/setup checks. The downloaded APK's SHA-256 is
  `1c85634a5d085803d485e9a06d1a89d570624a3ffe277bc2d28e9a94364ca37c`,
  matching the published checksum; version code is 9 with the existing certificate.

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
