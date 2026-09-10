# Android keyboard capability plan

[Mobile roadmap](mobile-roadmap.md) · [Layout design](android-keyboard-design.md) · [Security design](mobile-security.md)

[Research and QA criteria](mobile-keyboard-research.md) explain the typing,
accessibility and privacy evidence behind this plan. Proposed thresholds are project
targets, not measured performance or universal human-factors limits.

Reviewed September 9, 2026. The objective is an independently implemented Utterleaf
keyboard with a polished everyday surface and an optional terminal/power layout.
The historical source observations below document design context; they do not
define Utterleaf's identity or establish unverified capability, compatibility,
code reuse or release availability. Security comes first, then privacy.

## Historical source review and Utterleaf decisions

Only official user-facing documentation and public product imagery were inspected;
no third-party keyboard implementation code was reviewed or imported for this plan.
Links identify the reference behavior; acceptance criteria below are Utterleaf's
proposed requirements. Source visibility alone does not establish a reuse license.

| Historical source | Observed behavior | Utterleaf decision |
| --- | --- | --- |
| [FUTO overview](https://keyboard.futo.tech/) and [official product image](https://keyboard.futo.tech/assets/decoration-hero.webp) | Offline speech, swipe, correction, prediction and themes; familiar staggered letters, broad spacebar and compact action/suggestion area | Keep the everyday layout readable and familiar, with Utterleaf's own colors/assets. Add useful actions without filling the letter area with utility keys. |
| [FUTO typing settings](https://docs.keyboard.futo.tech/settings/keyboardtyping) and [actions](https://docs.keyboard.futo.tech/actions/supportedactions) | Resizing, optional number/arrows rows, typing behavior, emoji, editing actions and alternate keyboard modes | Independent sizing, reachable editing, optional number row and visible alternatives to gestures; later one-handed, split and floating modes. |
| [FUTO language management](https://docs.keyboard.futo.tech/settings/languagesmodels) and [prediction](https://docs.keyboard.futo.tech/settings/textprediction) | Separate layouts/resources, multilingual suggestions, correction controls and optional personalization | Separate layout, dictionary, composition and speech support claims. Make correction reversible and learning explicitly opt-in and erasable. |
| [Hacker's Keyboard user guide](https://github.com/klausw/hackerskeyboard/wiki/UsersGuide) and [official compact-layout image](https://raw.githubusercontent.com/klausw/hackerskeyboard/master/hk-5row-en-s.png) | Dedicated number/utility keys, Ctrl/Alt/Meta, arrows and Fn-accessed navigation/function keys | Offer a deliberate power layout, with a full key inventory and clear modifier state. Preserve a comfortable everyday default. |
| [Hacker's Keyboard FAQ](https://github.com/klausw/hackerskeyboard/wiki/FrequentlyAskedQuestions) | Documents small-screen density and application-dependent special-key behavior | Fit power controls through optional rows/layers and orientation settings; verify terminal/editor behavior independently. The guide's older Android examples are historical, not present-day certification. |

The linked images and documents are historical source material, not Utterleaf UI
assets or evidence that an Utterleaf feature works. Their gesture and power-key
examples reinforce a general Utterleaf rule: gesture typing, navigation and
destructive actions need separate settings and visible alternatives.
[Gesture reference](https://docs.keyboard.futo.tech/gestures)

Additional review notes identify useful interaction requirements: editing actions,
an optional suggestion area, an optional number row, staggered letters, secondary
character hints and a symbol page. Treat these as Utterleaf requirements to
implement and verify. An empty or decorative suggestion strip must not imply that
prediction exists.

## Current implementation and evidence boundary

Alpha04 introduced English letters/symbols, Shift/Caps, left/right cursor movement,
deletion and editor actions; local speech with explicit insertion; basic appearance,
feedback and repeat preferences; private model import and signed distribution.
Released alpha05 implements the staggered layout/toolbar, optional number row,
Esc/Tab, one-shot Ctrl/Alt, navigation, and `TerminalInput` dispatch. Its Fn layer
replaces letters with F1–F12, Insert and forward Delete. Guided setup separates
keyboard enabled/selected status from optional voice readiness and offers reviewed
tiny.en/base.en/small.en imports. One active model is replaced only after selected
size/hash verification; failed import preserves the previous file. This remains
English-only speech. Revision [f74b862](https://github.com/RioPlay/utterleaf/commit/f74b862)
passed [CI run 34432378047](https://github.com/RioPlay/utterleaf/actions/runs/34432378047):
4 JVM, 32 API 35 emulator and 3 release-contract tests, with zero emulator failures
or skips. Coverage includes real tiny.en/base.en inference, import bounds/rollback,
terminal event contracts, one-shot modifiers, number-row independence, the replacing
Fn layer and system-bar bounds. Actual setup and synthetic live-keyboard captures
were reviewed. Small.en inference and physical model performance remain unverified.

Released [alpha06](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha06) adds visible
optional secondary hints, common Latin accent/symbol selection by long press or
Tools → Accents → letter, and cancel, case and session guards. [CI](https://github.com/RioPlay/utterleaf/actions/runs/34440735943) passed 8 JVM,
38 emulator and 3 release-contract tests. Signed installation/upgrade checks
passed in [publishing run 34441330864](https://github.com/RioPlay/utterleaf/actions/runs/34441330864).

[Alpha05 is published](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha05).
Its [signing/publishing run](https://github.com/RioPlay/utterleaf/actions/runs/34432995380)
verified the stable certificate, signed alpha03-to-alpha05 emulator upgrade,
same-version reinstall and setup launch. Preference/model retention and physical
Obtainium updates were not established by these checks.

Implemented controls do not establish completed power-mode compatibility or add
suggestions. Current status belongs in the [layout design](android-keyboard-design.md)
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
Alpha05 explicitly permits raw ASCII key events in `TYPE_NULL` fields only when
terminal controls are enabled; speech stays disabled there. Alpha05 settings add
independent number-row and terminal booleans. Utility key labels and an event
dispatcher still need the compatibility and lifecycle gates below.

## Prioritized capability and acceptance matrix

**Implemented** describes source behavior above, with release status stated
separately. **Next** is active implementation
or acceptance work. **Later** requires the listed preceding foundation. None
of these labels asserts every physical/editor/accessibility acceptance gate passed.

| Phase / priority | Capability and status | Acceptance gate |
| --- | --- | --- |
| P0 / security, continuous | **Implemented foundation; next hardening:** editor sessions, capture/import boundaries | Zero late commits across 100 synthetic field/hide/restart/lock transitions. Cancel releases capture and clears speech/composition/modifiers; password and unknown-sensitive contexts never learn, predict, read back or dictate. Denied permission never blocks ordinary typing. No input in logs, telemetry or preference files. |
| P1 / broader acceptance | **Implemented in alpha05:** everyday geometry, symbols, toolbar and optional number row | Staggered letters, wide spacebar, direct comma/period and obvious Voice/Tools. Number-row preference persists and does not collapse key widths. Keep letter/symbol pages' utility positions stable. Verify all layers in both orientations, smallest supported width, largest supported labels and both themes. No clipped essential control or forced scroll during ordinary typing. Preserve typing/voice/switch access when expanded. Validate real IME screenshots separately from settings previews, including status/navigation bars and cutouts. |
| P1 / next refinement | **Released in alpha06:** secondary hints and alternate characters | Visible optional hints; common Latin accents/symbols selectable by long press or Tools → Accents → letter. Verify cancellation, case and session guards, hold timing, slide-off, repeat filtering and assistive exploration; no essential character is gesture-only. Physical, TalkBack and Switch Access validation remains open. |
| P1 / next | **Implemented basic editing; next completion:** selection, Unicode, Enter and touch behavior | Real-IME tests for selected-text replacement, forward/back delete, cursor boundaries, combining marks, emoji/ZWJ and multiline text; all supported Enter actions and no-enter-action flags. Direct-panel and live-IME Shift/Caps tests remain separate. Script 1,000 actions with zero duplicates or reordered characters; verify intended double letters with repeat filtering off/on. |
| P2 / alongside P1; broader acceptance | **Implemented subset in alpha05:** terminal/power controls and dispatch | Esc, Tab, Ctrl, Alt, four arrows, Home/End, PgUp/PgDn and Fn/F1–F12/Insert/forward Delete use `TerminalInput`. Fn replaces letters rather than growing the panel; verify every key remains reachable. Meta and numpad remain planned. Every displayed key needs an explicit contract and named editor evidence. No hidden automatic command submission or global key injection. |
| P2 / broader acceptance, then expansion | **Implemented one-shot Ctrl/Alt; planned:** latch/multi-touch and advanced editing | Provide explicit modifier release. Test Ctrl+C/D/Z/A, Alt combinations, Shift+arrows, tab versus focus navigation, repeats and cancel. Clear all local modifiers on mode/language/field changes and dismissal; never send cleanup keys to a newly bound editor. Distinguish Caps Lock, Shift and Shift Lock if offered. |
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
| Raw terminals | Alpha04 rejects `TYPE_NULL`; alpha05 enables ASCII key dispatch only with the explicit terminal preference. Verify that boundary and refused non-ASCII input independently. Raw mode keeps speech, learning and surrounding-text reads off because field sensitivity cannot be established. A label such as “terminal” does not imply passwords typed there are non-sensitive. |
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
- **Editor/security owner:** `KeyboardIme.kt`, `TerminalInput.kt`,
  future editing/modifier helpers, session gates and live-IME tests. Agree operation contracts
  with the layout owner before either changes constructor/callback interfaces.
- **Language owner, after P1:** new data-only layout/composition/dictionary modules,
  provenance manifests and language tests. Do not add dependencies or context
  collection until security review is recorded.
- **Coordinator:** roadmap status, release evidence, signing, compatibility matrix
  and assistive-technology participation. Keep unrelated desktop work independent.

Every capability ends with a recorded status: implemented, verified on named
targets, unsupported with a reason, or still planned. Reassess any newly considered
capability against Utterleaf's no-network, no-passive-capture and no-automatic-history
boundaries before adding it.
