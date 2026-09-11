# Utterleaf Keyboard and Voice — next system design

Design revision 1 · September 11, 2026 · **Design baseline merged; first native N1 slice implemented.**

The isolated [native candidate](../../mobile/next-keyboard/README.md) now implements
English tap typing, a main-thread editor gateway and local Incognito. Its
[execution evidence](../../mobile/next-keyboard/EXECUTION-EVIDENCE.md) is separate
from the interaction mockup. Composition, live decoding, voice, editing/terminal,
calibration and physical acceptance remain open; N1 is not complete.

The user requested a new system after reviewing LatinIME's adaptation cost. This
design chooses a Kotlin-owned keyboard core and UI, with explicit boundaries for
linguistic decoding and offline speech. The LatinIME experiment remains a
comparison build and source of regression scenarios. Android alpha13 remains the
working voice/edit/terminal reference. Neither application is replaced by this document.

## Product decision

Make ordinary typing immediate, voice useful in one tap, and editing accessible
without covering the host app with stacked controls. FUTO is the preferred
interaction reference. Hacker's Keyboard informs explicit power controls.
Utterleaf contributes its local voice, verified asset and editor-action contracts.
LatinIME contributes lessons in touch geometry, composition, language layouts and
accessibility; its complete application and native dictionary stack are not default
dependencies of the new core. Selected reuse requires a scoped dependency decision.

The design improves ownership and feature access; it does **not** establish that a
new implementation is faster, smaller, safer or more accurate. Those claims require
the matched measurements and acceptance gates below.

## The experience

- **Type:** staggered keys, broad Space, consistent punctuation/Enter, optional
  hints and rows. A single contextual bar provides actions, suggestions and a
  reachable microphone. Automatic correction is reversible and independent of
  suggestions; unavailable resources have an honest setup state.
- **Edit:** selection, arrows, Home/End, Undo/Redo and explicit Cut/Copy/Paste replace
  the key deck. ABC returns in one tap. No clipboard history or passive reads.
- **Terminal:** explicit mode, visible modifier state, Esc/Tab/navigation and a
  replacing Fn layer. Letters remain reachable without opening another menu.
  Voice insertion cannot emit Enter or execute a command.
- **Voice:** tap microphone, Stop or Cancel, then editable Review and Insert.
  Optional hold/release insertion is a separately enabled flow. Models are loaded
  only for explicit voice use; typing does not depend on microphone permission,
  a speech model or worker availability.
- **Comfort:** dark default, light/high-contrast options, height and bottom space,
  one-handed alignment, feedback/timing, language/layout and independently optional
  rows. Changes have a private practice field, Apply/Discard and scoped Reset.
- **Touch and privacy:** stable visible keys with gap-aware proximity zones;
  optional correction-informed calibration is Off by default. Off/Learn/Frozen
  are separate from a visible, sticky Incognito toggle that overrides learning.
  Sensitive fields enforce Incognito. [Adaptive touch](ADAPTIVE-TOUCH.md) defines
  the bounded aggregate data, weak correction signals and cancellation rules.

See [the experience specification](EXPERIENCE.md) for placement, state transitions,
gestures, accessibility, errors and complete baseline capability coverage.
`utterleaf-next-keyboard.html` is a self-contained conversation mockup: key input,
mode changes, selection controls, voice state transitions and preference drafts are
simulated locally. It never records, transcribes, accesses a clipboard or contacts
an Android editor. It is not native touch, speech, accessibility or performance evidence.
Calibration graphics are illustrative, not learned from the user's touches.

## Why the core is different

One main-thread **EditorGateway** owns every editor read and mutation. A renderer,
speech callback or decoder cannot keep an InputConnection and write independently.
Each asynchronous request captures immutable inputs and purpose-specific identity;
publication rechecks the editor and operation before touching state.

Typing, layout and feedback take the short path. Suggestion updates are coalesced;
ended gestures and explicit edit commands have ordered, bounded handling. A delayed
gesture A must neither overwrite gesture B nor silently lose A's word. Native
decoding and model work cannot hold a UI lock. See [architecture](ARCHITECTURE.md)
for the concrete contracts and the remaining decoder/transport decisions.

## What we reuse, reimplement and exclude

| Source | Keep as behavior or carefully adapted component | Do not carry by default |
| --- | --- | --- |
| Utterleaf alpha13 | Voice take cancellation/review; pinned whisper engine; verified model catalog/import; editor actions; terminal dispatch rules; local preference semantics | Button-based letter renderer, tightly coupled panel/service state, automatic trust in old tests after adaptation |
| LatinIME experiment | Session, malformed-input and lifecycle regressions; pointer/layout/accessibility techniques; published provenance for any selected source | Whole service hierarchy, global mutable keyboard/composer state, native dictionary storage as an unavoidable dependency |
| FUTO | Reachable actions, resizing, configurable gestures and feedback, voice-first access, readable correction choices | Code/assets without an explicit decision; passive clipboard history or learning features outside our policy |
| Hacker's Keyboard | Reachable modifier/navigation/function keys and visible state | Legacy Android implementation or a permanent desktop-sized row stack in Daily mode |

