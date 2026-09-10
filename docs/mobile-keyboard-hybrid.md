# Everyday typing and power controls

[Research report](mobile-keyboard-research.md) · [Capability plan](android-keyboard-capabilities.md) · [Mobile roadmap](mobile-roadmap.md)

Utterleaf's proposed hybrid combines a comfortable everyday touchscreen keyboard
with deliberate editing and terminal controls. Security comes first, then privacy.
The design defines its own everyday, editing and terminal surfaces. Historical
public documentation was consulted for interaction research; no implementation
code or imported layout/artwork is used. These are requirements to implement and
validate, not a claim that alpha05 already provides them.

## Recommended interaction model

| Surface | Primary purpose | Proposed behavior |
| --- | --- | --- |
| Daily | Messages, forms and ordinary writing | Stable staggered letters, wide Space, direct punctuation, clear Enter action, language switch and Voice. Optional number row and readable secondary hints. Suggestions appear only when a functioning engine is enabled. |
| Edit | Repair and navigate text | Reachable arrows, word/line navigation, selection mode, select all, copy/cut and explicit paste. Undo/redo only through a verified host-editor contract. Return to letters in one action. |
| Terminal | Exact input and commands | Explicitly enabled Esc, Tab, Ctrl/Alt and navigation, with Fn replacing the letter area for function keys/numpad. Visible modifier state and release action. Literal typing; no automatic correction, spacing or command submission. |

The number row should be independent of terminal mode. A person who enters
addresses and quantities should not need to enable programming controls. Edit and
Terminal should keep utility actions stable; switching panels must not lose the
cursor or commit pending work into another field.

