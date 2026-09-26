# Android alpha20 release readiness

## Goal

Prepare the current hardened alpha20 candidate for a bounded signed preview,
with exact-source verification, honest release notes and an explicit remaining
publication checklist. This is not a claim that the complete A–M redesign is done.
The user requested progress toward release on September 26, 2026 and subsequently
authorized following this bounded candidate through PR, checks, merge and release.
The broader redesign does not enter the release scope implicitly.

## Area and ownership

Android source/build/tests, Android release workflow and documentation only.
The owning checkout is `android-keyboard-hardening` on
`codex/android-polish-alpha20`. Root owns integration, all build/emulator runs and
release documentation. Independent agents audit release policy, evidence and the
bounded uncertain-dictation-insertion contract; they do not mutate remote state.

## Constraints

- Freeze new feature work; fix only demonstrated release blockers. Do not pull
  the prepared G controller or Tools redesign into this preview implicitly.
- Preserve the existing dirty work, stable preferences/model identities, offline
  operation, sensitive-field protections and desktop/mobile boundaries.
- Do not introduce automatic uncertain-insertion retries, passive capture,
  clipboard inspection, telemetry or new runtime network permissions.
- Preview readiness uses the repository's automated release policy. Unperformed
  phone, named-third-party and assistive-technology work remains unverified and
  does not become a false final-redesign completion claim.
- Keep signing material in the protected release workflow. Local unsigned/debug
  builds are not distributable signed releases. Do not create a tag, publish,
  merge or dispatch protected signing without release authorization.

## Acceptance

1. Independent review has no unresolved privacy/correctness release blocker.
2. Tooling, JVM, lint, the full ordinary API 35 app suite, isolated lifecycle host
   and unsigned release compilation pass against the recorded candidate.
3. Packaged release permissions/components/assets match the offline production
   boundary; test fixtures and debug-only components are excluded.
4. Version/code/tag/release-note metadata agree. Release notes describe verified
   changes and do not imply completed A–M or physical-device acceptance.
5. The remaining remote sequence is explicit: reviewed committed revision,
   exact-revision full Android CI on main/manual run, immutable
   `android-v0.1.0-alpha20` tag at that green main SHA, protected signing,
   signer/package/version/alignment plus signed upgrade/reinstall preservation,
   then authorized prerelease publication.

## Verification

From the owning checkout root:

```powershell
& 'C:\Users\unknown\Projects\Utterleaf\.venv\Scripts\python.exe' -m unittest discover -s mobile/android/tools -p 'test_*.py'
```

From `mobile/android`, run the app suite and independent host sequentially on the
same disposable emulator, preserving each report before the next invocation:

```powershell
.\gradlew.bat testDebugUnitTest lintDebug connectedDebugAndroidTest assembleRelease --no-daemon
.\gradlew.bat -PincludeLifecycleHost=true :app:installDebug :lifecycleHost:connectedDebugAndroidTest :lifecycleHost:lintDebug --no-daemon
```

Archive logs, exact APK hashes, source snapshots, JVM/connected/lint results and
manifest/packaging inspection in `.grok/validation`. Restore the previous IME.
An unchanged external release does not establish CI/signing success.

## Initial repository state

- Remote `main`: `be4f11779d29b11d5b3451fee2c23fe4d327acc3`, an exact ancestor
  of local HEAD `4458fed`; six local alpha20 commits plus the preserved dirty
  hardening/I-J increment. No rebase is needed against that observed main.
- No remote `codex/android-polish-alpha20` branch, alpha20 PR or alpha20 tag was
  found. Published Android preview remains alpha19. These are read-only remote
  observations, not authorization to create or publish resources.
- Latest local I/J debug APK:
  `a7135e6fb4ca2afa246752172ca90aa2d55a103c15ea90a420bf8fb1152ad3ca`.
  Its final layout has only focused verification so far; prior full-suite and
  release builds belong to earlier recorded candidates.

## Non-goals and stop

No desktop work, new dictation state machine, Tools redesign, model expansion,
stable-channel release or speculative physical acceptance. Stop source changes
when named local gates and review pass; report the precise remaining authority
or CI/signing/publication step instead of calling local checks a published release.

