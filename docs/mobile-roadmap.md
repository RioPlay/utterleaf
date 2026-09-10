# Mobile keyboard roadmap

[Roadmap hub](roadmap.md) · [Execution plan](execution-plan.md) · [Current mobile preview](mobile.md) · [Ideas](ideas.md)

Updated September 9, 2026. Product direction: a complete, customizable Utterleaf
keyboard with integrated offline speech, its own identity, and security first.
FUTO is a concept reference, not a specification to copy or a licensed dependency.
Desktop changes are tracked separately in the [desktop roadmap](desktop-roadmap.md).

## Current status

- **Released:** [Android 0.1.0-alpha04](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha04),
  with a native English typing keyboard, integrated local speech, verified model
  import, sizing/theme/feedback/repeat preferences, preview expiry warning/extension,
  and an Obtainium setup button. Alpha04 fixes Shift/Caps case handling and adds
  live-IME regression coverage. The separate voice companion remains available.
- **Verified in CI:** [4 JVM, 11 API 35 emulator and 3 Python release-contract tests](https://github.com/RioPlay/utterleaf/actions/runs/34427672686);
  ARM64 and x86_64 builds. The live-IME test covers letters, cursor movement,
  deletion, Done, voice-panel-to-password transitions and hide/reopen in a test
  activity, without starting capture. Shift/Caps is verified separately through
  direct typing-panel buttons. Selected-text replacement remains an acceptance task.
  See [validation evidence and limits](mobile.md#android-validation--september-9-2026).
- **User feedback on the earlier voice companion:** functions on a Pixel 8 Pro,
  with setup and voice-only usability friction. This does not establish alpha04
  keyboard, broader phone or accessibility acceptance.
- **Acceptance remains open:** real-editor typing/dictation/correction, assistive
  technology, physical interruptions, broad device coverage and real Obtainium updates.
- **Not implemented:** iOS app or keyboard extension.

## Android milestones

| ID / status | Deliverable | Completion gate |
| --- | --- | --- |
| M1 — In progress | Select and document keyboard foundation; threat model and licensing review | Record provenance, required notices, license compatibility, permissions, input-data lifetime, import boundaries, and update trust. Do not import restricted code merely because its source is visible. |
| M2 — In progress; foundation released in alpha03 | Normal typing with integrated voice | Letters, numbers, symbols, shift/caps, deletion, Enter actions, selected-text replacement and cursor controls. Type → dictate → correct → type without switching IMEs. Password typing works; dictation and learning are disabled there. No stale result reaches a new field. |
| M3 — In progress; initial preferences released in alpha03 | Accessibility and useful customization | Complete setup, typing, correction, dictation, cancellation and reset using TalkBack and Switch Access. Adjustable key/label sizing, light/dark contrast, reachable layouts, optional feedback and repeat filtering. Essential actions have visible single-tap alternatives. Test large fonts and landscape, not just default screenshots. |
| M4 — In progress; bounded speech and preview extension released | Comfortable offline speech | Clear mic/loading/error state, tap start/stop and optional hold mode, pause tolerance, accessible preview warning/extension, bounded longer takes, and correction without repeating the whole message. Measure quality and latency on real hardware; do not promise recognition of every speech pattern. |
| M5 — Planned | Everyday language and editing support | Reviewed multilingual layouts/dictionaries, optional suggestions and correction, correction rejection, accents, emoji and text shortcuts. Explicit local learning controls and deletion; no password learning or automatic clipboard history. |
| M6 — In progress; persistent signed channel began with alpha03 | Broad compatibility and sustainable distribution | Defined Android/API and ABI support, diverse physical-device matrix, stable protected signing, install/update/rollback-policy testing, reproducible build inputs and release checksums. No forced downgrade or unsigned consumer APK. |

Security and accessibility gates apply to every milestone; they are not deferred
until M6. M2 is not full FUTO feature parity. Swipe typing requires a separate
engine, model/data licensing review, resource measurements, and acceptance tests.

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

Record source revision, version, signed artifact, test/device evidence, known limits,
dependency/license changes and upgrade behavior. Update the user guide and real
screenshots when visible behavior changes. Keep desktop releases and download links
independent. Never mark all milestones complete from compilation alone.