[Reference review](REFERENCE-REVIEW.md) records primary sources, assumptions and
the distinction between documented reference behavior and measured comparisons.
The [FUTO capability matrix](FUTO-CAPABILITY-MATRIX.md) tracks the broader utility
baseline: rows, alternates/hints, gestures, actions, languages, voice, modes and
customization, including explicit privacy differences and unverified gates.

## Delivery with visible progress

| Milestone | Concrete output | Exit evidence |
| --- | --- | --- |
| N0 — Design baseline | This system spec, interactive concept and reviewed interface contracts | Resolve inconsistent states and failure paths; retain every required parity row |
| N1 — Keyboard core comparison | Isolated `mobile/next-keyboard/` candidate: renderer, main-thread editor gateway, two-thumb input, composition, Unicode deletion and deterministic fake decoder | Same synthetic sequences against candidate and LatinIME; no wrong-field edits or lost accepted actions; first named-phone comfort/latency sample |
| N2 — Useful integrated alpha | Adapt existing voice/model and Edit/Terminal behavior behind the gateway; settings/practice; basic language layouts | Cancellation, capability failures, model rollback, settings reset and process recovery; feature parity with alpha13's supported scope |
| N3 — Language and gesture quality | Reviewed linguistic backend/assets; correction, explicit dictionary, emoji and ordered real swipe; optional bounded touch calibration | Named-language typo/swipe repair results, Unicode/caret tests, calibration/Incognito interleavings and physical error rates; no claims from a fake decoder |
| N4 — Complete customization/interoperability | Inline autofill, supported mixed languages, split/floating modes and bounded layout import | Per-capability editor/device/accessibility evidence; unavailable features stay clearly absent from shipped controls |
| N5 — Replacement release | Performance, physical accessibility, migration, signing and Obtainium validation | Published named-device results, preserved user assets/settings, verified signed upgrade and return path |

N2 voice and Edit/Terminal adapters may be developed in parallel only after N1's
gateway contract stabilizes, with exclusive files. A linguistic-backend feasibility
investigation starts during N1 so swipe/dictionary risk is discovered early. N3 is
required for the everyday replacement; a useful N2 alpha is not renamed completion.

Implementation proceeds through vertical slices: ordinary typing → delayed suggestion
→ field switch → rejected stale completion, plus balanced held modifiers. It must
include real editor integration, not just a styled keyboard. This design authorizes
no claim of a replacement APK; preserve the two existing applications during comparison.

## Non-negotiable behavior

Security first, privacy second, convenience third. No ambient capture, telemetry,
passive lexical learning or typing history, clipboard monitoring/history, contacts/accounts integration,
network fallback, unverified assets or executable layout extensions. Preferences
stay local; Reset never deletes models, dictionaries or other user data. Logs and
performance traces use synthetic text and opt-in diagnostics without content.
The user explicitly authorized optional geometric calibration; it remains Off by
default, local and separately clearable. Incognito learns nothing. Preference
reset preserves calibration data and never silently exits active manual Incognito.

There is one native renderer/input path in a shipped candidate. The preserved
LatinIME application is an external benchmark, not a hidden fallback engine inside
the new service. Voice-only IME and explicit recognition-activity workflows remain
required compatibility targets through the same voice contracts, separate
entry-point coordinators and one exclusive capture/inference lease.

## Evidence and ownership

[Performance and acceptance](PERFORMANCE-AND-ACCEPTANCE.md) defines provisional
budgets and reproducible measurements. No benchmark has been run on this proposed
system. Existing foundation acceptance is 121 emulator / 12 JVM tests with PRs
[21](https://github.com/RioPlay/utterleaf/pull/21) and
[22](https://github.com/RioPlay/utterleaf/pull/22) merged; these counts do not transfer
to the new core.
[Design review](REVIEW.md) records the specialist/adversarial findings and their
resolution without transferring that existing implementation evidence.

Development uses Aden first: scoped symbol tree, bounded exact search, symbol and
caller inspection, then source/test verification. Missing framework/JNI edges prove
nothing. Assign one owner per source/test file and one operator for builds/emulators;
specialist implementation is followed by independent adversarial review.

This design supersedes the earlier sole-LatinIME-renderer decision **for the new
candidate**. It leaves the LatinIME experiment's implementation/provenance intact.
