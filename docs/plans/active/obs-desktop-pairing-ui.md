# Desktop OBS pairing setup

September 13, 2026. Continue `feat/obs-enrollment-flow` after the reviewed native
checkpoint `15e1c77` in draft PR #36. The full OBS audio goal remains in the
[enrollment](obs-native-enrollment.md) and [audio](obs-audio-design.md) plans.

## Goal and area

Let Windows users explicitly import, replace, inspect and forget their desktop
OBS pairing from Speech & privacy, in one separate compact dialog. Preserve the
five Settings destinations. Display a saved local pairing as saved, never as a
verified connection or live transcription readiness. The native plugin remains
an unpublished development component; the dialog must state that live OBS
transcription is still in development.

Area: new `utterleaf/obs_pairing_ui.py`, the existing Settings entry/close path,
desktop store owner support, focused store/UI tests and corresponding docs.
Native TaskDialog acceptance runs independently against synthetic state, with
no consumer OBS instance or store.

## Constraints and observable acceptance

- Opening Settings does not open a pairing store. Only explicitly opening the
  Windows pairing dialog may create its private directories/owner sentinel.
  The dialog worker claims a protected noninheritable share-zero owner file in
  the fixed desktop pairing directory, independent of configuration profiles.
  No automatic repair, key generation, network, capture or model loading occurs.
- Keep storage/key work on one joined or retained non-daemon worker; Tk stays on
  its owner thread. Hold the store/owner until worker teardown. Queue only safe
  outcomes and booleans; wipe loaded capability buffers, never display/log/copy
  keys or raw exception/native path data. Imports use the existing validated
  store; no format reimplementation.
- File selection and confirmation precede mutation. Initial import and explicit
  replacement are distinct; explain that verified import removes the selected
  transfer file when possible. Report saved-but-transfer-remains separately.
  Cancellation before commit preserves prior pairing and transfer; cancellation
  after commit must report saved state. Postcommit uncertainty requires explicit
  status reload and must not claim rollback.
- Forget confirms removal of this desktop copy only, explains that copies remain
  authorized until OBS Forget/Replace, and preserves preferences, models and
  transcripts. Failed deletion does not claim success. Corrupt/inaccessible
  state stays an error; allow explicit refresh/forget, not silent replacement.
- One child dialog per Settings window. Escape, window close and parent close
  signal cancellation and wait asynchronously for worker teardown. If close
  overlaps a committed/uncertain mutation, keep its outcome visible for Close
  acknowledgement. Do not destroy the parent with a live pairing worker.
- Use the existing theme, readable status/actions, responsive wrapping and
  keyboard focus. Test normal/compact sizes and enlarged fonts with rendered
  fixtures. Physical scaling/assistive-technology and actual OBS UI acceptance
  remain separate.

## Verification

From the owning worktree, use the original `.venv/Scripts/python.exe` with
`PYTHONPATH` set to this worktree. Run focused pairing-owner/store/UI and Settings
tests first, then affected privacy/configuration/boundary checks. Use disposable
Windows roots and synthetic capabilities for persistence, second-process owner,
cancel/reset/forget and real-Tk integration; no consumer pairing or microphone.
Capture the dialog in normal/compact/error states and inspect the actual images.
Independent review reads source, diff, contract and test/render evidence.

## Implemented source and evidence

`ObsPairingDialog` now opens lazily from Speech & privacy on Windows and retains
one worker/store owner until close. Normal and compact dark layouts keep status
and cancellation together in the top card; a scrollable body and fixed footer
preserve access with longer messages and enlarged text. Unexpected operation
failures mark the saved state unknown and require explicit Refresh; only a typed
precommit cancellation claims that the old pairing was preserved. Parent close
waits for storage teardown and leaves committed outcomes visible for acknowledgement.

The desktop store now exposes `claim_owner()` using the protected, noninheritable
share-zero `obs-pairing-owner-v1.lock`. Its six real Windows tests include actual
child-process contention/succession and noninheritance, plus unsafe ACL, nonempty
sentinel and reparse refusal. The larger owner/storage/privacy bundle passes 125
tests. The integrated ten-module setup/settings/store/privacy/configuration/backup/
boundary bundle passes **204 tests with no skips in 33.28 seconds**. After the
final unknown-state and status-card adjustment, all **23 UI tests** pass again
in 5.14 seconds. Tests include disposable actual DPAPI import, dialog reopen and
Forget while preserving unrelated files, worker cancellation on both sides of
commit, parent-close waiting, startup failure, lazy/singleton entry and Settings
reset/discard isolation. Test fixtures that render transient dialogs map their
parent before measuring geometry; hidden-window dimensions are not layout evidence.

Exact local commands from the owning worktree:

```powershell
$py = "C:\Users\unknown\Projects\Mindict\.venv\Scripts\python.exe"
$env:PYTHONPATH = (Get-Location).Path
& $py -m pytest tests/test_obs_pairing_ui.py tests/test_obs_pairing_owner.py tests/test_obs_pairing_store.py tests/test_settings_ui.py tests/test_settings.py tests/test_config.py tests/test_privacy.py tests/test_backup.py tests/test_backup_store.py tests/test_repo_boundaries.py -o addopts='' -q
& $py -m pytest tests/test_obs_pairing_ui.py -o addopts='' -q
& $py tests/capture_settings.py
& $py native/obs-plugin/tools/test_native.py --toolchain "C:\Users\unknown\.local\llvm-mingw-20260616-ucrt-x86_64" --output "C:\Users\unknown\Projects\Mindict\.grok\obs-enrollment-flow\setup-native-final" --build "C:\Users\unknown\Projects\Mindict\.grok\obs-enrollment-flow\build-a" --headers "C:\Users\unknown\Projects\Mindict\.grok\obs-native-build\headers" --ui
```

Settings capture passes. The actual desktop dialog captures at
`.grok/obs-enrollment-flow/desktop-ui-captures/` cover unpaired, paired, compact
uncertain state and enlarged text; root inspected normal/compact/enlarged images.
The revised error card keeps its explanation visible instead of placing it below
the setup instructions. Native dialog acceptance passes through real Windows
TaskDialog activation and targeted Escape, with three fixture captures and no
mutations or OBS startup; the native driver passes 29 top-level commands. Three
existing test-only heap-shim link warnings remain. Native and desktop fixture
checks do not establish actual OBS integration, physical scaling/input or assistive
technology. Final independent desktop source/test/render review is clear. The
reviewer reran 29 focused UI/owner tests and a 187-test related bundle against
the final source, and directly checked mapped modality, Escape and an ambiguous
post-mutation close result. The latter probes supplement the committed tests;
they do not establish physical assistive-technology acceptance. Separate native
fixture/driver review is also clear, including all three captures and current
source/artifact/nested-receipt hashes. The final combined local evidence is
`.grok/obs-enrollment-flow/desktop-setup-verification.json`.

CI [34758907354](https://github.com/RioPlay/utterleaf/actions/runs/34758907354) passes
all five desktop jobs at `15e1c776821abf14abfe6bec7786c8c133d867f7`, with release
skipped. That is the earlier linked native checkpoint; it does not validate this
desktop setup follow-up; its own CI remains pending.

## Non-goals and stop

No Android edits, plugin installation/publication, OBS launch, connection/Arm,
audio pipe, PCM, live recognition, new Settings preference or global redesign in
this step. Those remain required subsequent components, not removed scope.
Stop changing this setup increment when the named checks and independent review
pass; preserve its evidence, then continue real frontend/connection/Arm/audio
integration rather than declaring live OBS complete.
