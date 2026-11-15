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
| Merge/release input reconciliation | Sol worker | Reviewed runtime selection fixed; rebuilt package passed full closure gate |
| Release notes, pause and resource budget | Coordinator | Local archive prepared; Android paused; publication and target gates remain open |
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

Headless test results do not establish actual Tk interaction or native device
behavior.

The first executable build completed, but its notice gate rejected two Microsoft
runtime DLLs selected from the host JDK on PATH. This is a failed package, not
release evidence. The spec now explicitly selects both DLLs from the selected
Python base runtime; their existing manifest pins remain unchanged. The base
runtime bytes match the reviewed Python archive. All 36 affected packaging/media
checks passed, including valid inputs and each missing-DLL failure. A rebuild
proved the collected bytes and completed the full notice gate.

## Local package receipt

Package source: `0175d5735a30db5ee902651b3519bd1a3fb63d2c`. Later documentation
updates do not change this artifact's source identity. The canonical build exited
zero, produced notices for 48 packages and passed the complete native hash/license
and media gates. Both collected Microsoft runtime DLLs match the original reviewed
Python pins. No pins were relaxed to admit the host JDK's copies.

The four frozen CLI cases passed using an isolated APPDATA profile and offline
environment: help, prose cleanup (`um we should ship it` becomes `We should ship
it.`), spoken list formatting, and missing polish input rejected with exit 2.
No Settings window, doctor/device enumeration, microphone, recognition model,
emulator or installed-app change was used.

Local archive: `dist/Utterleaf-windows-x64-cpu.zip`, 114,996,239 bytes, SHA-256
`7c1ef41c654a38326b05feba8b5d10cd67a52fcd8dc392d0737ada5961090968`.
All 620 archive entries match the executed package's hashes. Its sibling `.sha256`
is ready. Detailed file hashes, CLI results, source identity, adverse first-build
log and storage read-back stay local under `.grok/verification/rc5/`.

Executed commands, with `$BuildPython` set to the reused Python 3.14.10 environment:

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& $BuildPython -m pytest tests/test_vocabulary.py tests/test_settings.py tests/test_config.py tests/test_privacy.py tests/test_ci_workflow.py tests/test_settings_instance.py tests/test_dictation_spacing.py tests/test_delivery_cancellation.py tests/test_packaging_media.py tests/test_packaging_notices.py tests/test_packaging_runtime_notices.py --junitxml=.grok/verification/rc5/focused.xml -q
& $BuildPython -m pytest tests/test_windows_clipboard.py -k 'not native_job_close and not native_abrupt_parent' --junitxml=.grok/verification/rc5/clipboard.xml -q
& $BuildPython -m pytest tests/test_packaging_runtime_notices.py tests/test_packaging_media.py --junitxml=.grok/verification/rc5/runtime-selection.xml -q
$env:UTTERLEAF_BUNDLE_CUDA = '0'
.\packaging\build.ps1 -PythonPath $BuildPython
& $BuildPython .grok/verification/rc5/verify-package.py
```

The final spec change received a fresh independent review with no material
finding. Its valid-input and each missing-DLL test passed before rebuilding.
Counts above overlap because affected packaging checks were rerun after the fix;
they are not a distinct-test total.

Storage read-back: 96,346,120-byte build scratch, 235,479,191-byte unpacked package,
114,996,239-byte archive, and a 918-byte test profile remain. Archive retention is
for review and potential delivery. Automatic approval review rejected native
PowerShell deletion of the temporary build, unpacked package and test profile,
with only `blocked by policy` supplied as the reason. No alternate deletion was
attempted. These disposable outputs remain until authorized cleanup can run.
C: had 91,823,816,704 bytes free after archive creation, above the 10 GiB reserve;
measured new output remains below 0.5 GiB and no environment was duplicated.

This is an unsigned, unpublished Windows-only local candidate. No hosted CI,
macOS/Linux candidate, archive installation, physical-device acceptance or public
push/tag/release was performed. Expat 2.9.0 and SQLite 3.50.4 advisory limits remain.

## Remaining broader gates and stop

Completion audit, November 15:

| Requirement | Evidence and remaining work |
| --- | --- |
| Modern desktop presentation and simpler CI | Prepared source and prior visual review are retained; display tests require explicit opt-in, PR checks remain headless, and release gates retain six named native jobs. Current actual interaction remains open. |
| Complete text in the intended field | Current-main clipboard receipt and cancellation fixes are included; 54 mocked clipboard cases and adjacent delivery checks passed. Browser, rich-text, terminal, elevated-field and real microphone acceptance remain open. |
| Explicit recurring corrections | The manually entered Vocabulary form and draft helper pass success, duplicate, malformed-input and no-persistence checks. The existing dictionary editor keeps rules inspectable and removable. Actual Tk Save/Cancel/undo/focus acceptance remains open. |
| Low effort and accessibility | Existing one-key start/stop, cancellation and short-lived recovery are retained. The known Tk UIA defect is unresolved; the native shell remains an isolated proof with complete pages, other surfaces and assistive-technology acceptance still required. No accessibility clearance is claimed. |
| Understandable privacy | Existing local processing, download controls and two-minute memory-only recovery remain; privacy checks passed. No passive learning, ambient capture or permanent transcript history was added. |
| Desktop release preparation | Source, notes, unsigned Windows CPU ZIP, checksums and headless frozen receipts are ready. Hosted exact-revision CI, target acceptance, signing decision and public actions are not complete. macOS/Linux packages require native runners. |
| Android pause and platform isolation | No Android worktree changes or builds were made. The desktop diff's earlier Android CI changes and roadmap correction were removed from its final tree and preserved as a local patch. No new Android schedule will ship with this desktop change. |

The Android baseline removal is tied to main `056cb49`: both
`.github/workflows/android.yml` and `docs/mobile-roadmap.md` match it exactly.
The deferred patch is `.grok/verification/rc5/deferred-android.patch`, SHA-256
`88bbd3c2a8c980e82c1512d8ec0cf5b09aa58aff62ee3209065fd74551c5002b`;
its source commits remain in history. Twelve focused CI-contract/repository-boundary
checks passed after the isolation fix. No package source or packaged file changed,
so the Windows archive receipt above still applies to its recorded source.

PR #62 was read back as open at remote head `0fb5aac3`, before these local commits;
its published description still identifies RC3. The remote head is an ancestor
of the prepared local branch, so a future authorized update can be a normal push.
No push or PR mutation has occurred. A replacement title/body is prepared locally
under `.grok/verification/rc5/` and must be bound to the approved branch revision.

Actual Tk focus/undo/save/cancel interaction, pointer drag cancellation, complete
Windows UI Automation and screen-reader support, microphone/editor/device tests,
mixed DPI and other desktop platforms remain unverified. Existing native-shell
gates are not waived. Headless checks and a package build cannot close them.

Stop before public push/tag/release. Deliver the candidate source/package identity,
actual checks, storage usage and open gates for the next explicit decision.
