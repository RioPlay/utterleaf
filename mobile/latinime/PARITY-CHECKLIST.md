# Utterleaf keyboard baseline and reference checklist

The product is **LatinIME's keyboard foundation, FUTO-inspired comfort and
refinements, Hacker's Keyboard-style functionality, and Utterleaf's own voice
engine**. These are four parts of the same baseline, not successive products.
Keep LatinIME's coherent input, composition and touch architecture. FUTO and
Hacker's Keyboard are experience/functionality references, not automatic source
dependencies or permission to copy branding, assets or differently licensed code.
Utterleaf's security/privacy rules apply at every stage.

Status: baseline acceptance checklist, September 10, 2026. Implementation, testing
and shipment are authorized; this checklist does not establish verified parity.
The isolated experiment remains incomplete; signed preview01 is published for testing.
This ordering refines the
[adversarial review](ADVERSARIAL-PLAN-REVIEW.md): an early experimental APK can be
small, but a claimed replacement cannot quietly omit key baseline capabilities.

## Evidence and completion rules

This first pass uses current official documentation and the supplied alphabetic
and symbol screenshots. Documentation is not a version-pinned device comparison.
Before calling a row equivalent, record the exact reference APK version/source,
device, OS, language, relevant settings and a synthetic task result. Do not infer
behavior from how an icon looks. Resolve discrepancies between documentation and
the tested version explicitly.

- **Required:** part of the intended everyday replacement experience.
- **Configurable:** the capability belongs in the baseline, but people choose its
  behavior or whether to enable it. This does not mean it can be omitted while
  claiming parity.
- **Separate gate:** valid target requiring dedicated feasibility, licensing or
  platform work. Record it as incomplete until verified, not as a hidden omission.
- **Deliberate difference:** incompatible with product policy or unnecessary to
  equivalent user outcomes. Explain the difference honestly.

All rows start **pending in the LatinIME port**. Existing Utterleaf behavior is a
regression reference, not evidence that the new port implements it. Track progress
per ID as `pending → source implemented → automated evidence → physical evidence`,
with file/test references, limitations and supported configurations. Screenshots
alone cannot advance behavior to verified.

### Current scoped evidence

The following rows have partial automated evidence in the isolated experiment;
none has complete physical acceptance. See [execution evidence](EXECUTION-EVIDENCE.md)
for source/test names, commands and limitations. Unlisted rows remain pending.

| IDs | Current evidence | Still required |
| --- | --- | --- |
| K01, K02 | Real IME injected letter/Space/Delete input, field/cursor switching, password restart and deferred lifecycle recovery. Separate-host IME process kill/rebind passed after same-field user re-show. | Automatic reappearance, broader symbol/Enter/editor tasks and physical one-/two-handed comfort. |
| K05, K07, K08 | Height/bottom spacing, feedback preferences and dark/light theme; live Apply/Reset and replacement-view typing. | Optional rows, remaining timing/theme controls and physical/accessibility checks. |
| L06 | Controlled subtype callback preserves current cursor/cache; old decoder identities are rejected. | User-facing language controls, dictionary quality and language-specific acceptance. |
| L08 | Cancellation/input-isolation tests and safe missing-policy handling only. The linked native gesture decoder is absent. | Reviewed swipe implementation/assets, recognition quality and device acceptance. |
| X03 | Local preference persistence, draft discard, scoped reset, recreation and bounded abrupt-process-death probe. Automatic dictionary reload failures preserve files. Dictionary write transactions passed failure tests and six external emulator process-death cases. | Physical storage/power-loss acceptance, format migration, shipping-app migration and comprehensive upgrade/model preservation. |

## Everyday keyboard

