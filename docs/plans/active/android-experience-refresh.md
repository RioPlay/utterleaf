# Android capability and experience plan

## Goal

Turn Utterleaf Android into a polished, privacy-first system keyboard that is
calm and reliable for ordinary typing while keeping fast editing, terminal,
navigation and offline-dictation workflows available on demand.

The priority order is typing responsiveness, cross-editor correctness, privacy,
state safety, one-handed use, editing speed, offline dictation and progressive
disclosure. Visual polish follows those invariants.

Status remains in the [mobile roadmap](../../mobile-roadmap.md). This plan
reconciles the published alpha21 baseline with the longer-running
[keyboard rebuild](android-keyboard-rebuild.md); it does not make release or
physical-device claims from emulator results.

Routine Android progress and preview releases follow the roadmap policy: they do
not require a new physical-phone, live third-party-editor or assistive-technology
campaign. A final redesign-completion claim still requires a recorded
compatibility, performance and accessibility audit. Unperformed work stays
`Not run` and limits claims; it is never converted into inferred success.

## Area and ownership

- Android only: `mobile/android/`, Android documentation and Android release
  evidence. Desktop source, tests and release artifacts remain separate.
- Editor/session policy: `EditorCapabilities.kt`, `KeyboardIme.kt`,
  `VoiceIme.kt`, `EditorActions.kt`, `PasswordManagerKey.kt` and focused tests.
- UI slices: one writer owns `TypingPanel.kt` and its geometry tests at a time.
- Do not edit `DeviceTest.kt` and `PrivacyCoreTest.kt` in parallel with other
  Android work. Use the AGENTS.md Aden sequence before each code slice.

## Product invariants

1. Ordinary typing stays on the critical path; expensive context, suggestion,
   model and rendering work stays outside key rendering and commit dispatch.
2. Advanced capability does not imply permanent chrome. Every visual addition
   needs measured interaction value and stable geometry.
3. Field, application, hide/show, orientation and process boundaries must
   invalidate transient modes and stale callbacks. Sensitive transitions always
   reset them. Existing generation/session checks prove only their named cases,
   not every lifecycle edge.
4. Editor metadata is interpreted into one session snapshot. UI and synchronous
   actions consume it rather than reimplementing `EditorInfo` policy; delayed
   dictation/draft delivery also re-resolves current metadata as a fail-closed
   eligibility check after its generation guard.
5. Fields that Android metadata positively identifies as sensitive collect no
   text, learning or history, minimize context inspection and disable dictation
   by default. Android metadata cannot identify every sensitive target, so an
   unrecognized field is not documented as proven non-sensitive. The keyboard
   has no clipboard-preview or clipboard-history surface; future work must not
   add one implicitly.
6. Explicit preferences remain local and stable. Reset restores documented
   defaults without deleting models or other user data.
7. Unsupported or broken editors fail locally without speculative retries,
   duplicated text, stale-target writes or keyboard-height changes.
8. No cloud dependency, telemetry, passive clipboard read, ambient recording or
   unverified model loading is introduced.

## Current baseline

| Milestone | Current source status | Open gate |
| --- | --- | --- |
| A — IME foundation | Central capabilities/actions, minimal sensitive surface, named lifecycle boundaries and fail-closed degraded-editor policy pass the current automated gauntlet. | Physical hardware configuration/OEM and named third-party behavior remain unverified; see scoped evidence below. |
| B — testing | Native cells now carry scoped Pass/Partial records; P1 archives a reproducible pre-visual emulator baseline. | Named real-application matrix, real-host dictation insertion timing and matched post-change performance comparison. |
| C — daily keyboard | The current working tree has themes, one-hand and purposeful landscape/split layouts plus the clean-room one-row daily surface and continuous bottom row recorded below. | Integrate the reviewed slice; matched post-change performance and final device/accessibility evidence remain part of the redesign gate. |
| D — suggestions | Fixed geometry/off-main-thread work; literal email/URI suppression has live native tests; generation/render timing recorded in P1. | Live numeric/search/unsupported-editor and named-host evidence beyond resolver/component policy. |
| E — Tools | Edit, navigation, modifiers, Fn and terminal surfaces exist. | Validate category/rail design without slowing mixed modifier-navigation tasks. |
| F — editing | Existing gestures plus owned-draft grapheme navigation/deletion, including interior combining/ZWJ caret positions, pass automated tests. | Host RTL, line crossing, punctuation and broader named-host acceptance. |
| G — dictation | Local review-first capture and stale-session safeguards exist. | One authoritative internal state machine and recoverable stale-target result flow. |
| H — setup | Keyboard/voice readiness separated; import progress/failure survives Activity recreation and preserves installed data. | Final complete readiness/task acceptance; Activity recreation is not process-death proof. |
| I — models | Verified imports/checksum readiness now have readable English model names, decimal-MB sizes/resource tradeoffs and explicit technical-details disclosure. | Standalone voice landscape/large-font reachability and model-specific physical performance remain unverified. |
| J — settings | Search, staged Apply/Cancel, computed Customized state and model-preserving individual/category resets pass the scoped checks below, including the final category-row correction. | Broader accessibility and real font-scale/phone evidence remain open. |
| K — recovery | Local fail-closed feedback avoids layout jumps. | Action-specific What/Affected/Next messages. |
| L — accessibility | Automated semantics, contrast, geometry and orientation checks exist. | A final audit record is required. Physical and live assistive-technology evidence remains optional for routine releases; absent evidence limits claims. |
| M — release | Offline/privacy/signing/upgrade gates are established. | Compatibility and performance gates below must pass before redesign completion. |

## Implemented in the current working tree — C daily-surface clean-room reset

**Goal** — Restore a calm, familiar daily keyboard: one compact action/suggestion
strip, a continuous bottom row with no dead slot, and advanced editing or terminal
controls available only when requested.

**Area** — `TypingPanel.kt`, its focused geometry/toolbar instrumentation tests,
and the IME root background only if inset validation proves a separate system-area
seam.

