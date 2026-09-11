# FUTO capability matrix for Utterleaf Next

Reviewed September 11, 2026 against the current official FUTO documentation
and the official [FUTO Android Keyboard source mirror](https://github.com/futo-org/android-keyboard).
The documentation is the source for the FUTO column; it is not a device or APK
test. The local status is an audit of this repository's Android-next UX contract,
core preview strings, and Canvas UI source. `Implemented` means present in the
current local source, not physically accepted. `Planned` means an explicit
Utterleaf target. `Separate gate` means it needs its own quality, provenance,
privacy, or platform evidence. `Excluded` is a deliberate policy difference.

FUTO's website and docs can change independently of a released APK. This matrix
does not infer a current installed release from the website, screenshots, or the
GitHub mirror. No FUTO code, assets, layouts, models, or license terms are
copied into Utterleaf.

## Sources and status vocabulary

Primary FUTO references used here:

* [Settings index](https://docs.keyboard.futo.tech/settings) — settings groups,
  languages/models, keyboard/typing, prediction, voice, dictionary, theme,
  custom layouts, and developer settings.
* [Keyboard & Typing](https://docs.keyboard.futo.tech/settings/keyboardtyping) —
  resizing, number and arrow rows, symbol hints, long-press ordering/timing,
  backspace/space behavior, action bar, autofill, swipe, emoji suggestions,
  correction, capitalization, spacing, popup, vibration, and sound.
* [Gestures](https://docs.keyboard.futo.tech/gestures), [Spacebar cursor](https://docs.keyboard.futo.tech/gestures/spacebar),
  [Backspace highlight/delete](https://docs.keyboard.futo.tech/gestures/backspace),
  and [Enter shortcuts](https://docs.keyboard.futo.tech/gestures/enter) — gesture
  ownership and long-press action access.
* [Supported actions](https://docs.keyboard.futo.tech/actions/supportedactions)
  and [assigning actions](https://docs.keyboard.futo.tech/actions/assigningactions)
  — action inventory, pinned/favorite/more/hidden placement, and action key.
* [Languages & Models](https://docs.keyboard.futo.tech/settings/languagesmodels),
  [Text Prediction](https://docs.keyboard.futo.tech/settings/textprediction),
  [Voice Input](https://docs.keyboard.futo.tech/settings/voiceinput),
  [Theme](https://docs.keyboard.futo.tech/settings/theme), and [Custom Layouts](https://docs.keyboard.futo.tech/settings/customlayouts).
* [Official source mirror](https://github.com/futo-org/android-keyboard) —
  provenance and licensing context only. Its README identifies a custom FUTO
  Source First License; source visibility is not permission to reuse it.

Local references audited:

* [Android-next experience](EXPERIENCE.md) — intended shell, Daily/Edit/Terminal,
  voice, settings, privacy, and parity delivery grouping.
* [Adaptive touch](ADAPTIVE-TOUCH.md) and [architecture](ARCHITECTURE.md) —
  bounded geometry policy, Incognito, editor gates, and planned capability
  boundaries.
* `mobile/next-keyboard/app/src/main/java/org/utterleaf/keyboard/next/ui/` —
  current Canvas keyboard geometry and tap surface. The core preview currently
  exposes English tap typing and Incognito; its own strings state that voice,
  prediction, swipe, touch learning, and terminal tools are unavailable.

## Everyday typing and layout

| Capability | FUTO documentation inventory | Utterleaf Next status and decision |
| --- | --- | --- |
| Staggered alphabetic layout | Familiar layout with configurable sizing and long-press behavior. | **Implemented in N1 source:** immutable QWERTY geometry, Canvas keycaps, shared hit/accessibility bounds. Physical comfort and full IME acceptance remain open. |
| Number row | Keyboard & Typing has an explicit **Number Row** toggle for supported layouts. | **Implemented, emulator checked:** default off, with local draft/Apply/Discard/Reset. The optional row appears on both pages, independent of Terminal, with stable bottom-relative utility positions. |
| Arrow row | Keyboard & Typing has an **Arrow Keys** toggle for a four-arrow row. | **Planned:** Edit provides arrows first; an optional row may increase height explicitly. Terminal/Fn navigation remains separate. |
| Secondary symbol hints | **Symbol Hints** displays additional long-press characters. | **Planned:** hints are independently configurable and must match actual alternates. Current accent work does not yet display secondary hints. |
| Long-press key ordering | **Layout of Long-Press Keys** can reorder or disable symbols/numbers in supported layouts. | **Planned:** reviewed accent/symbol ordering with visible picker; no essential output may be gesture-only. |
| Accent and case variants | Custom long-press examples include accented letters; docs describe missing accents/numbers as a layout configuration issue. | **Implemented, emulator checked:** an original Latin-alternate table, explicit `Accents` tap picker and optional hold/slide/release. Shift controls displayed, spoken and committed case; every popup includes Cancel. |
| Punctuation | FUTO's Custom Layouts documentation allows period long-press alternatives. | **Implemented, emulator checked:** direct comma/period remain stable. Utterleaf's own alternate choices include ellipsis, exclamation/question marks, semicolon and colon; these exact choices are our policy, not an asserted FUTO default. |
| Space and Enter | Space has cursor/gesture behaviors; Enter can expose key actions by long press. | **Implemented tap geometry:** wide Space, direct Enter. **Planned:** optional Space cursor behavior and an action surface; explicit host action remains bottom-right. |
| Key sizing | Interactive keyboard height/width resize is documented. | **Planned:** 48–80dp key-height preference and bounded width profiles. N1 uses density-consistent 56dp rows and 48dp utility targets; physical reach is unverified. |
| Action/suggestion bar | Can be hidden, may force-show for password inline suggestions, and carries actions/suggestions. | **Planned:** stable 48dp bar with up to three candidates; honest `No suggestions` state. No decorative empty prediction strip. |
| Auto-capitalization | Works only where the text field requests it, not generally in URL/search fields. | **Planned:** respect editor metadata; no blanket capitalization in literal/Terminal contexts. |
| Automatic spaces | Independent modes after punctuation and/or suggestions. | **Planned/configurable:** separate spacing preference; Terminal and literal fields remain exact. |
| Double-space period | Optional period-plus-space behavior. | **Planned/configurable:** off in literal-looking contexts; normal Space remains available. |
| Popup on keypress | Optional visual key popup. | **Planned/configurable:** feedback preference; N1 uses pressed Canvas color only. |
| Sound, vibration, intensity | Independent key sound, vibration, and vibration intensity settings. | **Planned/configurable:** local grouped settings, with sensitive-field/system policy. |
| Themes and borders | Theme selection and optional key borders; custom themes are documented as future. | **Partial:** own dark leaf palette in N1. **Planned:** light/high-contrast themes and borders; no FUTO assets. |

## Gestures, actions, and editing

| Capability | FUTO documentation inventory | Utterleaf Next status and decision |
| --- | --- | --- |
| Space cursor movement | Slide Space left/right to move cursor; behavior can be swapped with language long press/swipe. | **Planned:** optional, one owner per gesture, with Edit arrows as a tap alternative. N1 emits taps only. |
| Space language switching | Space long press or swipe can open/switch languages. | **Planned:** visible `Language` chooser first; gesture assignment later after conflict/accessibility tests. |
| Backspace repeat/delete | Long press/swipe Backspace can delete characters or entire words; swipe can highlight then delete. | **Planned/configurable:** repeat and drag deletion remain separate, cancellable, and never required. |
| Symbol slide selection | `?123` can slide to a symbol and auto-return to alphabet. | **Planned:** visible symbol picker and `ABC` return; N1 Symbols page is tap-only. |
| Enter long-press actions | Long-press Enter accesses undo, redo, language, editor, clipboard, and emoji actions. | **Planned:** Tools/Edit replacement surfaces; avoid making essential actions long-press-only. |
| Action inventory | Emojis, voice, language switch, text editor, clipboard manager, explicit paste/cut/copy, theme, modes, select all, undo/redo, arrows, debug, settings. | **Mixed:** N1 has only key actions and virtual accessibility nodes. Edit/Tools/Voice/Terminal are UX contracts; core strings mark voice, terminal, prediction, and swipe unavailable. |
| Action placement | FUTO supports one Action Key left of Space, pinned actions above the layout, favorites in the bar, more actions, and hidden actions. | **Planned:** Utterleaf keeps `Edit`, `Tools`, and `Dictate` stable in its own 48dp bar. Reordering/hiding is later; Settings/Reset must remain reachable. |
| Undo/redo/select all | FUTO action shortcuts send editor commands. | **Planned:** editor-owned operations through `EditorGateway`; no shadow document and no blind fallback. |
| Clipboard manager/history | FUTO documents a Clipboard Manager plus copy/cut/paste actions. | **Excluded:** explicit host clipboard operations may be supported; no clipboard monitoring/history or automatic reads. Raw Terminal Copy cannot be confused with Ctrl+C. |
| One-hand/split/float modes | Keyboard Modes include Standard, One Hand, Split, and Float. | **Planned/separate gate:** one-handed alignment first; split/floating require geometry, insets, and accessibility evidence. |
| Custom layouts | YAML custom layouts are available through FUTO Developer Settings, with custom rows, bottom keys, and long-press keys. | **Separate gate:** bounded versioned data-only imports with preview/rollback; no executable layouts, scripts, native libraries, or copied FUTO layout files. |
| Inline autofill | Keyboard & Typing can disable password-manager autofill; apps may provide smart replies. | **Separate gate:** delegate to Android/password-manager integration; IME never scrapes, stores, or learns credentials. |
| Debug information | Supported actions include debug info for editor, keyboard, screen, and memory state. | **Planned internal diagnostics:** no raw text/audio or private context in logs; user-facing export requires separate review. |

## Emoji, languages, dictionaries, and prediction

| Capability | FUTO documentation inventory | Utterleaf Next status and decision |
| --- | --- | --- |
| Emoji picker | Supported action opens emoji selection; Keyboard & Typing documents Emoji Suggestions. | **Planned:** local search/categories, complete Unicode sequences, skin tones and ZWJ; no network GIF search. |
| Emoji suggestions | Optional while typing. | **Separate gate:** requires bounded local suggestion resources and sensitive-field suppression. |
| Language layouts | Add language, choose layout, and switch via globe or Space behavior. | **Planned:** reviewed QWERTY/QWERTZ/AZERTY and explicit `Tools` → `Language`; layout/resource readiness shown separately. |
| Dictionaries | FUTO docs say many languages need a manually explored/downloaded dictionary; experimental dictionaries can add next-word suggestions. | **Separate gate:** reviewed local data-only dictionaries, provenance, atomic import/rollback, and per-language status. No network in core. |
| Multilingual typing | Multiple enabled languages can share prediction/autocorrect; layout options remain separate. | **Separate gate:** language-specific composition and native-speaker evidence. N1 is English tap typing only. |
| Auto-correction | Can correct on Space/punctuation; threshold and Transformer strength are configurable. | **Planned:** reversible, separate suggestion/correction controls with valid composing range. Never in Terminal, password, unknown-sensitive, or Incognito-forced contexts. |
| Suggestions | Correction suggestions and next-word suggestions are separate documented controls. | **Planned:** up to three candidates in the stable bar; no candidate row implies prediction until an engine is ready. |
| Personal dictionary | Dedicated dictionary menu; docs describe manual words and automatic learning when personalized suggestions are enabled. | **Deliberate difference:** explicit inspectable local vocabulary may be added/removed; no passive lexical learning, contact access, typing history, or clipboard history. |
| Blacklist/offensive filtering | Blacklisted suggestions and offensive-word filtering are documented; offensive filtering is on by default in the docs. | **Planned/configurable:** filtering must never mutate literal committed text silently; defaults require product review. |
| Swipe typing | Toggle enables swiping from key to key. | **Separate gate/planned baseline:** requires reviewed decoder/model licenses, bounded gesture lifetime, quality/latency/RAM/battery measurements, and a correction path. N1 deliberately has no swipe. |
| Touch calibration | FUTO references here do not establish a FUTO heatmap or adaptive touch feature. | **Utterleaf-owned separate feature:** Off/Learn/Frozen with bounded aggregate geometry, explicit Inspect/Clear, neutral Incognito zones, and no lexical/touch history. Do not claim FUTO behavior or use raw heatmaps. |

## Voice and models

| Capability | FUTO documentation inventory | Utterleaf Next status and decision |
| --- | --- | --- |
| Built-in/external voice | Voice settings describe built-in voice and an external provider option. | **Planned:** Utterleaf local voice only; no silent cloud fallback. Existing alpha voice contracts provide explicit capture, cancellation, review, and insertion. Core preview says voice unavailable. |
| Voice model selection | Languages & Models associates voice models with selected language; default English model is English-only. | **Planned/separate gate:** alpha13 catalog is source of truth; show language/size/status and verify imports atomically. No fixed FUTO model claim. |
| Voice length | Default 30-second limit, optional Long-form voice input. | **Planned/configurable:** manual Stop first; optional silence stop is distinct from insertion and never submits. |
| Silence stop | Auto-stop on silence is configurable and noise may require manual Stop. | **Separate gate:** local endpoint behavior and recovery need named-device testing. |
| Audio route/focus | Bluetooth microphone and audio focusing preferences are documented. | **Planned/configurable:** route/focus controls with permission/contention recovery; no capture in sensitive/raw contexts. |
| Symbol suppression | Voice can suppress special symbols by default or allow them. | **Planned:** explicit symbol policy in review; transcript insertion remains literal and never presses Enter. |
| Voice feedback | Start/stop indication sounds and a verbose-progress option are documented; verbose progress is noted as currently ineffective. | **Planned:** implement only functional controls; feedback can be disabled. Omit controls with no effect. |
| Review/edit workflow | FUTO docs establish voice-to-text access, not a verified Utterleaf-equivalent review UX. | **Utterleaf design:** Idle → Capture → Processing → Review → local Edit → explicit Insert; stale results are rejected. Manual Incognito may use explicit local voice in ordinary safe fields; forced sensitive policy blocks it. |

## Modes, privacy, and settings

| Capability | FUTO documentation inventory | Utterleaf Next status and decision |
| --- | --- | --- |
| Standard mode | Standard is one of the documented keyboard modes. | **Implemented as target/N1 tap surface:** Daily letters, symbols, punctuation, Space, Enter. Core preview supports English tap typing. |
| One Hand / Split / Float | Listed in Keyboard Modes. | **Planned/separate gate:** one-handed alignment before split/floating; no physical usability claim from emulator results. |
| Terminal/power layer | FUTO references desktop-style actions through supported actions, but these docs do not establish a raw terminal contract. | **Planned Utterleaf-owned:** explicit Terminal with literal ASCII, Esc/Tab/Ctrl/Alt/Fn/navigation, no smart text, and explicit Enter only for command execution. Core preview says terminal unavailable. |
| Privacy defaults | FUTO presents offline privacy goals but also documents Personalized suggestions, personal dictionary, autofill controls, and external voice choices. | **Utterleaf invariant:** no passive capture, lexical learning, contacts, cloud fallback, clipboard history, or raw diagnostics. Manual Incognito is sticky; forced sensitive policy cannot be disabled. |
| Incognito | No FUTO equivalent is asserted by these references. | **Implemented in core preview:** local preference with fail-closed save states, neutral zones, no learning, explicit reset preservation, and host-app privacy caveat. |
| Settings organization | FUTO groups Languages & Models, Keyboard & Typing, Text Prediction, Voice Input, Personal Dictionary, Theme, Help, Developer Settings, and Custom Layouts. | **Utterleaf grouped contract:** Typing & correction, Layout & touch, Feedback & appearance, Languages & voice, Power & privacy; drafts Apply/Discard and Reset preserves models/dictionaries/user data. |
| Themes/customization | Theme choice and key borders; custom themes are future in the docs. | **Planned:** own restrained dark/light/contrast themes; no copied assets or FUTO branding. |
| Resource readiness | FUTO separates language, layouts, dictionaries, voice models, and transformer resources. | **Planned:** expose each as separate `Ready`/`Not installed`/`Not supported` status; do not equate a layout with speech or prediction readiness. |

## Priority audit for the next slices

1. **Immediate layout parity:** persistent Number Row
   and accent picker are emulator checked; next add visible secondary hints and gateway-backed Edit arrows.
   Keep row persistence, narrow widths and reset/data preservation checks.
2. **Everyday interaction:** tap-accessible accents/case variants, punctuation
   picker, Space cursor and Backspace repeat/drag as independently assigned
   gestures, with cancellation and no overlap with utility keys.
3. **Action/edit surface:** editor-owned arrows, Select/Select all, Undo/Redo,
   explicit Cut/Copy/Paste, emoji search, and action placement. Clipboard history
   remains excluded.
4. **Language/resources:** reviewed layouts and dictionaries with separate status;
   then reversible correction/suggestions and explicit vocabulary. Complex scripts,
   multilingual prediction, and swipe remain separate gates.
5. **Voice:** integrate the local review/edit path and alpha13 model catalog only
   after session, permission, cancellation, and sensitive-field checks. No external
   provider fallback.
6. **Later ergonomics:** one-handed, split/floating, bounded data-only custom
   layouts, inline autofill interoperability, and evaluated swipe/prediction.

The official FUTO pages document a broad, configurable keyboard experience. They
do not provide acceptance evidence for Utterleaf, and this matrix does not claim
that a current FUTO APK, every listed layout, or every editor action behaves the
same on a named device. Utterleaf should match useful outcomes with its own
reviewed implementation while keeping its stricter privacy and provenance rules.