## Confirmed release blocker — uncertain dictation insertion

The independent review found that `VoicePanel.insertReview` offers a retry after
a Boolean failure, although both IMEs collapse a host `commitText` false/throw to
that value. A host may already have changed text. The old automatic-insert test
even models mutation before false and expects a later second insertion. That is
not an acceptable release contract; a changed transcript could still append a
duplicate and must not be used to silently re-arm the same take.

- **Approved scope:** VoicePanel and its focused control tests only. Use one
  per-take Boolean insertion-attempt latch, set before the callback to reject
  reentrancy. False or RuntimeException leaves insertion unconfirmed and disables
  all further insertion for that take, including after local edits or expiry
  extension. Do not store an additional attempted-transcript snapshot.
- **Recovery:** retain the existing selectable review and explicit Android Copy
  action; explain that the user should check the field. No new clipboard reader,
  automatic write or UI row. Clear/new take resets the latch; confirmed success
  retains the normal completion path. No host rollback or speculative retry.
- **Verification:** manual and hold paths, mutate-then-false, throw, repeated and
  reentrant taps, edit/revert/Keep reviewing, selectable recovery, clear/retake
  and subsequent successful insertion. Then repeat affected tests and full
  release gates against the corrected source. Independent review is required.
- **Ownership:** source reviewer becomes the sole writer of VoicePanel and
  VoicePanelControlsTest after the first full candidate run is archived. Root
  integrates/builds; the independent reviewer checks the diff and tests.

The larger G state machine and cross-editor result recovery remain deferred.

## Release verification log — September 26, 2026

The first full local release pass used debug APK
`a7135e6fb4ca2afa246752172ca90aa2d55a103c15ea90a420bf8fb1152ad3ca`.
Tooling passed 25/25; JVM passed 50/50 and lint reported zero errors, 54 warnings.
The ordinary emulator suite ran 234 cases: 233 passed, one failed, none skipped.
`assembleRelease` was not reached; an older release APK is not this candidate.

The failed EmojiImeTest stopped on its initial editor launch, before emoji/raw/
password transitions. Preserved logcat shows the prior test's asynchronous Gboard
restoration overlapping launch. There was no Utterleaf crash. The fixture now
uses the shared stable-selection/restore helper and failure-preserving cleanup,
retains its single show request and assertions, and reports read-only timeout
diagnostics. This is a diagnosed fixture correction, not an unchanged retry.

Original source, test source, APK, reports, logcat and dirty patch are preserved in
`.grok/validation/alpha20-release-20260926/app-first-run`. The uncertain-insertion
fix and fixture correction require focused and full new-candidate verification;
the first run is not a passing release gate.

The corrected insertion/fixture group passed **37/37** emulator cases, no
failures/errors/skips (60.386 test seconds), **50 JVM** tests and lint with
**zero errors / 51 warnings**. Debug APK SHA-256:
`46fe66dd5b34c7c1b8488d84d313d8a7059e255c4a7a05fe822fee683a65e5f5`.
`focused-corrected-run` preserves source, APK and raw reports. Selection:

```powershell
.\gradlew.bat testDebugUnitTest lintDebug connectedDebugAndroidTest '-Pandroid.testInstrumentationRunnerArguments.class=org.utterleaf.voice.VoicePanelControlsTest,org.utterleaf.voice.EmojiImeTest,org.utterleaf.voice.ImeTestReadinessTest,org.utterleaf.voice.TerminalInputTest' --no-daemon
```

Release workflow review also found that same-version reinstall was performed but
not followed by the data-preservation check. It now verifies synthetic preference/
model-storage markers after each candidate installation (upgrade and reinstall),
only when the signed alpha03 predecessor seeded those markers. A static command-
ordering regression covers seed/install/verify/reinstall/verify/launch. Tooling
passes **26/26**. This is workflow verification, not a signed alpha20 run or proof
of every prior-version upgrade or real-model inference after upgrade.

