# Android keyboard capability plan

[Mobile roadmap](mobile-roadmap.md) · [Layout design](android-keyboard-design.md) · [Security design](mobile-security.md)

Reviewed September 9, 2026. The objective is an independently implemented Utterleaf
keyboard combining a polished everyday experience with an optional terminal/power
layout. FUTO Keyboard and Hacker's Keyboard are product references. Full feature
coverage is the development goal, not a claim of current parity, compatibility,
code reuse or release availability. Security comes first, then privacy.

## Reference review and design decisions

Only official user-facing documentation and public product imagery were inspected;
no third-party keyboard implementation code was reviewed or imported for this plan.
Links identify the reference behavior; acceptance criteria below are Utterleaf's
proposed requirements. Source visibility alone does not establish a reuse license.

| Reference | Observed product direction | Utterleaf decision |
| --- | --- | --- |
| [FUTO overview](https://keyboard.futo.tech/) and [official product image](https://keyboard.futo.tech/assets/decoration-hero.webp) | Offline speech, swipe, correction, prediction and themes; familiar staggered letters, broad spacebar and compact action/suggestion area | Keep the everyday layout readable and familiar, with Utterleaf's own colors/assets. Add useful actions without filling the letter area with utility keys. |
| [FUTO typing settings](https://docs.keyboard.futo.tech/settings/keyboardtyping) and [actions](https://docs.keyboard.futo.tech/actions/supportedactions) | Resizing, optional number/arrows rows, typing behavior, emoji, editing actions and alternate keyboard modes | Independent sizing, reachable editing, optional number row and visible alternatives to gestures; later one-handed, split and floating modes. |
| [FUTO language management](https://docs.keyboard.futo.tech/settings/languagesmodels) and [prediction](https://docs.keyboard.futo.tech/settings/textprediction) | Separate layouts/resources, multilingual suggestions, correction controls and optional personalization | Separate layout, dictionary, composition and speech support claims. Make correction reversible and learning explicitly opt-in and erasable. |
| [Hacker's Keyboard user guide](https://github.com/klausw/hackerskeyboard/wiki/UsersGuide) and [official compact-layout image](https://raw.githubusercontent.com/klausw/hackerskeyboard/master/hk-5row-en-s.png) | Dedicated number/utility keys, Ctrl/Alt/Meta, arrows and Fn-accessed navigation/function keys | Offer a deliberate power layout, with a full key inventory and clear modifier state. Preserve a comfortable everyday default. |
| [Hacker's Keyboard FAQ](https://github.com/klausw/hackerskeyboard/wiki/FrequentlyAskedQuestions) | Documents small-screen density and application-dependent special-key behavior | Fit power controls through optional rows/layers and orientation settings; verify terminal/editor behavior independently. The guide's older Android examples are historical, not present-day certification. |

The FUTO image is promotional artwork; the Hacker's Keyboard image is an older
compact layout. Both were inspected as references, not reproduced as Utterleaf UI
or used as evidence that a feature works. FUTO's documented gesture shortcuts also
show why gesture typing, navigation and destructive gestures need separate settings
and visible alternatives. [FUTO gestures](https://docs.keyboard.futo.tech/gestures)

The user's additional FUTO examples emphasize the complete typing experience:
editing icons, a suggestion strip with a microphone, optional number row, staggered
letters, secondary character hints and a symbol page that keeps familiar geometry.
Treat those as requirements to implement and verify. An empty or decorative
suggestion strip must not imply that prediction exists.

## Current implementation and evidence boundary

Alpha04 provides English letters/symbols, Shift/Caps, left/right cursor movement,
deletion and editor actions; local speech with explicit insertion; basic appearance,
feedback and repeat preferences; private model import and signed distribution.
The alpha05 staggered-layout/toolbar revision, optional number-row preference and
initial terminal controls/`TerminalInput` dispatch are in progress; acceptance is
pending. Planned controls in this pass include Esc/Tab/Ctrl/Alt, navigation and an
F1–F12 layer with one-shot modifiers. This does not establish completed power-mode
compatibility or add suggestions. Current status belongs in the [layout design](android-keyboard-design.md)
and [mobile guide](mobile.md). Do not treat source or screenshots as a published APK.

The recorded alpha04 CI baseline is 4 JVM, 11 API 35 emulator and 3 release-contract
tests. Live IME coverage is letters, cursor movement, deletion, Done, voice-panel to
password-field transition, and hide/reopen; it starts no microphone capture.
Shift/Caps coverage is a separate direct-panel test. Selected-text replacement,
Ctrl/Alt/Meta/Fn, predictive composition and terminal support are not established by
those results. [Recorded evidence](mobile.md#android-validation--september-9-2026)

The alpha04 implementation uses `commitText` for text, key events for deletion/arrows,
and `performEditorAction` for supported Enter actions. It rejects `TYPE_NULL` fields;
its four-option settings and basic dispatch do not establish terminal support.
Alpha05 expands this foundation. Utility key labels and an event dispatcher still
need the compatibility and lifecycle gates below.

## Prioritized capability and acceptance matrix

**Implemented** describes the foundation above. **Next** is active implementation
or acceptance work. **Later** requires the listed preceding foundation. None
of these labels asserts every physical/editor/accessibility acceptance gate passed.

| Phase / priority | Capability and status | Acceptance gate |
| --- | --- | --- |
| P0 / security, continuous | **Implemented foundation; next hardening:** editor sessions, capture/import boundaries | Zero late commits across 100 synthetic field/hide/restart/lock transitions. Cancel releases capture and clears speech/composition/modifiers; password and unknown-sensitive contexts never learn, predict, read back or dictate. Denied permission never blocks ordinary typing. No input in logs, telemetry or preference files. |
| P1 / next, alpha05 layout | **In progress:** everyday geometry, symbols, toolbar and optional number row | Staggered letters, wide spacebar, direct comma/period and obvious Voice/Tools. Number-row preference persists and does not collapse key widths. Keep letter/symbol pages' utility positions stable. Verify all layers in both orientations, smallest supported width, largest supported labels and both themes. No clipped essential control or forced scroll during ordinary typing. Preserve typing/voice/switch access when expanded. Validate real IME screenshots separately from settings previews. |
| P1 / next refinement | **Planned:** secondary hints and alternate characters | Small secondary symbol/number hints remain legible without competing with letter labels. Optional long-press character selection has configurable timing and a visible single-tap symbols/accent route for every character. Test cancel, slide-off, repeat filtering and assistive exploration; no essential character is gesture-only. |
| P1 / next | **Implemented basic editing; next completion:** selection, Unicode, Enter and touch behavior | Real-IME tests for selected-text replacement, forward/back delete, cursor boundaries, combining marks, emoji/ZWJ and multiline text; all supported Enter actions and no-enter-action flags. Direct-panel and live-IME Shift/Caps tests remain separate. Script 1,000 actions with zero duplicates or reordered characters; verify intended double letters with repeat filtering off/on. |
| P2 / alongside P1; release after P0/P1 gates | **In progress subset:** terminal/power controls and dispatch | Alpha05 work includes Esc, Tab, Ctrl, Alt, four arrows, Home/End, PgUp/PgDn and Fn/F1–F12 with `TerminalInput`. Meta, forward Delete, Insert and numpad remain additional acceptance work. Every displayed key needs an explicit contract and named editor evidence. No hidden automatic command submission or global key injection. |
| P2 / next | **In progress:** one-shot modifiers; **planned:** latch/multi-touch and advanced editing | Provide explicit modifier release. Test Ctrl+C/D/Z/A, Alt combinations, Shift+arrows, tab versus focus navigation, repeats and cancel. Clear all local modifiers on mode/language/field changes and dismissal; never send cleanup keys to a newly bound editor. Distinguish Caps Lock, Shift and Shift Lock if offered. |
| P2 / next | **Planned:** select/copy/cut/paste/undo/redo toolbar | Named editor actions where supported; no automatic clipboard reading/history. Verify undo/redo separately in native, browser, terminal and rich-text editors; do not assume Ctrl+Z/Y always edits text. Explicit paste reads current clipboard only, handles empty/oversized content, and never appends Enter in terminals. Provide a visible select-mode alternative to Shift+arrows. Refused/unsupported actions do not trigger blind retries or duplicate fallback edits. |
| P3 / next after editor foundation | **Planned:** language layouts, accents, compose/dead keys and emoji | Start with a named, reviewed alphabetic-layout set, including QWERTY/QWERTZ/AZERTY alternatives; publish per-language layout/dictionary/speech status. Visible accent/compose picker and language switch work without holds. Test uppercase accents, RTL mixing, Unicode sequences and field changes mid-compose. Emoji search stays local; optional recents have off/clear controls. |
| P3 / next | **Planned:** local vocabulary, snippets and conservative correction | Explicit vocabulary additions and inspect/delete/export. Suggestions and auto-correction have separate switches; direct replacement requires a valid composing range and immediately reversible correction. Test names, negation, URLs, email, code and rejected corrections. Preserve a literal typing mode in power layout. Snippets insert explicit user-selected text, never executable scripts or automatic submit actions. |
| P4 / later, after P3 | **Planned:** prediction and multilingual composition | Review engine/dictionary/model provenance, licensing, network behavior and resource cost first. Bound per-session context (initial design cap: 256 Unicode code points); cancel work and clear context on field change. Learning defaults off; inspect/delete all learned data and honor no-learning editor flags. Complex-script IMEs require their own composition engine and native-speaker evaluation, not a character-map claim. |
| P4 / later, after P3/P4 language engine | **Planned:** swipe/glide typing | Independently review engine/model/data licenses; no unreviewed proprietary blob. Measure words corrected, latency, RAM, battery and error recovery on named phones/languages. Preserve tap typing and a visible correction path; gesture navigation and destructive gestures must not collide. Do not retain swipe paths or typed words for training implicitly. |
| P5 / later, incremental | **Partial preferences implemented:** fuller ergonomics and integration | Independent height/label sizing, orientation profiles, optional number/arrows rows, one-handed alignment, split/floating modes, adjustable repeat/dwell/feedback and theme contrast. Optional key hints, alternate-character popups, auto-capitalization and double-space period are independently configurable. Test mode switching without loss of editor focus or input state. |
| P5 / later | **Planned:** declarative custom layouts, inline autofill and further power compatibility | Bounded versioned data-only layout imports with preview/rollback, no executable plugins. Compose/dead-key/AltGr coverage gets a locale matrix. Inline autofill uses supported Android/password-manager integration; the IME does not scrape, persist or learn credentials. An explicit show-keyboard action may be evaluated only where Android permits it, without background capture or forced app control. |
| All phases / release gate | **Implemented signing; broader acceptance open:** accessibility, updates and performance | Preserve certificate/package identity; verify prior-to-new APK install and rollback policy. Test preference/model preservation separately. Real Obtainium, phones and assistive-technology workflows remain external gates. Record cold start, touch-to-dispatch p50/p95, memory and battery; initial engineering target is p95 ≤50 ms for ordinary key dispatch on named midrange hardware, with language/speech work off the UI thread. |

P2 can deliver a useful power layout before prediction/swipe work. P3 resource
review can proceed alongside P2 once ownership is split; it cannot bypass P0/P1
editor correctness. Do not delay basic modifier/terminal functionality behind a
large language model. Optional advanced features must leave precise offline typing
available on lower-resource devices.

## Modifier and InputConnection contract

Android recommends `commitText` for ordinary text; raw key events can be delivered
asynchronously after focus changes, and an accepted call does not prove the intended
editor effect. Use text/composition APIs for everyday input and a separately tested
special-key path for power mode. [Android InputConnection](https://developer.android.com/reference/android/view/inputmethod/InputConnection)

| Boundary | Required design and adversarial check |
| --- | --- |
| Text versus command | Keep typed Unicode, composing text, editor actions and physical-style key chords as distinct operations. Decide Tab/Enter behavior by explicit mode plus editor contract. Never substitute `commitText("c")` when Ctrl+C failed. |
| Modifier lifecycle | Keep one-shot/latch state in the active session only. Prefer complete down/up chord transactions per tap to leaving a remote modifier held. For hold/repeat, bind events to one connection generation and cancel immediately on lifecycle loss. Test cancel between every event and zero modifier leakage into the next editor. |
| Key-event metadata | Specify action order, key code, meta-state, timestamps/repeats and soft-keyboard identification in the contract; compare event traces with observed application effects. Do not infer success merely from a true API return. |
| Raw terminals | Review `TYPE_NULL` as a separate explicit raw-key capability; current Utterleaf rejects it. Raw mode keeps speech, learning and surrounding-text reads off because field sensitivity cannot be established. A label such as “terminal” does not imply passwords typed there are non-sensitive. |
| Selection/composition | Track editor-provided selection and composing ranges; invalidate pending edits on changes. Request only bounded context needed for the selected feature. No full-document extraction or clipboard capture as an editing workaround. Balance every batch edit, including failures. |
| Failure and compatibility | An invalid connection fails closed. Do not replay a chord in a new field or send a second speculative fallback. A terminal-specific escape/Tab mapping needs explicit configuration and versioned evidence; never infer it from private text or an app title. |

Respect `EditorInfo` action flags, field types and `IME_FLAG_NO_PERSONALIZED_LEARNING`;
the last is a request that this implementation must enforce before any learning
path. Terminal/power mode disables smart spacing/capitalization/correction by
default. [Android EditorInfo](https://developer.android.com/reference/android/view/inputmethod/EditorInfo)

## Compatibility and accessibility evidence

Maintain rows for Android EditText/Compose, browser plain and rich fields,
messaging editors, Termux, ConnectBot and a selected remote-desktop client. Record
app/Android versions, phone, layout, exact action, expected result, observed result,
and unsupported behavior. These are proposed test targets, not endorsements or
claims of current compatibility. Use synthetic local terminal sessions/remote
fixtures; do not test chords against valuable live sessions.

The terminal matrix must distinguish Ctrl+C interrupt from copy, Ctrl+D end-of-input,
Tab completion from focus traversal, Escape dismissal from application input, and
selection from cursor movement. Verify function keys/numpad and composed characters
separately. An app may reject special keys; no root, accessibility-service injection
or hidden global shortcut workaround is permitted. Hacker's Keyboard itself
documents application-specific limitations. [Official FAQ](https://github.com/klausw/hackerskeyboard/wiki/FrequentlyAskedQuestions)

For each layout, complete enable → type → correct → dictate → stop/discard → reset
with TalkBack, Switch Access and external input, then with participating users of
assistive technology. Modifiers announce off/armed/locked without reading private
text. No action requires a hold, chord or swipe; single-tap alternatives remain
visible. Verify large labels, focus order, contrast, reach and both orientations.
Resize power layouts instead of silently shrinking every key. Automatic tests and
screenshots supplement, and cannot replace, this acceptance evidence.

## Implementation ownership and completion rule

- **Layout owner:** `TypingPanel.kt`, `KeyboardOptions.kt`,
  `KeyboardSettingsActivity.kt` and direct-panel tests. Validate everyday and
  optional power surfaces separately; release only after their P0/P1 gates.
- **Editor/security owner:** `KeyboardIme.kt`, the in-progress `TerminalInput.kt`,
  future editing/modifier helpers, session gates and live-IME tests. Agree operation contracts
  with the layout owner before either changes constructor/callback interfaces.
- **Language owner, after P1:** new data-only layout/composition/dictionary modules,
  provenance manifests and language tests. Do not add dependencies or context
  collection until security review is recorded.
- **Coordinator:** roadmap status, release evidence, signing, compatibility matrix
  and assistive-technology participation. Keep unrelated desktop work independent.

Every capability ends with a recorded status: implemented, verified on named
targets, unsupported with a reason, or still planned. A complete parity claim would
require a dated exhaustive comparison and all applicable gates; this plan claims
none. Reassess any new reference feature against Utterleaf's no-network, no-passive-
capture and no-automatic-history boundaries before adding it.
