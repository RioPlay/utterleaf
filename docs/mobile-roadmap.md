# Mobile keyboard roadmap

[Roadmap hub](roadmap.md) · [Execution plan](execution-plan.md) · [Current mobile preview](mobile.md) · [Ideas](ideas.md)

Updated September 11, 2026. Product direction: a complete, customizable Utterleaf
keyboard with integrated offline speech, its own identity, and security first.
The design uses historical public documentation as research context, not as a
specification, dependency or source of product identity.
Desktop changes are tracked separately in the [desktop roadmap](desktop-roadmap.md).

[Mobile keyboard research](mobile-keyboard-research.md) supplies the evidence and QA
criteria behind the priorities: safe editor behavior and accessible everyday typing,
then editing, language/correction and evaluated prediction/swipe. The report is a
design input; it does not mark these features or physical acceptance as complete.

[Everyday typing and power controls](mobile-keyboard-hybrid.md) pools additional
touch research and ten concrete user reports into a Daily/Edit/Terminal proposal,
default-versus-optional decisions and security acceptance contracts. It refines this
roadmap without claiming those capabilities are already released.

## Current status

- **Foundation preview01, experimental:** a [signed test download](https://github.com/RioPlay/utterleaf/releases/tag/android-foundation-v0.1.0-preview01)
  is available separately from alpha13. A pinned AOSP LatinIME fork has been
  built and exercised locally with real IME touch input, restricted capabilities
  and comfort preferences. The [execution evidence](../mobile/latinime/EXECUTION-EVIDENCE.md)
  records 12 JVM and 112 API 35 emulator tests, lint limitations, native compilation
  and remaining licensing/security/product gates. Suggestion workers now receive
  owner-captured composer/context inputs and deep pointer copies, and pass captured
  immutable proximity ownership into native suggestion admission instead of mutable
  keyboard state. Dictionary loads reject retired generations and stale UI
  notifications. Native dictionary/proximity
  leases defer disposal during admitted operations; a bounded external process-death
  probe passed. Owner-checked service/view cleanup and real-touch view reuse are
  verified locally; cached layouts retain immutable keyboard-only editor metadata.
  Remaining lifecycle/cache, native hardening and framework recovery
  checks continue. It is not yet integrated
  into the shipping keyboard; alpha13 remains the released implementation.

- **Released alpha12:** compact [quick editing actions](android-quick-actions.md).
  Revision `aec275b` passed [Android CI 34498263015](https://github.com/RioPlay/utterleaf/actions/runs/34498263015):
  74 emulator tests with zero failures/skips, JVM tests, lint and 3 release contracts.
  [Signed publication 34499446037](https://github.com/RioPlay/utterleaf/actions/runs/34499446037)
  verified signing continuity and emulator install/upgrade. Physical-device and
  accessibility acceptance remain open. Earlier entries below are release history.

- **Released alpha13:** slider accessibility values,
  preference snapshot synchronization, condition-based gesture tests and live-IME
  editing-action coverage. Revision `d942098` passed
  [CI 34513111803](https://github.com/RioPlay/utterleaf/actions/runs/34513111803):
  76 emulator tests, zero failures/skips, 8 JVM tests, lint, builds and 3 release
  contracts. Physical accessibility acceptance remains open; these changes are
  shipped in [alpha13 with additional release validation](android-keyboard-design.md#released-in-alpha13).

- **Released alpha10:** held Ctrl/Alt chords, independently configurable
  delete repetition and retained model imports with between-take selection.
  [67 emulator tests passed](https://github.com/RioPlay/utterleaf/actions/runs/34480299407),
  alongside 8 JVM tests, lint and 3 release-contract checks. Publication is tracked
  in the [Android guide](android-keyboard-design.md#released-in-alpha10).
  The [defaults/customization contract](android-keyboard-capabilities.md#required-defaults-and-customization-contract)
  now applies to new interactions and preferences.

- **Released alpha09:** [editing and voice evidence](android-keyboard-design.md#released-in-alpha09).
  Shift-space selection, held deletion, period punctuation, sizing/practice and
  one-handed voice controls with local transcript editing. 61 API 35 emulator,
  8 JVM and 3 release-contract tests passed, plus signed install/upgrade checks.
  Clipboard tools, optional silence detection, prediction and dictionaries remain
  planned; see the [capability plan](android-keyboard-capabilities.md) and
  [foundation assessment](android-keyboard-foundation-decision.md).

- **Released alpha07:** [gesture and import evidence](android-keyboard-design.md#released-in-alpha07).
  Hold–slide–release accents, spacebar cursor movement and model autodetection;
  8 JVM, 44 emulator and 3 release-contract checks passed. Physical-device and
  assistive-technology acceptance remain open. See the [correctness review](correctness-review.md).

- **Layout revision:** [alpha05 design](android-keyboard-design.md) replaces the
  app-button grid with staggered rows, a wide spacebar, direct punctuation and
  an expandable editing toolbar. Release and validation status are recorded in
  [the mobile guide](mobile.md).

- **Released in alpha05:** staggered everyday layout, independent
  number-row preference, optional terminal controls with one-shot Ctrl/Alt,
  navigation, and a replacing Fn layer with F1–F12, Insert and forward Delete.
  Setup separates keyboard activation from optional voice and offers verified
  tiny.en/base.en/small.en imports. Status/navigation-bar inset handling is included.
  [Alpha05 is published](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha05).
  Revision f74b862 passed CI and its setup/live-keyboard captures were reviewed. Small.en inference,
  named terminal compatibility and physical accessibility remain unverified.

- **Released foundation:** alpha05 carries forward the alpha04 foundation,
  with a native English typing keyboard, integrated local speech, verified model
  import, sizing/theme/feedback/repeat preferences, preview expiry warning/extension,
  and an Obtainium setup button. Alpha04 fixes Shift/Caps case handling and adds
  live-IME regression coverage. The separate voice companion remains available.
- **Released alpha06:** [release evidence](android-keyboard-design.md#released-in-alpha06)
  adds visible optional secondary hints, common Latin accent/symbol selection through
  long press or Tools → Accents → letter, and cancel/case/session guards. Automated
  release checks passed; adjustable hold timing, broad language support and
  physical/TalkBack/Switch Access acceptance remain open.
- **Verified in CI:** [4 JVM, 32 API 35 emulator and 3 Python release-contract tests](https://github.com/RioPlay/utterleaf/actions/runs/34432378047),
  with zero emulator failures or skips; tiny.en/base.en real fixture inference,
  model bounds/rollback, terminal event contracts, number row, Fn and inset checks;
  ARM64 and x86_64 builds. The live-IME test covers letters, cursor movement,
  deletion, Done, voice-panel-to-password transitions and hide/reopen in a test
  activity, without starting capture. Shift/Caps is verified separately through
  direct typing-panel buttons. Selected-text replacement remains an acceptance task.
  See [validation evidence and limits](mobile.md#android-validation--september-9-2026).
- **User feedback on the earlier voice companion:** functions on a Pixel 8 Pro,
  with setup and voice-only usability friction. This does not establish alpha05
  keyboard, broader phone or accessibility acceptance.
- **Acceptance remains open:** real-editor typing/dictation/correction, assistive
  technology, physical interruptions, broad device coverage and real Obtainium updates.
- **Not implemented:** iOS app or keyboard extension.

## Android milestones

The [keyboard capability plan](android-keyboard-capabilities.md) turns the product
requirements into independent Utterleaf work: P1 everyday layout/editing, P2
optional terminal keys/modifiers, P3 languages/correction, then P4 prediction/swipe
and P5 advanced customization. It records current limits, editor contracts and
measurable gates.
The alpha05 layout, number-row preference, terminal dispatch and one-shot modifiers
are released with controlled CI coverage; broader phone/editor acceptance remains
open. Released alpha06 adds optional secondary hints and common Latin accent/symbol
selection with long-press and Tools routes; physical and assistive-tech
validation remains open. Adjustable hold timing, broader languages, verified
undo/redo behavior and a functional suggestion strip remain follow-up work.
Visible toolbar space does not establish implemented suggestions or correction.

| ID / status | Deliverable | Completion gate |
| --- | --- | --- |
| M1 — In progress | Select and document keyboard foundation; threat model and licensing review | Record provenance, required notices, license compatibility, permissions, input-data lifetime, import boundaries, and update trust. Do not import restricted code merely because its source is visible. |
| M2 — Partial implementation released; broader everyday/terminal acceptance open | Polished everyday typing, integrated voice and optional power layout | Complete [P1/P2 editing and modifier gates](android-keyboard-capabilities.md#prioritized-capability-and-acceptance-matrix): selection/Unicode/Enter plus Ctrl/Alt, Esc/Tab, navigation and Fn/function keys. Meta and further power features remain planned. Verify text/composition versus raw-key dispatch in named editors/terminals. Type → dictate → correct → type without switching IMEs. Password typing stays available; speech/learning stay disabled there. No stale edit or modifier reaches a new field. |
| M3 — Partial implementation; alpha06 released | Accessibility and useful customization | Verify enabled/selected keyboard status independently from model/microphone readiness; optional companion steps must not block typing. Validate number row, adjustable key/label sizing, contrast, reachable layouts and independent feedback/repeat preferences. Alpha06 provides optional secondary hints and common Latin accent/symbol selection by long press or Tools → Accents → letter; physical, TalkBack and Switch Access validation remains open. Adjustable hold timing and broader languages remain planned. Complete setup, typing, correction, dictation, cancellation and reset using TalkBack and Switch Access. Test system-bar/cutout bounds, large fonts, landscape and stable geometry across symbol pages. |
| M4 — Partial implementation; three English model choices in alpha05 | Comfortable offline speech | Keep one active model; exact catalog size/hash and atomic replacement preserve the previous model on failure. Tiny.en/base.en fixture inference passed CI; small.en inference remains unverified. Measure memory, quality and latency on real hardware. Clear mic/loading/error state, tap start/stop, pause tolerance and accessible preview warning/extension; optional hold mode, longer takes and fuller correction remain work. No promise of recognition for every speech pattern. |
| M5 — Planned | Languages, correction, composition and optional swipe | Follow [P3/P4 language gates](android-keyboard-capabilities.md#prioritized-capability-and-acceptance-matrix): reviewed layouts/dictionaries, accents/compose/emoji/snippets, reversible correction, then bounded prediction and licensed swipe. Complex scripts need separate composition evidence. Learning is explicit, local and erasable; no password learning or automatic clipboard history. Power mode preserves literal typing. |
| M6 — In progress; persistent signed channel began with alpha03 | Broad compatibility and sustainable distribution | Defined Android/API and ABI support, diverse physical-device matrix, stable protected signing, install/update/rollback-policy testing, reproducible build inputs and release checksums. No forced downgrade or unsigned consumer APK. |

Security and accessibility gates apply to every milestone; they are not deferred
until M6. The [capability matrix](android-keyboard-capabilities.md) separates
implemented, next and later work. Swipe requires a separate engine/model/data review and measurements;
special-key labels require real InputConnection/editor compatibility evidence.

## Accessibility acceptance matrix

| Need | Required verification |
| --- | --- |
| Blind / low vision | TalkBack key exploration, names/states, focus through suggestions and settings, useful status announcements without reading private content unexpectedly. Test large labels and both contrast themes. |
| Tremor / limited dexterity | No mandatory long press or swipe; configurable repeat behavior does not silently remove intended double letters; visible alternatives for navigation and correction. |
| Limited reach / fatigue | One-handed alignment and size preferences, reachable mic/stop/cancel, bounded dictation without requiring continuous pressure. |
| Switch / external input | Reach all essential controls through scanning and external input; no focus traps; preserve platform braille and keyboard switching workflows. |
| Deaf / hard of hearing | Recording, completion and errors understandable without sound; independently configurable haptics and visual feedback. |
| Cognitive / language needs | Stable layout, predictable corrections, understandable settings, reset and optional read-back. No forced rewriting of intended text. |

Actual users of assistive technology must participate before claiming accessibility
coverage. Automated checks complement that work. No single accessibility preset
works for everyone, and selecting preferences must not require disclosing a diagnosis.

## Security and device gates

[Security design](mobile-security.md) records the initial foundation decision and
trust boundaries. [Obtainium support](mobile-obtainium.md) defines the signed release
channel, certificate identity and update acceptance work.

- No surrounding-text collection beyond a documented editing need; no text in logs,
  telemetry, crash attachments or preference files. Review any later prediction context.
- No arbitrary executable keyboard plugins or unchecked model/layout imports.
- No accessibility-service permission solely to make the keyboard accessible.
- Losing the field, hiding the panel, locking or interrupting capture must stop or
  cancel safely; explicit tests for Bluetooth, calls, permission revocation and contention.
- Test supported older Android versions and newer releases, low/mid/high hardware,
  multiple manufacturers, and small/large displays. Current ARM64/x86_64 builds do
  not imply 32-bit support. Expand ABIs only with build, resource and runtime evidence.
- A persistent release signing identity and isolated publishing workflow are implemented.
  The [successful alpha04 signing/publishing run](https://github.com/RioPlay/utterleaf/actions/runs/34428171272)
  verified the same signing certificate, an emulator upgrade from alpha03 to alpha04,
  and same-version reinstallation. Preference/model preservation was not exercised.
  The [alpha05 signing/publishing run](https://github.com/RioPlay/utterleaf/actions/runs/34432995380)
  also passed with the same certificate: signed alpha03-to-alpha05 emulator upgrade,
  same-version reinstall and setup launch. Preference/model retention was not tested.
  CI debug keys remain disposable; physical updates, real Obtainium updates and independently
  protected offline key backup remain separate gates.

## iOS track

1. **Planned:** verify current public keyboard-extension, microphone and distribution
   constraints; define a supported foreground speech/keyboard handoff.
2. **Planned:** native typing keyboard and containing app with local inference,
   explicit permissions, bounded data sharing and documented lifecycle boundaries.
3. **Planned:** physical iPhone tests for VoiceOver, Switch Control, large text,
   external input, secure-field system-keyboard behavior and app handoff.
4. **Planned:** separate signing, CI, distribution and supported-version matrix.

No private APIs or persistent background microphone workaround. Android's implementation
is not proof that iOS can offer identical microphone integration. Current evidence
and primary platform references are in [the mobile guide](mobile.md).

## Before each mobile release

The current released baseline is Android alpha13, revision `45da18a`: 76 emulator
tests, 8 JVM tests, lint, builds and 3 release contracts passed in
[CI 34516072857](https://github.com/RioPlay/utterleaf/actions/runs/34516072857).
See [signed publication and APK checksum](android-keyboard-design.md#released-in-alpha13).
Earlier alpha entries retain their historical validation scope.

Track the [Android responsiveness and acceleration pass](android-performance.md)
separately from feature completeness; hardware speedups require physical-device
measurements and safe CPU fallback.

Record source revision, version, signed artifact, test/device evidence, known limits,
dependency/license changes and upgrade behavior. Update the user guide and real
screenshots when visible behavior changes. Keep desktop releases and download links
independent. Never mark all milestones complete from compilation alone.
