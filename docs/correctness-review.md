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
- **Android alpha07 source:** revision `ee47aa7` passed build, lint, 8 JVM,
  44 emulator and 3 release-contract tests in [PR13 CI run 34443696731](https://github.com/RioPlay/utterleaf/actions/runs/34443696731).
  Emulator checks had zero failures and zero skips. Generic
  model import autodetects reviewed tiny.en, base.en and small.en by exact size
  and SHA-256, independently of the download selector; failed or cancelled
  replacement retains the old working model. Current touch source covers
  Spacebar cursor movement and hold/slide/release accent selection while keeping
  the Tools → Accents → letter tap route. The secure in-window overlay remains
  part of manual acceptance.

Injected gestures passed in the live synthetic editor, and the held-accent capture
was visually reviewed. Touch, overlay and import manual acceptance remain open;
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