Historical keyboard documentation records independent sizing, optional utility
rows, alternate-character hints and timing controls. It also illustrates a coupling:
hiding correction choices can make automatic replacement difficult to repair.
Utterleaf should keep restoration available whenever automatic replacement is active.
[Historical typing-settings source](https://docs.keyboard.futo.tech/settings/keyboardtyping)

Historical power-key documentation records one-shot and held modifiers, explicit
cancellation and an Fn map. It warns that full layouts become too small on phones
and that applications may ignore special keys. These are design constraints; the
2018 revision is not current compatibility certification.
[Historical power-key source](https://github.com/klausw/hackerskeyboard/wiki/UsersGuide)

## Defaults and meaningful choices

| Area | Recommended starting policy | Optional capability |
| --- | --- | --- |
| Correction | Conservative, visible and immediately reversible once its acceptance gates pass | Separate suggestions, automatic replacement, capitalization and spacing controls; explicit literal mode |
| Learning | No implicit personal learning | User-added vocabulary first; later inspectable, erasable local learning with a separate switch |
| Clipboard | Read only for an explicit paste action | History requires a separate retention design; keep it off by default |
| Touch | Comfortable daily geometry and stable key positions | Independent height/labels, left/right alignment, repeat and hold timing, optional hints and number row |
| Accessibility | Selectable alternatives to essential gestures and chords | Screen-reader, switch and motor-accommodation settings validated independently |
| Speech | Ordinary typing works without a model or microphone permission | Local voice with a clear model/language, Stop/Cancel and recovery path |
| Power keys | Compact daily surface | Deliberately enabled terminal layer with explicit modifier states and tested host support |
| Customization | Reviewed built-in layouts and restrained themes | Later bounded, data-only layout imports; no executable keyboard plugins |

Put settings into **Typing & correction**, **Layout & touch**, **Languages & voice**,
**Privacy & data**, and **Advanced input**. Keep common adjustments near the relevant
panel, and put terminal compatibility settings in Advanced input. Provide section
reset buttons with a preview of what resets; appearance reset must not delete a
speech model or vocabulary. These menu groups are a design recommendation to test,
not new implemented navigation.

## Evidence from reported needs

The following original reports were reviewed September 9, 2026. They are
self-selected scenarios, not verified defects in Utterleaf or estimates of how
many people want each feature. Open/closed labels describe the source at review;
a closed request is not evidence of current broken behavior.

| Report and scope | Need to address | Utterleaf acceptance case |
| --- | --- | --- |
| HeliBoard [#2526](https://github.com/HeliBorg/HeliBoard/issues/2526), May 31, 2026, open; English, reported 3.9 | Control over proper-name suggestions | Test unwanted name suggestions separately from spelling correction. Preserve literal entry; evaluate a control before adding another default setting. |
| HeliBoard [#2527](https://github.com/HeliBorg/HeliBoard/issues/2527), May 31, 2026, open | Reporter expects Private Space clipboard contents to remain private | Keep automatic clipboard history absent. Before introducing retention, test Personal/Private Space and work-profile behavior with synthetic secrets; do not assume the OS isolates keyboard-owned history. |
| HeliBoard [#2524](https://github.com/HeliBorg/HeliBoard/issues/2524), May 31, 2026, open | Easier cursor movement than a small spacebar gesture | Provide visible navigation first. Evaluate keyboard-wide cursor gestures as optional because they may conflict with glide typing and accessibility. |
| HeliBoard [#2525](https://github.com/HeliBorg/HeliBoard/issues/2525), May 31, 2026, open | Faster language switching than a hold-and-popup sequence | Test a visible language control and optional immediate cycling. Preserve composing text and screen-reader access. |
| FUTO [#2176](https://github.com/futo-org/android-keyboard/issues/2176), July 22, 2026, open | Bengali phonetic input, including conjuncts | Require an actual transliteration/composition engine and native-speaker testing. A Bengali character layout alone does not satisfy this request. |
| FUTO [#2192](https://github.com/futo-org/android-keyboard/issues/2192), July 28, 2026, open; reported 0.1.29.1, Android 14 | Emoji search should follow a language change immediately | Change language with the picker open; verify local search refreshes without closing it or leaking prior editor context. |
| FUTO [#2182](https://github.com/futo-org/android-keyboard/issues/2182), July 26, 2026, open with Cannot Reproduce/Awaiting Info labels | Reporter describes unexpected clipboard paste while tapping letters | Ordinary typing and suggestions must never trigger paste. Exercise populated clipboard, rapid taps and app switches; treat unexpected insertion as blocking. The source report is not independently confirmed. |
| FUTO [#2175](https://github.com/futo-org/android-keyboard/issues/2175), July 22, 2026, closed | Quick clearing of a search field | Consider an optional Edit action only with clear scope and verified recovery. Keep destructive actions away from primary typing keys. |
| Hacker's Keyboard [#965](https://github.com/klausw/hackerskeyboard/issues/965), August 6, 2025, open | Voice becomes difficult to reach when address-bar punctuation changes | Keep an enabled Voice action reachable independently of comma/slash placement. Test URL fields and symbol layers. |
| Hacker's Keyboard [#988](https://github.com/klausw/hackerskeyboard/issues/988), May 22, 2026, open | Convenient secondary special characters | Provide readable hints, consistent alternates and a visible tap-based picker; test hold timing and cancellation. |

Touch research adds a separate lesson: geometry needs measurement. Park and Han's
2010 one-handed experiment found target size and location both affected accuracy;
its controlled task and older devices do not establish an ideal modern keyboard.
Test left/right placement independently from height.
[Publisher abstract](https://www.sciencedirect.com/science/article/pii/S0169814110000806)

A 2021 Applied Ergonomics study of two-thumb touch errors reports boundary and
directional patterns. That supports inspecting where errors occur, rather than
using only a total error count. Its college-student laboratory sample does not
justify universal hit regions. Use synthetic text trials and opt-in observations;
do not collect everyday keystrokes for layout tuning.
[Publisher abstract](https://www.sciencedirect.com/science/article/pii/S0003687021001885)

If Utterleaf later changes from native buttons to a custom-drawn keyboard, preserve
separate actionable accessibility nodes, state and events for the keys. Rendering
performance must not discard the accessibility model. Actual TalkBack and switch
workflows remain required even with a correct accessibility tree.
[Android custom-view accessibility guidance](https://developer.android.com/guide/topics/ui/accessibility/views/custom-views)

## Security contracts

Security protects the intended destination, integrity and availability of input;
privacy limits what is collected, retained or disclosed. A keyboard can process
everything locally and still be unsafe through stale insertion, malicious imports
or accidentally retained secrets.

| Boundary | Minimum proposed contract | Required evidence |
| --- | --- | --- |
| Text and editor sessions | Bind pending edits and speech to the active connection and selection. Cancel stale work; never retry an edit in a new field. | Field/app/selection changes during every asynchronous operation; zero wrong-field insertion |
| Sensitive input | Honor password variants and no-personalized-learning requests. Keep learning off by default, because ordinary fields can also contain secrets. | Canary strings in password, ordinary, browser and terminal contexts; inspect retention and later suggestions |
| Clipboard | Explicit paste only, bounded content and current-field validation. No automatic history or cross-device sync. | No reads on typing/start/idle; no unexpected paste; profile/space tests before adding history |
| Resources | Reviewed data formats and provenance, bounded parsers, integrity checks and atomic replacement. No arbitrary native-library imports. | Malformed/oversized/wrong-hash imports, interruption and rollback; basic typing survives missing resources |
| External actions | A browser or share target is a separate disclosure boundary. Minimize parameters and show the action; no typed text in help/download URLs. | Inspect outgoing intents and incoming malformed requests; no background launch from typing |
| Learning and diagnostics | Explicit, inspectable vocabulary; no raw text/audio in diagnostics. Review any export before sharing. | Storage/log/crash-payload checks and clear/delete behavior; no cross-editor reappearance |
| Updates | Stable signer/package identity, reviewed permissions and migration behavior | Verify the published APK and prior-version upgrade, including settings/model preservation |
| Terminal input | Explicit mode, balanced modifiers, clear reset, no automatic submit and no speculative printable fallback | Observe actual effects in named terminals/editors; an accepted API call is insufficient |

Android documents `IME_FLAG_NO_PERSONALIZED_LEARNING` as a request to avoid updating
personalized data. It is not a general declaration that every field is safe or a
reason to disable unrelated ordinary input. Use field metadata conservatively and
do not promise perfect secret detection.
[EditorInfo reference](https://developer.android.com/reference/android/view/inputmethod/EditorInfo)

Android's sensitive-clipboard flag suppresses the system preview; it does not
encrypt clipboard content. Clipboard retention needs its own policy even when
typing history is disabled.
[Android copy/paste documentation](https://developer.android.com/develop/ui/views/touch-and-input/copy-paste)

FUTO's June 19, 2024 privacy policy describes no network permission alongside
browser-mediated actions and optional crash-report email that can include typing
or dictionary data. This supports reviewing each data path individually. It is a
publisher disclosure, not an independent security audit.
[FUTO privacy policy](https://keyboard.futo.tech/privacy)

Receiving editors, the OS and authorized accessibility services remain separate
trust boundaries. No Internet permission, secure-window flags and signed updates
each address particular risks; none alone proves that a keyboard is secure.
Use the [security design](mobile-security.md) for current implementation claims.
iOS remains a separate platform feasibility and acceptance track as explained in
the [research report](mobile-keyboard-research.md#android-and-ios-boundaries).

## Implementation sequence and proof

1. **Reliable entry and repair:** selected-text replacement, grapheme-aware deletion,
   editor actions, modifier cancellation and safe field transitions. Test real
   editors and literal strings as well as synthetic text fields.
2. **Accessible daily surface:** alternate characters with a tap route, independent
   sizing and readable hints. Complete type/correct/submit/switch workflows with
   TalkBack and Switch Access, including intended repeated letters.
3. **Editing and terminal acceptance:** verify each displayed action in named host
   applications. Keep refused actions explicit; no blind fallback that duplicates
   text or submits a command.
4. **Language and reversible correction:** reviewed layouts, vocabulary authority,
   mixed-language tests and inspectable resource provenance. Publish layout,
   dictionary, composition and speech support separately.
5. **Evaluated prediction and swipe:** compare completion time, remaining errors,
   repair effort and preference against a familiar keyboard after stated practice.
   Measure latency, RAM and battery on named physical devices.

These priorities refine existing work rather than marking it complete. Alpha05 has
an English typing surface, some editing/power controls and local speech; prediction,
autocorrection, broader languages and swipe remain planned. Current evidence and
open physical/accessibility gates stay in the [capability plan](android-keyboard-capabilities.md).

The success criterion is being able to type, repair and trust the result without
fighting the keyboard. More keys, higher suggestion acceptance or a polished
screenshot alone do not establish that outcome. Use the detailed
[research release checklist](mobile-keyboard-research.md#release-checklist) and
record the tested build, phone, language, access method and host application.
