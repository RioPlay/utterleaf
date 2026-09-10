# Current correctness review

Status: pending release validation. This is a focused engineering pass, not a
release certificate or complete audit.

## Current pass

- **Desktop:** addressed cancellation during formatting and edit-window
  retargeting. The regression set contains 11 cases. A local Tcl transient
  failure was isolated and then passed; the full repeat passed 731 tests with
  13 skips (11 optional FFmpeg cases, one symlink case, and one Tk-availability
  case). PR12 CI passed Windows and macOS tests and Linux tests; the Linux build
  remains pending.
- **Android model import:** the generic import path autodetects the reviewed
  tiny.en, base.en and small.en models by exact size and SHA-256, independently
  of the browser download selector. A failed or cancelled replacement retains
  the old working model.
- **Android touch/input:** the in-progress gesture work covers Spacebar cursor
  movement and hold/slide/release accent selection while retaining the tap route
  through Tools → Accents → letter. The secure in-window overlay remains part of
  the validation surface.

Gesture CI has not run yet. The Android touch, overlay and import statements
above describe current source work and targeted checks, not completed release
validation.

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
