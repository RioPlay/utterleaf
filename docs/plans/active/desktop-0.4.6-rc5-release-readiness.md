# Desktop 0.4.6 RC5 preparation

Status: active, local candidate only. No tag, upload, installation or publication
is authorized by this plan. Stable remains v0.4.5; published Windows RC4 is retained.

## Goal

Deliver the desktop research priorities through dependable input, explicit local
corrections and a reviewable release candidate. Android is paused until a suitable
pipeline is agreed; its prepared branch and published evidence remain intact.

## Source and area

`feat/desktop-modernization` in the existing desktop worktree. Merge `92d054a`
reconciles its prepared UI/recovery work with main `056cb49`, including published
RC4's security, clipboard, Settings-lock and T3 spacing fixes. Source version is
`0.4.6rc5`; a future preview tag would be `desktop-v0.4.6-rc.5`.

Area: Vocabulary form and pure staging helper, existing settings persistence,
desktop release inputs, notes, focused checks and one Windows CPU package tree.

## Constraints and alternatives

- No passive correction learning, editor/clipboard capture, permanent history,
  new network path, model loading or microphone recording.
- The form stages a manually entered pair in the existing dictionary draft.
  Existing Save, Cancel and Reset behavior remains authoritative. Review-to-Settings
  IPC is deferred because it would introduce another private-text data path.
- Preserve current-main security pins and the full native payload/license gate.
  Reuse the existing reviewed Python 3.14.10 environment; do not create another
  environment or binary copy for convenience.
- One coordinator owns storage: at most 5 GiB additional working output, at least
  10 GiB free on the output volume. Recheck before building or copying archives.
- Keep local checks headless and targeted. No app windows, screenshot loops,
  Android builds, emulator, installed-app change, public push, tag or release.

## Acceptance and verification

- Valid names, terms and number-format pairs append without altering prior draft
  text; duplicate or malformed pairs are rejected with input retained. The UI
  callback performs no persistence. Save/Cancel/reset retain their existing path.
- Focused helper/callback checks accept valid input and reject representative
  invalid input; adjacent settings, privacy, delivery, clipboard, spacing, instance,
  packaging-notice and CI-contract checks pass without a real Tk root.
- Project/module versions and preview notes consistently identify unpublished RC5.
- The canonical Windows build accepts an explicit existing Python path and rejects
  an unavailable path before build work. One CPU output tree contains checksums,
  notices, no recognition weights or optional CUDA payloads, and passes permitted
  frozen CLI checks. Receipt identity is tied to the exact source revision.
- Independent review inspects the feature, merge resolutions and release inputs.

Commands use `$BuildPython` for the existing reviewed environment and `PYTHONPATH`
for this checkout. Focused tests select the affected headless modules explicitly;
`./packaging/build.ps1 -PythonPath $BuildPython` is the build entry point. Exact
executed commands and results are recorded below, not inferred from exit codes.

## Ready queue

| Work | Owner | Status |
| --- | --- | --- |
| Current-main and release authority | Luna scout, coordinator integration | RC4 confirmed; main merge committed |
| Explicit correction staging | Luna runner | Source prepared; helper and callback checks passed |
| Merge/release input reconciliation | Sol worker | Source resolved; full package closure pending |
| Release notes, pause and resource budget | Coordinator | Preparing local RC5 candidate |
| Independent review | Sol reviewer | Complete; selected-interpreter notice defect fixed and regression checked |

## Verification evidence

Headless checks on the prepared tree: 212 passed in the explicitly selected
vocabulary, settings, config, privacy, CI-contract, instance, spacing,
delivery-cancellation and packaging modules; 54 mocked clipboard checks passed
(the two real process lifecycle tests were deliberately excluded). Reports are
local under `.grok/verification/rc5/`. No UI opt-in was used.

PowerShell parsing passed. A missing `-PythonPath` was rejected with the expected
message before creating `build` or `dist`. The notice collector now follows the
selected interpreter's `purelib`, verified with both a present and absent
environment while a conflicting checkout environment exists.

The local Windows CPU package and frozen CLI checks are still pending. Headless
test results do not establish actual Tk interaction or native device behavior.

The first executable build completed, but its notice gate rejected two Microsoft
runtime DLLs selected from the host JDK on PATH. This is a failed package, not
release evidence. The spec now explicitly selects both DLLs from the selected
Python base runtime; their existing manifest pins remain unchanged. The base
runtime bytes match the reviewed Python archive. All 36 affected packaging/media
checks passed, including valid inputs and each missing-DLL failure. A rebuild
must prove the collected bytes and complete the full notice gate.

## Remaining broader gates and stop

Actual Tk focus/undo/save/cancel interaction, pointer drag cancellation, complete
Windows UI Automation and screen-reader support, microphone/editor/device tests,
mixed DPI and other desktop platforms remain unverified. Existing native-shell
gates are not waived. Headless checks and a package build cannot close them.

Stop before public push/tag/release. Deliver the candidate source/package identity,
actual checks, storage usage and open gates for the next explicit decision.