The supplied screenshots establish the requested visual vocabulary. FUTO documents
resizing, optional rows, hints, press timing, spacing/capitalization, feedback and
inline autofill controls in [Keyboard & Typing](https://docs.keyboard.futo.tech/settings/keyboardtyping).
The following acceptance tasks are Utterleaf proposals, not claims about FUTO's
measured performance.

| ID | Capability | Class | Acceptance task |
| --- | --- | --- | --- |
| K01 | Familiar staggered layout and comfortable Space/Enter/Delete | Required | Type one- and two-handed; check B/Space errors, overlap, edge touches and stable key locations across panels. |
| K02 | Letters, symbols, numbers and context-appropriate Enter | Required | Enter a message, URL, email, decimal and multiline text without unintended Send. |
| K03 | Accents and secondary characters | Required | Hold, slide and release the intended alternate; cancel without insertion; provide an accessible alternative. |
| K04 | Visible hints and alternate-key ordering | Configurable | Change supported hint/order preferences and verify they match actual output and survive restart. |
| K05 | Sizing and optional number/arrow rows | Configurable | Adjust geometry in practice; verify portrait/landscape and reset without losing user data. |
| K06 | Auto-capitalization, punctuation spacing and double-space period | Configurable | Test every enabled/disabled mode in prose and literal fields; no missing or doubled separators. |
| K07 | Sound, haptics, key previews and press timing | Configurable | Independently change feedback/timing; verify sensitive-field policy and no delayed key dispatch. |
| K08 | Theme and border choices | Configurable | Test dark, light and contrast-focused Utterleaf themes, readable hints and state feedback. |
| K09 | Inline autofill interoperability | Separate gate | Test a supported password manager with platform-provided suggestions; no credential logging or persistence by the keyboard. |

FUTO's [theme settings](https://docs.keyboard.futo.tech/settings/theme) establish
theme/border choices. Utterleaf should preserve user choice with its own assets.
Its dark default is the requested preference, not a claim of universal comfort.

## Correction, languages and swipe

FUTO documents adjustable local prediction/correction and word exclusion in
[Text Prediction](https://docs.keyboard.futo.tech/settings/textprediction).
[Languages & Models](https://docs.keyboard.futo.tech/settings/languagesmodels)
distinguishes installed resources, layouts, switching and multilingual input.
Its documentation currently identifies an English-only transformer option and
language-dependent speech models; do not promise universal language parity.

| ID | Capability | Class | Acceptance task |
| --- | --- | --- | --- |
| L01 | Suggestions and reversible correction | Required | Correct a typo, retain a literal name, undo a replacement and reject it without repeated unwanted correction. |
| L02 | Independent suggestions/correction controls and strength | Configurable | Check Off/conservative/stronger behavior with no hidden coupling or unavailable controls. |
| L03 | Explicit personal dictionary and blocked suggestions | Required | Add/remove an entry deliberately, verify effect, and retain entries across preference reset. |
| L04 | Offensive-word filtering preference | Configurable | Respect the selected filtering policy without silently altering literal user-entered words. Default remains a review decision. |
| L05 | Clear language/layout/resource status | Required | Set up a language without mistaking an available layout for an installed dictionary or speech model. |
| L06 | Reachable language switching | Configurable | Switch without unintended cursor movement or losing composition; preserve a visible alternative. |
| L07 | Mixed-language correction on supported language pairs | Separate gate | Native speakers test the declared pair, names, accents and switching; document unsupported scripts/pairs. |
| L08 | Dependable offline swipe | Separate gate | Compare recognition and repair on the same synthetic phrases; verify decoder/model licensing, bounds, cancellation and no network fallback. |
| L09 | Local next-word prediction | Separate gate | Measure useful completions, repair effort and latency using bounded current-session context; no retained typing history. |
| L10 | Emoji entry and local discovery | Required | Insert and delete complete sequences; test skin tones/combined emoji and editor compatibility. |

**Swipe stays in the baseline target.** It can arrive after the first internal
build, but an APK without it is not an equivalent replacement for swipe users.
Likewise, a dictionary-only decoder is not evidence of matching contextual quality.
Choose implementation dependencies by quality, provenance and security evidence,
not by copying another keyboard's model stack.

## Gestures and quick actions

FUTO's [gesture guide](https://docs.keyboard.futo.tech/gestures), detailed
[Space behavior](https://docs.keyboard.futo.tech/gestures/spacebar) and
[Backspace behavior](https://docs.keyboard.futo.tech/gestures/backspace) establish
cursor, symbol and deletion shortcuts. Its [actions](https://docs.keyboard.futo.tech/actions/supportedactions)
and [assignment controls](https://docs.keyboard.futo.tech/actions/assigningactions)
provide editing, navigation, voice and keyboard-mode access with configurable
placement. Match useful outcomes without assuming synthetic Ctrl shortcuts work
in every Android editor.

| ID | Capability | Class | Acceptance task |
| --- | --- | --- | --- |
| A01 | Space cursor gesture and selectable alternate behavior | Configurable | One gesture has one owner; switching its mode never triggers both cursor and language actions. |
| A02 | Backspace repeat and drag deletion | Configurable | Treat repeat and drag separately; preview destructive selection, cancel safely and stop on focus loss. |
| A03 | Slide from symbols and return to letters | Configurable | Enter one symbol in one gesture; release/cancel leaves the correct layer and inserts at most once. |
| A04 | Punctuation and shortcut popups | Required | Reach everyday punctuation quickly with clear selection feedback and an accessible alternative. |
| A05 | Compact actions with pin/reorder/hide choices | Configurable | Customize without losing access to Settings/Reset; test toolbar overflow on narrow screens. |
| A06 | Undo/redo/select/cut/copy/paste/navigation | Required | Verify actual editor text/selection and stale-control rejection; never silently reinterpret Copy as a terminal interrupt. |
| A07 | One-handed mode | Configurable | Left/right layouts retain usable targets, microphone reach and a clear exit. |
| A08 | Split and floating modes | Separate gate | Test tablet/foldable geometry, insets, movement, focus and accessibility; explicitly exclude untested configurations. |
| A09 | Custom data-defined layouts | Separate gate | Validate bounded schema, invalid-layout recovery and escape to a known-good layout; no scripts or executable extensions. |

FUTO documents developer-accessible [custom layouts](https://docs.keyboard.futo.tech/settings/customlayouts).
Ordinary Utterleaf sizing, gestures and action preferences must not require editing
layout files. Full custom layouts are a distinct advanced capability.

## Voice, setup and accessibility

[FUTO voice settings](https://docs.keyboard.futo.tech/settings/voiceinput) document
local voice, audio-route/focus choices, sounds, extended takes and silence stopping.
Its page also lists a progress option with no current effect; Utterleaf should
not reproduce nonfunctional controls. Silence stopping is distinct from insertion,
and insertion is distinct from sending or executing text.

| ID | Capability | Class | Acceptance task |
| --- | --- | --- | --- |
| V01 | Reachable offline microphone workflow | Required | Start explicitly, stop/cancel, inspect and insert once; no input reaches a later editor session. |
| V02 | Supported audio route and focus preferences | Configurable | Test wired/Bluetooth capture, interruption, mic contention, denial/revocation and recovery on named phones. |
| V03 | Longer takes and silence stop | Configurable | Show recording state/time/resource limits; stop on silence only when enabled, preserve manual stop and never implicitly Send. |
| V04 | Feedback and symbol handling | Configurable | Verify audio cues can be disabled and selected symbol behavior preserves intended text. |
| V05 | Model/language readiness and setup recovery | Required | Explain missing/incompatible assets and recover from canceled/failed import without breaking installed models. |
| X01 | Accessible typing and editing | Required | Explore keys, select alternatives, correct and navigate to host controls with current TalkBack and supported access methods. |
| X02 | Readable controls and configurable comfort | Required | Test large text, contrast, value announcements and non-gesture alternatives without clipping or hidden required actions. |
| X03 | Preferences, practice and reset | Required | Verify persistence, quick-toggle reversal, Apply/Cancel where applicable, migration and non-destructive reset. |

X01–X03 are Utterleaf acceptance requirements. They are not claims that FUTO has
passed equivalent testing. Microphone/speech access in sensitive fields continues
to follow Utterleaf's stricter policy.

## Deliberate policy differences

| Reference capability or mechanism | Utterleaf decision |
| --- | --- |
| Clipboard manager/history, listed among reference actions | Explicit clipboard operations only; no monitoring/history. |
| Personalized suggestions learned from communications/typing, described in prediction settings | No passive learning; reviewed local models, bounded transient context and explicit dictionary entries instead. |
| External voice provider, offered in voice settings | No silent external/cloud fallback; preserve the local speech guarantee. Any provider integration requires a separately reviewed policy. |
| Exact proprietary/model/internal implementation | Match the outcome with reviewed compatible dependencies; no automatic import of source, models or assets. |
| Menu item that currently has no effect | Omit unavailable controls; explain supported capabilities honestly. |

These differences must remain visible in any eventual comparison. Do not advertise
unqualified feature-for-feature identity when intentionally excluding capabilities.
An alternative implementation or privacy rule can be better suited to Utterleaf
without being equivalent in every feature.

## Required power and voice integration

Hacker's Keyboard's [user guide](https://github.com/klausw/hackerskeyboard/wiki/UsersGuide)
provides the functional reference: desktop-style modifiers, navigation and function
keys with application-dependent behavior. Its historical compatibility claims
must be retested on current editors and terminals.

| ID | Baseline requirement | Acceptance task |
| --- | --- | --- |
| T01 | Reachable Ctrl, Alt, Shift and Meta where supported | Test held chords, one-shot state, explicit lock choices and cancellation without stuck modifiers. |
| T02 | Esc, Tab, forward Delete, arrows, Home/End, Page Up/Down and Fn-accessed F1–F12 | Verify actual behavior in named terminal/remote-editor applications, not just emitted key events. |
| T03 | Selection and word editing with modifiers | Exercise Shift-navigation, Ctrl+Backspace and supported combinations without overlapping gesture actions. |
| T04 | Comfortable optional power layout | Keep ordinary typing spacious; expose terminal controls directly when the power layout is selected, with a clear return path. |
| T05 | Safe terminal semantics | Distinguish Copy from Ctrl+C, newline from execution and text insertion from submission; reject stale actions after focus changes. |
| E01 | Utterleaf's existing local voice engine | Integrate its verified model handling, explicit recording, cancellation and editable output with LatinIME's active editor session; do not substitute another keyboard's speech stack. |

These requirements block calling the migration complete. They can be absent from
an internal build experiment, but are not optional future add-ons to the intended
product. This table defines functional scope, not universal Android app support.

## Utterleaf integration details and further refinements

These are product targets, not claims that the references lack them. U01–U03
detail the required power/voice integration above. U04–U06 guide refinement of
the complete hybrid. Preserve already-promised Utterleaf workflows during migration.

| ID | Refinement | Evidence needed |
| --- | --- | --- |
| U01 | Full optional Terminal layer: modifiers, forward Delete, navigation and Fn | Named terminal/editor matrix, held/one-shot state, cancellation and safe distinction between text actions and commands |
| U02 | Hold-to-speak/release-to-insert plus expandable editable review | One-handed task success, clear mode feedback, cancellation and no accidental submission |
| U03 | Between-take switching among verified installed speech models | Accurate availability/size/quality guidance; no races with decoding/import or lost assets |
| U04 | Quicker configuration and precise practice feedback | People can tune comfort and restore defaults without assistance or private data collection |
| U05 | Better responsiveness and hardware use where justified | Matched accuracy/latency/memory/battery evidence; GPU/NPU feasibility remains separate |
| U06 | Friendly Utterleaf identity | Original assets, consistent controls and restrained Utterling use without stealing typing space |

## Work order and immediate deliverables

1. Review this checklist and its deliberate differences. Resolve initial languages,
   gesture defaults, action placement and the desired correction behavior.
2. Capture the reference version/settings and synthetic task definitions. Produce
   Daily/Symbols/Edit/Terminal/Voice/Settings prototypes for review.
3. After implementation approval, build the full restricted LatinIME experiment
   described in the adversarial plan. Do not substitute native-only success for
   an actual IME.
4. Implement and validate the complete hybrid in coherent slices: LatinIME typing,
   FUTO-referenced refinements, Hacker-style power controls and Utterleaf voice.
   Track all separate-gate rows openly. Retain existing workflows before migration.
5. Run side-by-side task comparisons and record accepted differences. Only then
   describe the baseline as comparable for the tested users/languages/devices.
6. Refine beyond it using demonstrated friction, preserving settings choice and
   the security/privacy invariants.

No code/build/device evidence was produced in preparing this document. Official
documentation and screenshots support the reference inventory; observed parity,
physical comfort and quantitative superiority remain unverified.
