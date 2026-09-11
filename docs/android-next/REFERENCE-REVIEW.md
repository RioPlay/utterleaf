# Reference decisions

September 11, 2026. Primary documentation and local source review; no new
side-by-side physical reference-app session was performed. The new UX is original
work informed by documented behavior. No third-party code, dictionaries, models,
icons or screenshots are imported by this design.

| Reference | Evidence | Adopt as a design principle | Deliberate boundary |
| --- | --- | --- | --- |
| FUTO keyboard/typing | [Official settings guide](https://docs.keyboard.futo.tech/settings/keyboardtyping) describes resizing, optional rows, hints, feedback and correction controls | Comfortable defaults with independent local choices and private practice | Resource/engine availability must be explicit; settings cannot override security |
| FUTO space gesture | [Official gesture guide](https://docs.keyboard.futo.tech/gestures/spacebar) describes cursor movement and alternate language-switch mappings | A useful one-handed cursor gesture with a visible tap alternative | One gesture owns a motion; language switching must not compete with cursor selection |
| FUTO actions | [Official actions guide](https://docs.keyboard.futo.tech/actions/supportedactions) describes reachable voice, editing, language and mode actions | Compact actions and a replacing edit surface | Use editor capability contracts rather than assuming Ctrl shortcuts work everywhere; no clipboard manager/history |
| Hacker's Keyboard | [Official repository](https://github.com/klausw/hackerskeyboard) documents separate numbers, arrows and modifier/Tab/Esc utility; its maintainer describes substantial legacy API limitations | Terminal utility and explicit modifier state | Behavior reference, not a legacy implementation dependency |
| Android platform | [IME guide](https://developer.android.com/develop/ui/views/touch-and-input/creating-input-method) defines service lifecycle, editor communication, field types and subtypes | Own current-editor policy, Unicode and lifecycle correctness explicitly | Rewriting the renderer does not remove these framework obligations |
| LatinIME pinned source | [Pinned upstream](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/) and [our execution record](../../mobile/latinime/EXECUTION-EVIDENCE.md) | Pointer/layout/composition techniques; retain regression scenarios | Current experiment lacks native swipe policy and production dictionaries; native storage and full service inheritance are not mandatory new-core dependencies |

Local Aden inspection traced `UtterleafIme`, `MainKeyboardView`, `InputLogic`,
`VoiceSession`, `ModelStore`, `KeyboardIme`, `EditorActions` and `TerminalInput`.
Framework entry points and JNI were validated against source rather than inferred
from missing caller edges.

The most useful existing Utterleaf contracts are:

- [ModelStore](../../mobile/android/app/src/main/java/org/utterleaf/voice/ModelStore.kt):
  known catalog, exact size/hash validation and atomic publication; retain behavior
  while separately verifying worker-process transport and parser safety.
- [VoiceSession](../../mobile/android/app/src/main/java/org/utterleaf/voice/VoiceSession.kt):
  explicit capture, cancellation, 120-second cap and microphone release before
  decoding. Its full-buffer copy is an optimization opportunity, not a reason to
  discard its acceptance scenarios.
- [EditorActions](../../mobile/android/app/src/main/java/org/utterleaf/voice/EditorActions.kt)
  and [TerminalInput](../../mobile/android/app/src/main/java/org/utterleaf/voice/TerminalInput.kt):
  explicit actions, supported host operations, balanced key events and honest
  unsupported behavior. Reuse through the new gateway, never through cached fields.

Before selecting any decoder/asset: record revision, source URL, license and required
notices, input limits, storage/memory format, supported languages, cancellation,
malformed-input behavior and reproducible quality/performance results. License
compatibility is a distinct review; public availability is not redistribution
permission. No AOSP binary dictionary is bundled by this proposal.

The user's remembered FOSS keyboard with a touch heatmap has not been reliably
identified. Do not attribute that feature to FUTO, HeliBoard or another project
without primary evidence. [Adaptive touch](ADAPTIVE-TOUCH.md) is an independent
design requirement: fixed keycaps, bounded local geometric adaptation, explicit
opt-in and Incognito. No competing touch algorithm or asset is imported here.