**Constraints** — [FUTO Keyboard's public source mirror](https://github.com/futo-org/android-keyboard)
is behavioral research under its own source-first license, not an implementation
source. Do not copy its code, assets, labels,
constants, layouts or theme values. Preserve Utterleaf's privacy policy, editor
session guards, preference IDs, dynamic action behavior, typing path and specialist
Tools capabilities. Sensitive fields remain minimal.

**Acceptance** — Ordinary portrait and landscape use one 48dp daily strip; Tools
and Edit remain one tap away; suggestions occupy stable inline geometry; advanced
destinations remain reachable through Tools; every non-split bottom-row region is
an actionable key; only the explicit split channel may be inert; key targets and
sensitive-field profiles retain their contracts.

**Verification** — Run `python -m unittest discover -s mobile/android/tools -p
test_*.py`, `gradlew testDebugUnitTest`, then the focused connected classes
`DailyToolbarContractTest`, `KeyboardSpacingTest`, `KeyboardGeometryTest` and
`CompactLayerTest`. Follow with the affected editing/lifecycle bundle and
`lintDebug`; capture portrait and landscape emulator renders for human review.

**Non-goals** — Prediction/swipe input, a new dictation state machine, wholesale
Tools navigation redesign, or claims about physical-device comfort.

**Stop** — Stop when the focused contract and affected regression bundle pass,
renders show no dead bottom-row hole or duplicated daily chrome, documentation
matches the result, and remaining device-only validation is stated explicitly.

### Working-tree evidence — September 27, 2026

- The ordinary daily surface now uses one 48dp row for Tools, Edit, three stable
  inline suggestion slots and Dictate. Undo/Redo, clipboard, Emoji, draft and
  specialist keys moved behind the existing explicit Tools/Edit routes. Sensitive
  fields keep their separate minimal row.
- The non-split bottom row is fully assigned to mode switch, comma, Space, period
  and the dynamic editor action. Split landscape retains only its documented
  center channel. A geometry regression covers portrait/landscape and all three
  alignment choices, rejecting inert non-split cells or discontinuities.
- The Tools hub remains no taller than the default number-row keyboard. Caps is
  in its header; Edit, Emoji, private draft/password manager, Extra Keys, number
  row, accents/compose, alignment and letter layouts remain explicitly reachable.
- Android tooling passed **26/26**; JVM tests passed **50/50**; the affected
  emulator bundle passed **76/76**; the disclosure-transition group passed
  **24/24**; and lint reports **0 errors / 58 warnings**. A fresh API 35 portrait
  render was inspected and contains no bottom-left void or second action row.
- Two complete **238-test** emulator runs each reached **237/238** with different
  one-off live-fixture failures: selected-text suggestion rejection in the first
  run and raw-terminal ASCII delivery in the second. Each exact failed case passed
  immediately in isolation; the second full run also passed the first case. These
  failures remain recorded as test-environment timing evidence, not converted into
  a green full-suite claim. No physical-device usability claim is made.
- PR [#64](https://github.com/RioPlay/utterleaf/pull/64) merged the daily-surface
  reset as `3545a8e`. Exact-main run
  [36341409976](https://github.com/RioPlay/utterleaf/actions/runs/36341409976)
  reproduced the selected-text case: Android's selection callback could trail the
  host selection while a completion was tapped. The follow-up now confirms the
  connection's current selected-text state before any destructive completion edit
  and fails closed on an unreadable check. Tooling **26/26**, JVM tests, lint, the
  exact regression, and the complete **18/18** suggestion class pass locally. A
  subsequent 238-case local run passed the original regression but stopped at
  **237/238** on a different default-IME readiness fixture that passed in the
  preceding class run. PR #65 merged the safeguard at `eb4cfd2`; exact-main run
  [36344294106](https://github.com/RioPlay/utterleaf/actions/runs/36344294106)
  then passed the complete emulator privacy/inference, packaging and release-input
  gate on its failed-job rerun. The first attempt's two unrelated live timing
  failures each passed exact isolated reruns. This closes the bounded integration
  gate, not the physical-device or final A–M redesign gates.

## Milestones

### A — IME foundation

- Create one immutable `EditorCapabilities` value for field kind, sensitivity,
  multiline/numeric/email/URI/phone/search modes, primary action, expected complex
  editing, suggestions, selection, dictation and clipboard policy.
- Render Enter, Search, Send, Go, Next and Done from that value; retain explicit
  Previous compatibility and newline fallback for unsupported/no-enter actions.
- For fields positively identified as sensitive, disable suggestions,
  learning/history, nonessential surrounding-text inspection and dictation;
  clear transient tools; and emit no field text in diagnostics. No clipboard
  preview exists or is added by this plan. Explicit Paste may remain available
  without a keyboard-side clipboard read; Copy/Cut remain blocked in password
  fields.
- Define reset behavior for new editor/application, hide/reopen, rotation,
  process recreation, sensitive transition and hardware keyboard changes.
- Track expected metadata support separately from observed `InputConnection`
  failures, and degrade without retries that can duplicate or cross-target text.

### B — testing and performance foundation

- Maintain repeatable native fixtures and real-application records for a standard
  field, Chrome, Firefox, Signal, Google Messages, Gmail, Google Docs, Termux,
  WebView, a password manager, numeric/email/URL/search fields, multiline text and
  Next/Done forms.
- For each target cover typing, deletion/hold, cursor/selection, clipboard actions,
  Enter/action, dictation, suggestions and Tools reset behavior.
- Record keyboard-show, press-feedback, press-to-commit, candidate generation and
  render, Tools switching, dictation start/process/insert, memory and sustained
  frame behavior before and after major milestones.
- Use the [compatibility and performance evidence template](../../android-keyboard-compatibility.md).
  Every cell begins `Not run`; a result changes only when its exact environment,
  expected/observed behavior and supporting artifact are recorded.

### C–E — daily keyboard, suggestions and power tools

- Centralize lightweight spacing, radius, typography, surface and state tokens.
  Keep letter, Space, Backspace, action and dictation controls visually primary.
- Prototype persistent versus contextual Cut/Copy/Paste and a compact explicit
  clipboard surface; select the lowest measured interaction cost without passive
  reads or permanent clutter.
- Keep suggestion geometry fixed and context-aware. No expensive suggestion work
  runs during key rendering.
- Tools uses clear Edit/Navigation/Symbols/Fn/Terminal states without separating
  controls that are frequently chorded. Preserve an efficient Ctrl/Alt/Shift rail,
  Esc/Tab, spatial navigation and F1–F12. Define persist/collapse/reset behavior.
- Portrait and landscape are intentionally composed; landscape is not a shrunken
  portrait layout. Every control keeps accessible size, separation and feedback.

### F–G — editing and dictation

- Refine word selection, Select all, cursor/selection drag, Backspace swipe/hold,
  replacement and spacing. Cover field edges, sentence starts, multiline, RTL,
  emoji/surrogates, punctuation and selection across lines before masking defects
  with visual work.
- Present Ready, Listening, Processing and Inserted while implementing explicit
  Unavailable, Initializing, Starting, Stopping, Result ready, Committing,
  Complete, Cancelled and Error transitions internally.
- Bind every take/result to its editor generation. If focus moves, never inject
  into the new target; retain a bounded result only for explicit Copy or safe
  insertion. This is a required contract, not a claim that existing generation
  guards cover every focus transition. Utterling art supplements visible labels
  and controls.

### H–J — setup, models and settings

- Setup answers whether typing is ready, then separately reports microphone,
  installed model and offline-dictation readiness with one direct next action.
- Models are presented as user capabilities and size/tradeoff first; format,
  identifier, checksum and location remain advanced details.
- Keep stable preference IDs while grouping Keyboard, Typing & Gestures, Voice,
  Appearance and Privacy & Advanced. Provide search, modified indicators and
  per-setting reset, plus category reset where appropriate. Preference resets
  never remove models or other user data.

### K–L — feedback and accessibility

- Every failure says what happened, what was affected and what to do next in a
  reserved/status/overlay surface that does not change keyboard height.
- Validate spoken names and states, pressed/selected/toggle semantics, target
  sizes, font scaling, contrast, non-color cues, reduced motion, both orientations
  and one-handed use throughout; finish with a dedicated accessibility audit
  record. Label emulator/automation, physical-phone and live assistive-technology
  evidence separately, leaving unperformed checks `Not run`.

### M — Android release gate

Do not call the redesign complete until the final audit records the named
compatibility matrix, performance comparison and accessibility review; required
supported rows pass or are explicitly documented unsupported with a reason;
sensitive behavior and cross-app state isolation are correct; typing matches the
baseline; dictation cannot target a stale editor; suggestions keep fixed geometry;
power chords remain efficient; landscape is usable; existing editing survives;
and no cloud dependency or telemetry has been added. `Not run` rows prevent the
corresponding verification claim, but do not create a new physical-phone or
third-party-app campaign gate for an otherwise eligible routine preview release.

## Foundation slice — A1 editor capability contract

### Acceptance

- A single metadata-only resolver covers null, raw, ordinary text, all supported
  password variations, multiline, number, datetime, phone, email, URI, filter and
  search fields plus every supported primary action.
- Raw fields receive their explicit restricted profile. Recognized sensitive
  fields disable suggestions, dictation, draft, complex/surrounding-text work and
  Copy/Cut while retaining explicit Paste eligibility. Basic host selection remains
  permitted by policy; that flag alone does not verify sensitive-editor behavior.
  Null and structurally unrecognized metadata use tested conservative
  defaults; this resolver does not claim to detect every sensitive editor.
- `KeyboardIme`, `VoiceIme`, editor actions and password-manager visibility consume
  the resolver; existing UI geometry and preference behavior do not change.
- Finish/hide/destroy clears the voice-only editor snapshot as well as its take.
  This is a source requirement; direct coverage of each callback remains separate
  from the general connected-suite result.

### Verification

From `mobile/android`:

```powershell
.\gradlew.bat testDebugUnitTest --no-daemon
.\gradlew.bat lintDebug --no-daemon
.\gradlew.bat connectedDebugAndroidTest "-Pandroid.testInstrumentationRunnerArguments.class=org.utterleaf.voice.KeyboardEditorContractTest,org.utterleaf.voice.EditorActionsTest,org.utterleaf.voice.SuggestionStripTest,org.utterleaf.voice.PrivateDraftImeTest" --no-daemon
```

Also run `python -m unittest discover -s mobile/android/tools -p test_*.py`.
Run the complete connected suite before merging this privacy-critical refactor.

### Working-tree evidence — September 26, 2026

- `testDebugUnitTest`: 47 tests, zero failures/errors/skips; the new resolver
  matrix contributes seven tests, including raw/unknown action fallback.
- Android release tooling: 17 tests passed.
- `lintDebug`: zero errors and 60 warnings; no warning names a changed
  source file.
- Focused API 35 editor/privacy group: all 23 cases passed in the complete
  software-renderer run across `KeyboardEditorContractTest`, `EditorActionsTest`,
  `SuggestionStripTest` and `PrivateDraftImeTest`, including both new tests.
- Complete software-renderer run: 198 tests, 197 passed, one failed, zero
  errors/skips (270.518 test seconds). The sole failure was
  `ComposeImeTest.completedComposeReplacesUtf16SelectionOnceWithoutClipboardOrSubmit`
  at IME-selection setup, before its editing assertions. Its unchanged isolated
  rerun passed. Real tiny.en and base.en speech-inference tests passed. Preserve
  the distinction between individual-case success and a clean complete suite.
- At the end of this initial A1 run, a clean full-suite gate was still open; the
  later passing combined-candidate run is recorded in the sensitive-surface section
  below. The real-application matrix, hardware-keyboard policy and physical/
  assistive evidence remain open; emulator results do not establish unobserved
  environments or performance.
- First complete-suite attempt on the default-renderer API 35 emulator did not
  complete: 159/198 tests ran, with five cascading failures after the main thread
  stalled in `HardwareRenderer.nSetStopped` and then the renderer finalizer timed
  out. The initial failure preceded the new metadata-transition test; the
  suggestion worker was idle. Logs are retained locally under
  `.grok/validation/editor-capabilities-20260926/native-renderer-first-run`.
  The software-renderer run above used a cold start with `-no-snapshot-load
  -no-snapshot-save -no-audio -gpu software`; this first attempt is not a passing gate.
- On the cold software renderer, the 23-test focused group passed both new tests
  but failed the existing Unicode-delete assertion (22/23 passed). That exact test
  then passed unchanged in isolation. Both runs are preserved alongside the first
  logs as `software-focused-first-run` and `unicode-isolated-rerun`. This is an
  unresolved intermittent observation, not proof of either a source regression or
  a pre-existing test issue. It also passed in the complete software-renderer run.
- The complete software run and unchanged Compose retry are preserved locally as
  `software-full-first-run` and `compose-isolated-rerun` under the same validation
  directory. No editing-action retries or relaxed assertions were introduced.

## Non-goals

- No desktop work, release/version bump, cloud service, telemetry, new permission,
  model format, language engine, prediction/swipe engine or UI-framework rewrite.
- The A1 slice does not redesign alpha20 toolbar geometry or claim physical-phone,
  real-application, TalkBack or Switch Access acceptance.

## Completed slice — sensitive surface and bounded transition proof

First close the integration-test reliability follow-up: make IME setup/teardown
and post-editor-update readiness observable, add case-specific synthetic failure
diagnostics, and verify the affected classes before the sensitive changes. Run
the complete suite on the combined candidate. Do not retry destructive key actions or
claim that isolated passes explain the two intermittent observations above.

### Continuation contract

- **Harness area:** `ComposeImeTest.kt`, `KeyboardEditorContractTest.kt` and a
  small test-only readiness helper if needed. Wait for stable selected-IME state
  after setup/restoration; observe readiness after synthetic editor updates.
  Add case-specific diagnostics. Do not retry input, change production timing or
  relax a behavioral assertion. Verify the affected classes, then the full suite.
- **Sensitive-surface area:** `KeyboardIme.kt`, `TypingPanel.kt` and focused panel/
  live-IME tests. Pass resolved sensitivity into the panel; preserve normal/raw/
  private-draft layouts and preferences. Keep literal Unicode entry, symbols,
  alternate characters, Shift/Caps, Backspace, action, Paste and keyboard switching.
  Hide and reject nonessential advanced surfaces and host-context gestures.
- **Acceptance:** password profiles expose no Tools/Edit/Extra Keys/emoji/voice/
  draft/suggestion entry, even if callbacks are supplied; Paste remains a single
  explicit host command. Normal-to-sensitive lifecycle changes invalidate old
  callbacks and transient state. Named automated transitions are evidence only
  for their actual fixture, not arbitrary third-party applications.
- **Verification:** JVM/tooling/lint, focused harness and sensitive-surface cases,
  existing editor/suggestion/draft/emoji/toolbar regressions, then a clean full
  API 35 suite. Review portrait and landscape sensitive layouts independently.
- **Non-goals/stop:** no general toolbar redesign, new preference, settings reset,
  model/permission/release change, A5 retry policy or hardware-keyboard claim.
  Stop this slice after its checks and independent review pass; leave the broader
  compatibility, performance and accessibility gates explicit.

### Implementation

- `TypingPanel` receives immutable sensitivity from `EditorCapabilities`. Its
  password toolbar contains only Paste, Switch keyboard and the optional configured
  password-manager shortcut. Letters, symbols, held-letter alternates, manual
  Shift/Caps, Backspace and the resolved editor action remain usable.
- Tools/Edit/Extra Keys, emoji, voice, draft, suggestions and host-context gestures
  are withheld. Entry points reject sensitive callbacks even when a panel caller
  supplies them. Refused Space/Backspace swipes are consumed, not reinterpreted as
  accidental typing/deletion. The panel does not request host selection or text.
- Automatic capitalization and repeat filtering are bypassed for literal password
  typing. Neither last-key label nor timestamp is retained; saved preferences are
  unchanged. Normal/raw/private-draft surfaces keep their existing policy.
- Session invalidation disposes the old typing panel, empties suggestion state and
  clears transient controls. The password-manager callback also checks its captured
  session token before launching an application. Explicit Paste remains one host
  menu action, with no keyboard-side clipboard read.

### Remaining lifecycle scope

Panel tests and the named native fixtures below are not proof for arbitrary
applications, process recreation, hardware-keyboard changes or every orientation
transition. Direct portrait/landscape layout renders are not live rotation proof.
Continue that matrix as a separate bounded A4 slice, then the A5 fallback policy.

- Keep ordinary typing, Backspace, the resolved action key, keyboard switching,
  the configured password-manager shortcut and explicit host Paste available.
  Suppress nonessential Tools and emoji entry points, keep suggestions/dictation/
  draft unavailable, and reject forbidden callbacks as well as hiding their
  controls. Do not change normal-field geometry.
- Extend proof that normal-to-password transitions clear layers, modifiers, compose,
  suggestions, drafts and dictation across field/application changes, hide/reopen
  and rotation. These are currently incomplete evidence, not established bugs.
- Use a counting/failing connection to verify no sensitive surrounding/selected
  text reads or Copy/Cut; explicit Paste is one host action with no clipboard read.
- Run focused sensitive-transition tests and the existing editor/action/suggestion/
  draft groups, capability JVM tests, lint and Android tooling tests. Leave A5
  degraded connections, hardware-keyboard policy and visual redesign separate.

### Verification commands

From `mobile/android` (the tooling command above runs from the worktree root):

```powershell
$sensitiveClasses = @(
    'org.utterleaf.voice.ImeTestReadinessTest',
    'org.utterleaf.voice.SensitiveTypingPanelTest',
    'org.utterleaf.voice.ComposeImeTest',
    'org.utterleaf.voice.KeyboardEditorContractTest',
    'org.utterleaf.voice.DailyToolbarContractTest',
    'org.utterleaf.voice.EditorActionsTest',
    'org.utterleaf.voice.EmojiImeTest',
    'org.utterleaf.voice.SuggestionStripTest',
    'org.utterleaf.voice.PrivateDraftImeTest',
    'org.utterleaf.voice.KeyboardGeometryTest',
    'org.utterleaf.voice.KeyboardTuningTest',
    'org.utterleaf.voice.DeviceTest#liveKeyboardEditsAndSurvivesFieldAndVisibilityChanges'
) -join ','
.\gradlew.bat connectedDebugAndroidTest "-Pandroid.testInstrumentationRunnerArguments.class=$sensitiveClasses" --no-daemon
.\gradlew.bat testDebugUnitTest lintDebug connectedDebugAndroidTest --no-daemon
```

### Sensitive-surface evidence — September 26, 2026

- Harness-only verification, before production changes: 6/6 passed. The first
  readiness attempt passed 5/6; the new check incorrectly required Android's
  normalized selection callback to retain a reversed host-selection direction.
  It now compares callback bounds while retaining exact directional host checks
  and all edit-result assertions. No destructive action is retried.
- The combined focused group passed 49/49, zero failures/errors/skips (111.423
  test seconds). Five new panel cases cover literal/manual-case input, zero
  last-key retention, absent advanced callbacks, refused gestures, stale disposed
  controls and portrait/landscape toolbar geometry. Two cleanup-helper cases cover
  all-step execution and primary/suppressed failure preservation.
- Editor action checks reject surrounding/selected/extracted-text reads and
  require exactly one Paste command for each supported password variation.
  The live native fixture verifies typing, stale Paste refusal, voice-to-password,
  password hide/reopen and email/password/raw transitions. These are named cases,
  not a complete cross-application lifecycle proof.
- Independent review found and resolved an eligibility mismatch: password emoji
  browsing is now false in the central resolver as well as guarded by the panel.
  Ordinary literal Unicode/symbol/alternate entry is unchanged. An early full run
  was intentionally cancelled to apply that correction; it is not counted as a
  completed result. The corrected candidate passed **205/205** in the complete API
  35 software-renderer suite, zero failures/errors/skips (270.408 test seconds),
  plus **47 JVM** and **17 tooling** tests. Lint passed with zero errors and 60
  existing warnings. Independent code and documentation review passed.
- A further live native geometry/capture case passed (1/1, 31.443 seconds). Its
  attached password keyboard confirms the minimal toolbar and readable action key.
  An initial unattached synthetic capture did not initialize the action drawable's
  enabled state; that capture issue is not evidence of a live keyboard defect.
  The test-only renderer now initializes and asserts enabled drawable state before
  drawing. All five sensitive-panel cases passed again (1.169 seconds), with
  production unchanged. Corrected portrait and landscape images were visually
  inspected: controls remain unclipped and the action label has its accent fill.
  This is render/layout evidence, not physical one-handed or live-rotation proof.
- Local raw reports are retained under `.grok/validation/sensitive-input-20260926`
  in `harness-first-run`, `harness-corrected-run`, `focused-run` and `full-final-run`.
  `sensitive-live-portrait.png` is the attached native keyboard capture. Direct synthetic
  renders are generated by `SensitiveTypingPanelTest`; they contain only the
  owned keyboard surface, never host text or other applications. Final reviewed
  images are `sensitive-portrait-final.png` and `sensitive-landscape-final.png`.

## Latest completed slice — A4 transient UI lifecycle

- **Goal:** a detached/reopened keyboard returns to its field's baseline surface,
  without stale Tools, modifiers, Caps, compose, alternates, gestures or repeat
  callbacks. Ordinary typing and explicit preferences survive the reset.
- **Area:** `TypingPanel.kt`, focused new lifecycle tests, and the IME services
  only where a demonstrated lifecycle defect requires a change. One writer owns
  each source/test file. Do not modify `DeviceTest.kt` or `PrivacyCoreTest.kt`
  concurrently with other Android work.
- **Constraints:** no new text-context reads, recording triggers, preference IDs,
  settings persistence, model deletion, permissions or desktop changes. The local
  private-draft owner retains responsibility for its text; resetting a keyboard
  surface must not mutate another owner's editor. Keep numeric default, action
  label and capability policy when reusing a panel.
- **Acceptance:** attached same-instance detach/reattach clears advanced state,
  refuses old tap/long-press controls, cancels pending input and restores usable
  typing. Verify ordinary/numeric and owned preview/private panel variants.
  Add bounded native-IME rotation evidence if the fixture supports a reliable
  one-shot transition; distinguish it from synthetic configuration rendering.
  Audit voice-panel reuse and fix only a demonstrated defect with regression proof.
- **Verification:** Android tooling and JVM tests; focused lifecycle, compose,
  modifier, rollover, gesture, geometry, sensitive and private-draft regressions;
  lint; complete API 35 connected suite for the shared panel change. Preserve
  first failures rather than converting isolated retries into a clean suite.
- **Non-goals:** A5 fallback/retries, daily toolbar redesign, dictation state-machine
  redesign, cross-app/process/hardware claims without named evidence, release work.
- **Stop:** named checks and independent review pass, docs distinguish actual
  platform transitions from panel tests, and remaining A4 gaps are explicit.

Android's default `InputMethodService.onConfigurationChanged` rebuilds input UI
and calls the appropriate input-start callbacks. Retain that framework behavior
instead of adding a redundant custom configuration override.
[Android lifecycle reference](https://developer.android.com/reference/android/inputmethodservice/InputMethodService#onConfigurationChanged(android.content.res.Configuration))

Then complete the remaining A4 application/process/hardware matrix and define A5
limited/broken-connection fallback without speculative retries.

### Lifecycle policy and evidence boundaries

| Boundary | Required behavior | Evidence scope |
| --- | --- | --- |
| New editor / application | Invalidate the old UI generation, suggestions, draft and voice take; derive new capabilities and show the field's baseline keyboard. Never send cleanup keys to the new editor. | Existing native same-app field tests; a real second-application transition remains unverified. |
| Hide / finish / reopen | Clear owned transient panels and pending work. Reopening does not resume recording or restore Tools/modifiers. | Existing native hide/reopen cases; not a universal host claim. |
| Same panel detaches / reattaches | Cancel gestures/repeats and reset Tools, edit/Fn, Caps/modifiers, compose/alternates and repeat cache. Reattach starts at letters or the configured numeric base, preserving eligibility, action and explicit preferences. | Four attached-panel regressions passed in focused and full API 35 runs. |
| Orientation / configuration | Retain the framework's UI rebuilding and input-start callbacks; rebuild from current options without reviving an old panel's controls. | Native API 35 portrait/landscape/portrait recreation plus explicit reopening passed. This is separate from direct renders and does not claim every host preserves keyboard visibility. |
| Process recreation | Transient UI/capture state is memory-only and starts fresh; load only explicit preferences and verified installed model choices. Do not save field contents or advanced modes for restoration. | Source policy; a process-recreation campaign remains `Not run`. |
| Hardware keyboard connects / disconnects | Follow Android's input-view visibility policy; never force the soft keyboard open or start capture. Any resulting hide or input restart uses the same reset boundaries. | Source policy; physical and emulated hardware transitions remain `Not run`. |

### Verification log — September 26, 2026

- First focused run: 40/41 passed (80.828 test seconds), including all four new
  attached-panel cases. `PrivateDraftImeTest.fieldSubtypeAndHideClearDraftAndMakeOldButtonsHarmless`
  failed at its first keyboard-show setup, before its lifecycle assertions. The
  captured log shows Gboard receiving both show/restart requests, not Utterleaf.
  Preserve this failure and tighten setup/restoration readiness rather than retrying
  editing actions or changing product timing.
- First live-rotation test failed waiting for a visible replacement keyboard.
  The Activity did recreate in landscape; Android then applied the fixture's
  `stateAlwaysHidden` policy (`HIDE_ALWAYS_HIDDEN_STATE`), aborting automatic show.
  The corrected fixture must explicitly reopen once in each recreated editor,
  without `restartInput` after rotation, and retain old-surface/key and modifier
  assertions. Its claim is rotation plus explicit reopening, not continuous
  keyboard visibility across every host rotation.
- Raw first-run reports are retained locally in
  `.grok/validation/ime-lifecycle-20260926/focused-first-run` and
  `rotation-first-run`. Neither run is a passing complete gate.
- The corrected focused group passed **42/42**, zero failures/errors/skips
  (62.679 test seconds). This includes portrait-to-landscape-to-portrait Activity
  recreation with explicit IME reopening, replacement surface identity, old-key
  refusal, cleared modifiers and fresh typing. Four direct panel cases also pass.
  Reports are retained in `focused-corrected-run` in the same validation directory.
- The private-draft fixture now uses stable default-IME setup/restoration and
  one-shot restart/show. Cleanup attempts every restoration step without masking
  the primary failure. A final test-only cleanup refinement removes an unrelated
  focus-recovery loop and closes a locally started Activity if launch readiness
  fails; the final complete suite below includes that refinement. No product timing
  or editing assertion was changed to address the harness failures.
- Independent review passed the product reset, new tests and final harness diff.
  A bounded voice audit found no demonstrated defect requiring source changes:
  existing take/editor generations and lifecycle clearing remain intact. A named
  live voice-only hide/reopen test remains separate evidence, not a proven bug.
- First complete run: **209/210** passed, zero errors/skips (298.277 test
  seconds). The only failure was
  `SuggestionStripTest.stripCompletesTheComposingWordThroughTheEditor` at keyboard
  setup, before typing or candidate assertions. Its log also shows Gboard servicing
  both show requests. Extend the existing stable selection/restoration and one-shot
  launch pattern to that fixture; preserve suggestion assertions and restore its
  preferences even if launch fails. This failed complete run is retained in
  `full-first-run`, not counted as a clean gate.
- After that test-only correction, the suggestions/private-draft/new-lifecycle
  group passed **22/22**, zero failures/errors/skips (41.558 test seconds), in
  `suggestion-harness-corrected-run`. Independent review passed its options
  ownership, stable selection/restoration and failure-preserving cleanup; product
  code is unchanged from the earlier lifecycle runs.
- Final combined candidate: **210/210** complete API 35 software-renderer emulator
  tests passed, zero failures/errors/skips (276.543 test seconds), with **47 JVM**
  tests, **17 Android tooling** tests and lint with **zero errors / 60 existing
  warnings**. Raw reports are in `full-final-run` and `lint-final.txt`. Independent
  source, test and documentation review passed. Debug APK SHA-256:
  `3ae6c1d9f1f9ffc28a8ad1331399ac3e4c77b1510272a6102588f96d0a25e073`.
  This is working-tree evidence, not a release or physical-phone claim. The
  debug/test packages were removed by Gradle and the prior default IME restored.

Run from `mobile/android`:

```powershell
$lifecycleClasses = @(
    'org.utterleaf.voice.TypingPanelLifecycleTest',
    'org.utterleaf.voice.KeyboardLifecycleTest',
    'org.utterleaf.voice.ComposePanelTest',
    'org.utterleaf.voice.HeldModifiersTest',
    'org.utterleaf.voice.TypingRolloverTest',
    'org.utterleaf.voice.KeyboardGesturesTest',
    'org.utterleaf.voice.SensitiveTypingPanelTest',
    'org.utterleaf.voice.PrivateDraftImeTest'
) -join ','
.\gradlew.bat connectedDebugAndroidTest "-Pandroid.testInstrumentationRunnerArguments.class=$lifecycleClasses" --no-daemon
.\gradlew.bat testDebugUnitTest lintDebug connectedDebugAndroidTest --no-daemon
```

The tooling command runs from the worktree root:
`python -m unittest discover -s mobile/android/tools -p test_*.py`.

## Next bounded slice

Capture the opt-in performance baseline against the passing foundation candidate,
then address literal-field suggestions, private-draft graphemes and model trust.
The larger named-application compatibility, accessibility and redesign gates remain
open. A same-package Activity recreation is not process recreation, and observed
emulator input-device add/remove is not physical hardware usability.

### Verified bounded slice — external lifecycle gauntlet

- **Goal:** prove voice-only hide/reopen, real cross-package editor transitions
  and IME process recovery without confusing Activity recreation with process death.
- **Area:** a separate, opt-in `lifecycleHost` debug fixture and its instrumentation;
  a signature-protected debug-only product host; a named voice-only IME test.
- **Constraints:** release source/manifest/dependencies stay unchanged. No microphone
  capture, real field content, network, broad process termination or product test hooks.
  The driver survives the IME process and restores prior IME state on every exit.
- **Acceptance:** new-package and recreated-process keyboards return to daily typing
  with cleared modifiers; the old target stays unchanged and fresh input reaches only
  the current target. Voice-only reopening stays idle with options collapsed and a
  working return-to-keyboard control. Process tests verify old/new package-owned PIDs
  and preservation of the independent host's PID, text and selection.
- **Verification:** compile/lint fixtures; named voice and host instrumentation;
  existing app instrumentation after integration. Preserve first-run failures.
- **Non-goals:** arbitrary third-party application compatibility, physical hardware
  claims, release publication, or framework callbacks simulated as device evidence.
- **Stop:** these named boundaries pass independent review and repeatable checks;
  then advance to degraded-editor handling and the pre-redesign baseline. A hardware
  claim additionally needs observed input-device add/remove and applicable visibility
  transitions; an already-attached emulator keyboard is not absent-to-present proof.

### Verified bounded slice — A5 degraded editor contract

- **Goal:** null, refusing, throwing and malformed editor connections fail locally
  without crashing ordinary typing or replaying an ambiguous edit.
- **Area:** editor-action dispatch, auxiliary voice insertion and bounded suggestion
  completion/context work; counting and mutate-then-fail instrumentation fixtures.
- **Constraints:** exactly one requested mutation per step, no automatic fallback
  to key events/newlines/clipboard and no speculative restoration of the old word.
  A host's `false`/exception does not establish that it left text unchanged. Never
  log field contents. Keep existing session guards and terminal key-release rules.
- **Acceptance:** action and voice failures do not escape; a candidate commit that
  mutates then refuses/throws is never followed by the original word or a retry;
  absent, throwing or oversized context prevents destructive completion; a refused
  batch prevents completion; every attempted batch gets one closing attempt, per
  the [InputConnection contract](https://developer.android.com/reference/android/view/inputmethod/InputConnection#endBatchEdit()).
- **Verification:** focused editor-action, terminal, suggestion and voice tests;
  JVM/tooling/lint and complete app instrumentation after integration; independent
  contract/diff/test review.
- **Non-goals:** pretending an unsupported host supports complex editing, automatic
  editor-specific workarounds, retries, telemetry or a new connection framework.
- **Stop:** the named adversarial cases and existing editing regressions pass;
  document ambiguous outcomes honestly, then advance to the performance baseline.

### In progress — B matched performance baseline

- **Goal:** record a repeatable pre-redesign emulator baseline without placing
  measurements or logging on the shipping typing path.
- **Area:** opt-in instrumentation/recorder, default annotation exclusion in the
  app test configuration, and an Android-only standard-library report parser.
- **Constraints:** no production hooks/dependencies, private content or telemetry.
  Use synthetic text/public verified audio. Microphone startup is measured only on
  the explicitly invoked emulator with host audio disabled. Restore fixture state.
  Timing assertions must not turn performance observations into flaky correctness gates.
- **Acceptance:** raw on-device nanosecond timestamps, explicit sample counts,
  median and nearest-rank p95 for show, key feedback/commit, candidate generation/
  render, Tools transitions, voice startup/decode/insertion; memory and sustained
  frame samples. First-draw endpoints are rendering proxies, not physical display
  presentation. Record device/build/APK/options/model/audio identity and distinguish
  cold/warm cases. Comparisons require matched conditions; emulator numbers do not
  establish phone responsiveness, heat, battery or one-handed usability.
- **Verification:** parser unit tests, instrumentation compilation, one isolated
  opt-in baseline run, complete sample/metadata validation and independent review.
- **Non-goals:** a benchmark dependency/framework, optimizations before measurement,
  arbitrary numerical pass thresholds, production diagnostics or live user speech.
- **Stop:** records and limitations are reproducible and archived outside build
  outputs; retain the baseline for before/after comparisons during later milestones.

### Gauntlet log — external lifecycle and degraded editors

- Auxiliary voice-only hide/reopen passed its first named run, **1/1** (4.633
  test seconds), on the preceding `3ae6c1…` candidate. It verifies idle reopening,
  collapsed options, usable controls/keyboard return, unchanged synthetic host text
  and no active recording at each checked boundary. It never taps a microphone.
  Raw evidence: `.grok/validation/external-lifecycle-20260926/voice-first-run`.
- First combined degraded-editor/voice/hardware group: **37/38**, zero errors/skips
  (26.071 test seconds). All new lifecycle and adversarial cases passed. The old
  successful spacing fake returned `world` despite a one-character context request;
  the new bound correctly refused it. Correct the success fake to honor its request
  and retain separate malformed-editor tests. Raw evidence is in
  `.grok/validation/degraded-editor-20260926/focused-first-run`.
- Hardware evidence observes an actual external alphabetic `InputDevice` being
  added and removed through `uinput`, then explicit IME hide/reopen and fresh typing.
  The device reported `keyboard=2` with Tools still visible after attachment because
  an internal emulator keyboard was already present. This is **not** evidence of an
  absent-to-present configuration transition or physical USB/Bluetooth usability.
  The fixture owns the input stream and removes only its own device at cleanup.
- First external-host run: **0/2** (39.801 seconds). Both failures were incorrect
  daily-layer assertions: `Select neighboring word` is also a normal toolbar control.
  The next run passed process recovery but failed the cross-app Edit-layer precondition,
  **1/2** (24.120 seconds): the generic header's `Return to typing` label is overridden
  by `Close editing tools`. Use the exact visible layer-specific control, not a shared
  shortcut or a default argument. No product timing or lifecycle action was changed.
  Both raw runs remain under `external-lifecycle-20260926`, as `host-first-run` and
  `host-corrected-selector-run`; neither is a complete passing gate.
- Independent A5 review also identified a malformed `CharSequence` liveness hole:
  unchecked length access could strand the suggestion worker, and an untrusted
  conversion could allocate beyond the request. A shared bounded indexed-copy helper
  now catches getter failures and never uses host conversion methods. Counter-based
  tests check zero oversized inspection and recovery on the next valid request.
  Every attempted batch is balanced; a false/throwing batch end leaves the IME-client
  result unconfirmed, with no replay or compensating edit. Independent final review
  passed these corrections; combined final verification is in progress.
- The first full A5 candidate (`2ac137…`) did **not** complete: 162 cases passed,
  one failed, and the process crashed after 163 of 219 scheduled cases (257.747
  reported test seconds). `invalidatedOrClosedSuggestionReadsCannotDeliver`
  exposed `InterruptedException` escaping the new bounded-read helper when closing
  a blocked worker. The correction catches interruption, preserves its signal and
  returns unavailable; a new separate-thread regression checks that behavior.
  The original close/invalidate test is unchanged. Evidence is retained in
  `degraded-editor-20260926/full-first-run`; this is a real corrected source
  regression, not a clean full gate or a harness retry.
- The final independent-host run passed **2/2**, zero failures/errors/skips
  (10.712 test seconds): cross-application reset and actual IME process death/
  recovery. The prior Gboard selection was restored. Raw evidence is retained in
  `external-lifecycle-20260926/host-final-run`. The product APK SHA-256 was
  `7cd497b94a9d28e08b67b96b7b7ce397eb5c9c1a944b32a02899f5ecf25b4162`;
  this includes the interruption fix, but the complete app regression run remains
  pending. The separate fixture is opt-in and debug-only, uses synthetic editors,
  verifies process ownership before terminating the IME, and has no release or
  network permission. This does not establish arbitrary third-party compatibility.
- The corrected affected group passed **41/41**, zero failures/errors/skips
  (26.056 test seconds), then the complete ordinary app suite passed **220/220**,
  zero failures/errors/skips (310.935 test seconds). The default run excluded the
  opt-in performance class. **47 JVM** tests passed and lint remains **zero errors /
  60 existing warnings**. The product APK hash is the same `7cd497…` candidate as
  the passing independent host above. Raw reports, JVM XML and lint are archived in
  `degraded-editor-20260926/full-final-run`; focused reports are in
  `focused-final-run`. The former default IME was restored. Independent final A5
  review passed the interruption, bounded-copy and no-replay rules. The release
  merged manifest contains neither debug fixture components/permission nor network
  permissions. These checks complete the named automated A4/A5 slice, not the A–M
  redesign or a physical-phone/third-party compatibility gate.

### Literal fields and private-draft graphemes

- **Goal:** English completion must not add word spacing to email/URI fields;
  private-draft deletion and horizontal movement must respect grapheme clusters.
- **Area:** capability resolver, its JVM/live suggestion tests and explanatory
  settings copy; separately, `PrivateDraftEditor` and its owned-editor tests.
- **Constraints:** no preference-ID/default change, added context inspection,
  geometry change or host-editor deletion-policy change. Prose and search retain
  suggestions. Preserve word/vertical movement and existing selection behavior.
- **Acceptance:** email, web-email and URI metadata disable the requester and
  strip without disabling typing; an ordinary metadata restart restores candidates.
  Private-draft Backspace/Delete/Left/Right cannot split a combining sequence,
  supplementary character or family ZWJ cluster, including shifted navigation.
- **Verification:** resolver JVM tests; focused live suggestion/private-draft
  instrumentation; independent diff/test review and affected regression checks.
- **Non-goals:** language prediction, address completion, host RTL policy or a
  wholesale editing rewrite. Host combining deletion and live RTL/cross-line
  behavior need their own evidence and remain explicitly open.
- **Stop:** the named literal-field and owned-grapheme cases pass without changing
  ordinary typing or the previously recorded baseline conditions.

### Performance gauntlet log

- The first opt-in attempt compiled and selected only the one performance case,
  but failed its unmeasured Tools-close setup assertion (54.576 test seconds).
  Its records correctly say `measurement_body_completed=false` and
  `cleanup_completed=true`; the prior IME was restored. Raw evidence is archived in
  `.grok/validation/performance-20260926/first-run`, not accepted as a baseline.
  The fixture now resets Tools between samples through one direct close callback
  and retains the daily-surface assertion; measured Tools opening still uses an
  injected touch. This is a setup-method change, not proof of a product touch defect
  or an established coordinate-routing cause. Review also corrected the reported
  decode warmup count and added the complete effective options identity before
  the next attempt. The product APK/source remain the passing `7cd497…` foundation
  candidate, archived separately as `foundation-source`.
- The second attempt failed the first pressed-key draw observation (19.56 test
  seconds). The first-show measurement ends at first draw, before geometry is
  necessarily settled for a subsequent injected touch. The fixture now waits,
  outside measured intervals, for three unchanged pre-draw key bounds/IME insets
  with no pending layout, verifies the intended key is pressed, and cancels an
  unsuccessful hold before the normal alternate-key deadline. It does not retry
  samples or turn the timeout into a product performance threshold. Evidence:
  `performance-20260926/second-run`; body incomplete, cleanup complete.
- The third attempt reached voice startup after collecting the typing, candidate
  and Tools samples, then failed because the fixture constructed an animated
  `VoicePanel` off the main thread (44.626 test seconds). All fixture View creation
  now runs on the main thread. Tools reset also receives the same unmeasured
  geometry barrier, and failed key DOWN is cancelled before listener cleanup.
  Evidence: `performance-20260926/third-run`, APK SHA-256
  `968a9916bb1d0a7eb322c49c2aadf8a780b4890acef6d815faeea28b474d7d09`.
  Body incomplete and cleanup complete: these partial samples are not a baseline.
- The fourth attempt completed the isolated case, **1/1**, zero failures/errors/
  skips (91.387 test seconds). The parser accepted complete body/cleanup records,
  all counts and matching device/APK provenance. The accepted pre-visual baseline
  is archived in `performance-20260926/baseline`, including exact product/test
  source, APK, raw logs, JSONL and summaries. APK SHA-256:
  `728f27dc28c7e7868795d4a586ab45df5118b588de4ea3e8baca25adfa394bd8`.
  See [P1](../../android-keyboard-compatibility.md#performance-run-p1--accepted-pre-visual-baseline)
  for timings, memory, frame observations and limits. Result insertion remains a
  local callback proxy, and software-emulator frame overruns are recorded rather
  than labeled a smooth-phone pass. No numerical performance threshold is asserted.

### Trust gate — model readiness and import recovery

- **Goal:** only checksum-verified bytes are considered ready or passed to native
  inference; setup remains truthful through checking, invalid files and recreation.
- **Area:** `ModelStore`, its sole production native caller in `VoiceSession`,
  Setup/Voice panel readiness and focused model/setup tests.
- **Evidence motivating the slice:** imports verified SHA-256, but the pre-slice
  readiness/selection code later accepted private files by catalog size alone.
  Sparse test files were incorrectly reported ready. Import work also reported
  to the Activity instance that started it, losing progress/result on recreation.
  The implementation and gauntlet below address those defects; they were not
  retrospectively included in the earlier foundation claims.
- **Constraints:** verify on a bounded background worker, never during typing or
  UI rendering. No network, preference-ID change, model deletion, persistent URI,
  transcript retention or synchronous 78–488 MB hashing. Existing verified legacy
  paths can remain in place; no migration is required solely for verification.
- **Acceptance:** per-process Ready follows an actual catalog checksum (or the
  just-completed verified atomic import), tied to canonical path/length/mtime.
  A new process re-verifies before loading; ordinary file changes invalidate the
  cached result. Missing/Checking/Invalid cannot yield a native-load path. Capture
  acquires the model-work lease before resolving one verified path and holds it
  through decode. Setup reports checking/failure with typing unaffected and a
  direct recovery action. Failed imports preserve the existing active model.
- **Verification:** real tiny/base fixture import and inference; same-sized
  unverified/corrupt rejection; verified legacy readiness; mutation invalidation;
  no UI-thread hashing; disposed observers; setup recreation and interrupted-import
  recovery tests. Keep Activity recreation distinct from process-death evidence.
- **Non-goals:** network model management, new model formats, a general task
  framework, disk provenance markers or protection from an OS compromise that can
  change verified bytes while preserving all metadata within the same process.
- **Stop:** the native-load boundary, truthful readiness and bounded lifecycle
  recovery pass review and named tests before further dictation or visual work.

### Trust, recovery and editing gauntlet log

- The first integrated affected group passed **53/53**, zero failures/errors/skips
  (71.202 test seconds), with **48 JVM** and **23 Python tooling** tests passing.
  Lint reports zero errors and 57 warnings. This covers real verified imports and
  inference, corrupt/unverified rejection, disposed panels, literal-field
  suggestions, owned grapheme boundaries, import failure surviving Activity
  recreation, and preservation of the active verified model. It does not turn
  Activity recreation into process-death evidence. Raw reports and the APK are in
  `.grok/validation/model-trust-20260926/focused-first-run`; APK SHA-256
  `5e7008cfd5ddf8debf05e2579b530e064b85d8b768292a558935ac5f21c0a266`.
- Review after that run found missing cases: a caret inside a combining/ZWJ
  cluster must delete the whole containing cluster; concurrent readiness
  notifications must not regress Ready to stale Checking; a throwing observer
  must not strand others or escape a successful model mutation; thread-start
  memory failure must release the capture lease. Corrections and focused
  regressions were then integrated before the full ordinary suite. Native test
  paths also use the verified-file gate. The earlier 53-case result does not
  establish these later corrections.
- The review-corrected ordinary suite passed **228/228**, zero failures/errors/
  skips (309.344 test seconds), plus **48 JVM** and **23 tooling** tests. Lint
  remains zero errors / 57 warnings. APK SHA-256:
  `9656da86113da153f9023a73d95bef55552eecbfaf29cadac933c46a7912ec92`.
  Evidence is archived in `model-trust-20260926/full-first-run`; the former Gboard
  selection was restored. This includes inside-cluster deletion, model observer
  ordering/reentrant mutation, observer exception isolation, import memory failure
  and retry, and an actual short-capture terminal callback observing a released
  lease. Thread-start memory-failure branches are statically reviewed, not injected.
  A final review correction makes native-result byte clearing unconditional even
  if UTF-8 conversion fails; it was applied **after** this archived run and is part
  of the next candidate, not retrospectively covered by this APK.
- Final exact-candidate verification including that byte cleanup passed **228/228**,
  zero failures/errors/skips (303.121 test seconds), **48 JVM** tests and lint
  with zero errors / 57 warnings. `assembleRelease` also passed; this is an
  **unsigned compilation artifact**, not signing, publishing or release approval.
  Evidence is archived in `model-trust-20260926/full-final-run`. Debug APK SHA-256
  `728f27dc28c7e7868795d4a586ab45df5118b588de4ea3e8baca25adfa394bd8`
  matches the accepted P1 baseline; unsigned release SHA-256 is
  `14fac623ef1be8e416b1dd4fc9d3c1d9b385634ba43c8574adcf3a1c04498b98`.
  Gboard was restored. The release merged manifest requests only microphone
  permission and contains none of the debug fixture components; model/JFK test
  assets are not release payloads. No source/layout change followed P1, so there
  is no post-redesign performance comparison to claim yet.
- The subsequent independent-host run failed **0/2** (0.811 test seconds), before
  exercising any editor: `withKeyboard` could not find the installed product IME.
  The Gradle log showed cross-project parallel scheduling starting the host tests
  before `:app:installDebug` completed, despite its earlier position in the command.
  Evidence is retained in `model-trust-20260926/host-first-run`. This exposes a
  missing build dependency, not a passing lifecycle gate. The fixture must depend
  explicitly on product installation; validate that correction from a deliberately
  absent disposable test installation, without sleeps or test retries.
- The corrected host task explicitly depends on `:app:installDebug` through lazy
  debug-task configuration. Independent review and **25/25 tooling** tests passed,
  including two new task-order/opt-in/release-isolation contracts. After verifying
  the disposable AVD/package identity, the debug test installation was removed;
  `pm path` confirmed absence. The same command then installed the product before
  running the host and passed **2/2**, zero failures/errors/skips (11.258 test
  seconds), with host lint zero errors / five warnings. Evidence:
  `model-trust-20260926/host-final-run`. Gboard was restored and the product APK
  remains the exact `728f27dc…` candidate from the app suite and P1. No global
  parallelism setting, sleep, retry or product source change was used to close
  this build-order gate.

### Current increment handoff

The named A4/A5, literal-field/owned-grapheme, model-trust/import-recovery and
pre-visual measurement gauntlets above are closed for their stated scope. Final
checks: 228 app cases, two independent-host cases, 48 JVM cases, 25 tooling cases,
one isolated performance case, app/host lint without errors, and unsigned release
compilation. Reports and failed predecessors remain archived. No signing,
publishing, telemetry/cloud dependency or desktop change was performed.

The complete A–M redesign is **not** closed. Next source slices remain the Tools/
daily composition prototype, authoritative dictation state/recoverable stale-result
flow, and remaining action-specific recovery work. The I/J increment below adds
capability-first model presentation and granular settings resets. Named
third-party compatibility, real-host result insertion measurement, post-redesign
performance comparison and final accessibility acceptance remain open. Do not
promote these scoped automated results to phone, OEM, third-party or final
redesign-completion claims.

### Tools audit — rail microchange rejected before editing

- The current accessory-to-Fn switch preserves modifier state, but Fn hides its
  controls. A shared rail would shorten some modifier-change tasks. However, the
  actual specialist surface is one 48 dp row with 96 dp of fixed selectors and
  horizontally scrolling keys; a prefix inside that scroll is not persistent.
- A fixed 162 dp modifier rail leaves only 62 dp at 320 dp portrait width, or
  54 dp with the ABC control at 360 dp one-hand landscape: one visible Fn key.
  This adds scrolling for F2–F4; moving accessory modifiers also slows the current
  Esc/Ctrl/Left arrangement. A two-tap arithmetic benefit does not establish a
  lower real interaction cost when other tasks lose visible targets. **No rail
  code was changed.** Preserve the current functional surface for this candidate.
- The next useful prototype is a replacement Tools composition within the typing
  area's height: persistent modifiers with a 2×6 Fn grid and spatial navigation,
  intentionally different portrait/landscape arrangements. It must preserve
  Esc/Tab/all navigation keys, at least 48 dp targets, total keyboard height,
  reset semantics and efficient mixed chords at the minimum widths. It needs
  task-step/geometry evidence, matched P1 performance and independent accessibility
  review before choosing a layout. This is not physical-usability proof.
- Clipboard alternatives were also compared: current persistent Cut/Copy/Paste
  are one tap; contextual actions either preserve all slots or introduce unstable
  targets/editor-dependent state; a privacy-safe explicit flyout is two taps,
  duplicating the existing Edit route. No passive clipboard read or new menu was
  added, and placement remains unchanged pending actual task evidence.

### I/J slice — model clarity and reversible settings resets

- **Goal:** model choices explain the English capability, size and storage/runtime
  tradeoff before exposing implementation identifiers; settings make deviations
  from defaults visible and allow individual/category resets without losing
  unrelated choices or model data.
- **Area/ownership:** one writer owns model presentation in Setup/VoicePanel and
  its focused tests; another owns KeyboardSettingsActivity and reset tests. Root
  owns documentation, integration, emulator/build execution and any necessary
  exclusive DeviceTest/PrivacyCoreTest edits. Model trust/capture/storage code,
  the typing panel and all desktop files remain unchanged.
- **Constraints:** retain exact preference IDs/defaults and staged Apply/Cancel
  semantics; compute modified status from values rather than another persisted
  flag. Reset affects preferences only, never models, transcripts or other user
  files. No new model recommendation/accuracy claims, model migrations, hashing
  on rendering, network, permission requests or implicit selection/import. Model
  identifiers, checksums and locations belong behind explicit details; keep
  missing/checking/invalid/verified/selected states truthful and text-labeled.
- **Acceptance:** normal model choices have distinct readable names, explicit
  units/size and unchanged stable selection identity. Details can be opened and
  closed without mutating storage or starting capture. Modified indicators and
  individually named reset actions are accessible and searchable. Individual
  reset changes only its setting; category reset changes only the displayed
  category; both remain staged until Apply and are discarded by Cancel. Verify
  recreation, persistence/reopen, dependent layout controls, and model preservation.
- **Verification:** focused JVM/presentation/reset tests, existing affected setup/
  settings/voice tests, tooling and lint; integrate into one emulator run after
  independent review. Reuse the existing baseline: no ordinary typing-path change
  is authorized, so do not rerun expensive decoding solely for presentation copy.
- **Non-goals:** the authoritative dictation state machine, Tools composition,
  theme redesign, preference schema migration, speculative physical usability or
  releasing/signing/publishing the candidate.
- **Stop:** the named UI/reversibility cases pass, source and docs match, and
  independent review has no unresolved correctness/privacy regression.

### I/J verification log — September 26, 2026

- The initial JVM attempt stopped at compilation: a refresh lambda ending in an
  optional callback inferred nullable Unit. Its return was made explicit; this
  predecessor is not counted as a test pass.
- The first integrated group passed **45/46** (79.246 test seconds), with **50 JVM**
  and **25 tooling** tests passing. The failure was the synthetic reset-action
  visibility assertion. A single diagnostic rerun preserved the same dimensions
  and assertion and exposed the harness defect: translating a ScrollView viewport
  from `(0, 0)` subtracted its own scroll offset. Using its drawing rectangle
  cancels that target offset while retaining ancestor scrolling. No product
  height, viewport size or assertion was weakened to obtain the later pass.
- With that reviewed harness correction the affected group passed **46/46**, no
  failures/errors/skips (62.848 test seconds); **50 JVM** tests and lint with
  **zero errors / 54 warnings** passed. Debug APK SHA-256:
  `7d5abbfd01c9c34b148dca0c09c56038245b23274262d58677bcee2d16d033f4`.
  Reports, exact source/APK, predecessors and synthetic captures are archived
  under `.grok/validation/ij-presentation-20260926` (`focused-first-run`,
  `geometry-diagnostic-run`, `focused-final-run`).
- Scope includes readable choices without changing model identity, details
  opening/closing/recreation, friendly import-success copy, busy/stale selection
  guards, category inventory, individual/category reset staging, Cancel/Apply,
  reopen/recreation, alignment/split dependencies, and model/unrelated-setting
  preservation. Disclosure nonmutation/no-capture follows the reviewed pure
  callback; that UI test directly checks visibility and lease availability, not
  storage hashes or an instrumented capture counter.
- Visual inspection of the passing synthetic captures found the new category
  status label breaking into word fragments beside its wide action. A subsequent
  presentation-only correction stacks the category label/action at full width;
  it leaves individual rows, callbacks, reset policy and the existing header
  unchanged. Its test requires natural one-line status text, full text consumption
  and zero ellipsis (no forced maxLines), plus the existing target/bounds checks.
  The 46-case result above predates this final visual correction.
- The corrected category composition then passed **22/22** affected settings
  cases, no failures/errors/skips (32.632 test seconds), **50 JVM** cases and lint
  **zero errors / 54 warnings**. Final debug APK SHA-256:
  `a7135e6fb4ca2afa246752172ca90aa2d55a103c15ea90a420bf8fb1152ad3ca`.
  `layout-final-run` preserves the exact source/test APKs, raw reports and three
  synthetic captures. Independent review and render inspection passed. Gboard
  was restored. The scoped I/J contract is closed; no full-suite, performance,
  signed-release or phone claim is attached to this presentation-only correction.
- Geometry is scoped to synthetic 320×240 dp / 24 sp settings rendering in an
  emulator landscape Activity, and 320 dp / 1.5×-text model options in an owned
  panel. This is not real system font-scale, screen-reader or phone usability
  evidence. The existing header still wraps at the extreme synthetic width/text
  combination; that remains part of the final accessibility work, not an I/J
  redesign-completion claim. Standalone voice landscape is unverified.

The first command ran the 46-case group; the second rechecked the final category
layout (22 cases). Run from `mobile/android`; optional synthetic-capture arguments
used in the archived runs do not change test selection:

```powershell
.\gradlew.bat testDebugUnitTest lintDebug connectedDebugAndroidTest '-Pandroid.testInstrumentationRunnerArguments.class=org.utterleaf.voice.SettingsResetTest,org.utterleaf.voice.SettingsExperienceTest,org.utterleaf.voice.KeyboardTuningTest,org.utterleaf.voice.PersistenceTest,org.utterleaf.voice.SetupRecoveryTest,org.utterleaf.voice.ModelCatalogTest#setupSeparatesTypingVoiceAndSelectableModelLinks,org.utterleaf.voice.VoicePanelControlsTest' --no-daemon
.\gradlew.bat testDebugUnitTest lintDebug connectedDebugAndroidTest '-Pandroid.testInstrumentationRunnerArguments.class=org.utterleaf.voice.SettingsResetTest,org.utterleaf.voice.SettingsExperienceTest,org.utterleaf.voice.KeyboardTuningTest' --no-daemon
```

### Prepared next G slice — editor-bound dictation ownership

Read-only source preparation is complete; this is **not implemented** or a
passing dictation recovery gate. The next cohesive change needs these boundaries:

- One service-local controller per IME owns the authoritative internal phases,
  take/editor tokens, bounded result (16,000 characters) and 120-second expiry.
  It never stores an InputConnection, host text, disk/Bundle state or static result.
- Capture emits a typed mic-off Processing transition only after recorder release.
  Editor changes during Starting/Listening/Stopping cancel and purge. Only
  mic-off Processing may survive the finish/start handoff for explicit recovery;
  hidden/destroyed or sensitive/raw/unknown/non-dictation targets always purge.
- Services issue a new editor token on start and recheck current capabilities at
  insertion. Automatic hold insertion requires the original token. A recovered
  same-package safe result may offer explicit Insert here; cross-package or
  unknown-package recovery is Copy/Discard only. Package metadata is not a
  security identity. Copy is explicit, sensitive-marked where supported, and
  clears the local result after success; no passive clipboard read is introduced.
- Commit outcomes distinguish Inserted, Not attempted and Unconfirmed. A
  false/throw after one host commit is uncertain: never replay or roll back;
  retain Copy/Discard only. This cannot use the current Boolean printable helper
  as an authoritative success model.
- Separate panel detach/unsubscribe from service cancellation. VoicePanel owns
  presentation/local editing only; the existing Dictate control can expose
  Processing/Review result without forcing voice UI over ordinary typing.
- Require reducer transition/late-callback/expiry tests, no-capture recovery UI,
  actual finish/start/hide lifecycle tests, safe/sensitive/cross-package target
  transitions and mutate-then-false/throw InputConnection regressions. Preserve
  ordinary typing, geometry, model trust and fixed local feedback. Root owns IME
  integration and exclusive DeviceTest/PrivacyCoreTest edits; other writers need
  explicit disjoint ownership before implementation.

## Stop

Stop each bounded slice when its named checks pass, documentation matches source,
independent review finds no unresolved privacy/correctness regression and remaining
device/accessibility limits are explicit. Do not broaden a completed foundation
slice into unrelated visual, language, release or desktop work.