Independent source review passed the per-take insertion contract. The 90-second
warning presentation is source-reviewed; the focused tests exercise expiry
extension, not elapsed wall-clock execution of that warning. A suspected model
observer leak was disproved by the assigned subscription handle and detach-close
path; no speculative observer change was made. Final fixture review additionally
requires the owned Activity to be finished if launch readiness fails before it
can be returned to its caller, while preserving the original failure.

### Final local candidate

The failure-cleanup correction passed independent review. With all product and
test files frozen, the full command above passed **236/236 ordinary API 35
emulator cases**, no failures/errors/skips (384.820 test seconds), **50/50 JVM**
tests, lint **zero errors / 51 warnings**, and `assembleRelease`. The separate
lifecycle-host command then passed **2/2**, no failures/errors/skips (14.856 test
seconds), with host lint **zero errors / 5 warnings**. Tooling passed **26/26**.
Both host cases used the same product debug APK as the ordinary suite. Gboard
was restored; the device is the owned disposable API 35 x86_64 emulator, not a
physical phone or a named third-party-editor campaign.

- Debug APK SHA-256:
  `46fe66dd5b34c7c1b8488d84d313d8a7059e255c4a7a05fe822fee683a65e5f5`.
- Unsigned release APK SHA-256:
  `26e7e9296728e71ad6cafea17f95b02ee9653445137190bb0f89ab6d788af4c0`.
- Release identity: `org.utterleaf.voice`, `0.1.0-alpha20`, code **20**,
  min SDK 26 / target 36, ARM64 + x86_64, 11,569,761 bytes.
- Packaged manifest: non-debuggable, only `RECORD_AUDIO`, no Internet permission,
  backup and cleartext disabled, the expected three Activities and two
  permission-protected IMEs, no instrumentation/provider/receiver/debug host.
  Release assets are only notices/licenses and Obtainium configuration: no model
  or audio fixtures. DEX inventory excludes the debug Activity classes and
  test/lifecycle-host packages. Unsigned APK passes 16 KB / 4-byte ZIP alignment.
- `app-final-run`, `host-final-run`, `package-final-run` and
  `tooling-corrected.log` under `.grok/validation/alpha20-release-20260926`
  retain exact source/APKs, raw results, hashes, manifest/DEX/ZIP inspection and
  cleanup proof. Earlier failed and focused runs remain separate.

The local release-preparation contract is satisfied; source editing stops here.
These checks do not establish a protected signature or publication. At the end of
the local verification pass, no new commit, push, PR, merge, tag, signing dispatch
or release had been performed. Alpha19 remained the published preview. The broader A–M release gate, physical
usability, G recovery, replacement Tools and final accessibility remain open.

### Promotion authorized — September 26, 2026

The user has authorized following the candidate through release. The remote
preflight reconfirmed main at `be4f11779d29b11d5b3451fee2c23fe4d327acc3`, with
no alpha20 branch, PR or tag. The intended sequence is the checklist below;
source is frozen and the release PR/checks may proceed. Independent offline
signing-key backup confirmation is still pending and holds signing/publication.

### Remaining promotion checklist

1. Remote promotion/publication is authorized. Obtain confirmation of the
   independently protected offline signing-key backup before signing. Do not
   request key bytes or passwords. Missing confirmation holds signing/publication.
2. Review/commit the intended Android changes while preserving unrelated dirty
   user work; push/open the authorized PR. PR checks are the fast path only.
3. Merge only after required review/checks, then obtain the full successful
   `android.yml` main/manual run for the exact release SHA and its retained
   `Android-release-input`. Local APKs are not substituted for that artifact.
4. At that green main SHA create immutable `android-v0.1.0-alpha20`; verify
   package/version metadata and tag/run SHA equality before proceeding.
5. With publication authority and backup confirmed, dispatch the protected
   `android-release.yml` from main with that tag/run. This workflow signs,
   verifies signer/package/version/alignment, checks signed alpha03 upgrade plus
   same-version reinstall preservation, and **publishes** the prerelease.
6. Verify published public assets/checksums/version/certificate and update the
   roadmap/download links only after actual success. Synthetic markers do not
   establish real-model inference after every upgrade or live Obtainium use.
