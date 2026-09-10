# Touchscreen keyboard gap review

Reviewed September 10, 2026 against current source and living first-party
documentation. Product documentation describes intended behavior and QA targets;
it does not certify a competitor or establish Utterleaf parity. Current source
status is separate from physical-device and accessibility acceptance.

## What the current source covers

Alpha07 source and the capability plan cover visible optional secondary hints,
common Latin accent/symbol selection by long press with hold/slide/release
cancellation, and the tap route through **Tools → Accents → letter**. The source
also has Spacebar cursor movement, Shift/Caps case handling, and session guards
that invalidate stale panel/editor actions. Generic speech-model import accepts
reviewed tiny.en/base.en/small.en by exact size/hash and preserves the prior model
on failed replacement. Password typing remains available while dictation is
disabled in password fields.

Follow-up source covers direct Tools forward Delete, Shift+Space selection and
held-delete gestures. Revision `ebbd48a` passed 60 API 35 emulator tests, including
the synthetic live editor and local transcript editing. Physical-device and
named terminal validation remain open.

PR15 source (including the PR14 keyboard work) adds independent key height from 48–80 dp
(default available) and bottom spacing from 0–80 dp, a secure ephemeral practice
field capped at 256 characters and cleared on stop, and period-key
hold/slide/release punctuation while retaining a normal period tap. Final revision
`ed491bd` also starts a review take from the keyboard's explicit Voice action and
reuses desktop state icons. It passed 61 API 35 emulator tests, 8 JVM tests,
lint and 3 release-contract tests in [run 34475913178](https://github.com/RioPlay/utterleaf/actions/runs/34475913178).
The tested source is merged and [signed alpha09 is published](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha09).

These are source capabilities, not proof of complete real-editor behavior. The
following gaps remain release-critical or require named-device evidence:

| Priority | Gap / required behavior | Current status |
|---|---|---|
| P0 | Every tap, hold and release commits exactly once to the active editor session; field changes, dismissal, rotation, cancellation and multitouch cannot retarget a late action. | Session guards exist; real-editor acceptance remains open. |
| P0 | Unicode-safe editing: selected-text replacement, combining marks, emoji/ZWJ deletion, cursor boundaries and multiline Enter behavior. | Basic text/delete/arrows exist; comprehensive Unicode and selection matrix is missing. |
| P0 | Privacy boundaries: no passive clipboard history/read, no typed text in logs or diagnostics, no learning in sensitive/unknown contexts, and no stale model or transcript disclosure. | Architectural controls exist; inspect storage/logs and sensitive-field behavior on device. |
| P1 | Spacebar cursor movement must coexist with a normal space tap; Shift+Space selection/extension needs a defined contract or an explicit unsupported state. | Cursor movement exists; Shift+Space source work is in progress and real-editor selection is open. |
| P1 | Held delete needs an explicit policy: repeat rate, word-versus-character mode, cancellation and intentional repeated-character safety. | Held-delete source work is in progress; keep single-delete behavior dependable until tested. |
| P1 | Accent/symbol picker must preserve case, show a readable selection, cancel on slide-off, and retain the tap route when hints are hidden. | Source route exists; adjustable hold timing and TalkBack/Switch Access behavior remain open. |
| P1 | Period punctuation needs the same hold/slide/release contract as letter alternates while a tap still inserts a period. | PR14 source implements the route; CI and real-editor/device validation remain open. |
| P1 | Accessibility must provide equivalent activation without mandatory holds, swipes or chords, with stable focus/order and useful announcements. | Native controls expose labels; physical TalkBack/Switch Access workflows are unvalidated. |
| P1 | Offline suggestions, reversible autocorrection and personal dictionaries must be separate choices; additions are explicit and deletable/exportable, with no implicit collection or password/private learning. | Prediction/correction and vocabulary remain planned; terminal mode must stay literal. |
| P2 | Broader languages require reviewed layouts, dictionaries, composition and speech claims per language; common Latin accents do not equal multilingual support. | English typing/speech foundation only; broader language work remains planned. |
| P2 | Layout tuning needs independent key height and bottom spacing without clipping or moving the secure practice/editor boundary. | PR14 source bounds key height to 48–80 dp and bottom spacing to 0–80 dp; physical size/orientation validation remains open. |

## First-party behavior that sets the test bar

- FUTO’s current typing documentation describes independent keyboard resizing,
  optional number/arrow rows, visible long-press symbol hints, configurable
  long-press duration, single-character or whole-word backspace behavior,
  Spacebar language/cursor gestures, separate autocorrect/suggestion/personalized
  learning controls, and optional automatic spaces. These are documented behavior
  references, not requirements to copy. [FUTO Keyboard & Typing](https://docs.keyboard.futo.tech/settings/keyboardtyping)
  · [FUTO Text Prediction](https://docs.keyboard.futo.tech/settings/textprediction)
  · [FUTO Gestures](https://docs.keyboard.futo.tech/gestures)
- Google’s current Gboard help documents Spacebar cursor movement, double-tap
  Caps Lock, long-press accents, language switching without changing the device
  language, and language-specific availability limits. [Gboard Help: Use your keyboard](https://support.google.com/gboard/answer/2842292?hl=en-GB)
- Microsoft documents SwiftKey Incognito as a visible mode that turns learning
  off, with automatic entry for private browsing or sensitive fields on Android;
  its page states the feature is not supported on SwiftKey for iOS. This supports
  testing both explicit privacy mode and field-triggered behavior without treating
  field metadata as perfect secret detection. [SwiftKey Incognito](https://support.microsoft.com/en-us/swiftkey-keyboard/how-does-incognito-mode-work-on-your-microsoft-swiftkey-keyboard)
- Apple’s VoiceOver guide documents Standard, Touch and Direct Touch typing,
  alternate-character selection by hold/drag/release, cursor movement by
  character/word/line, text selection, cut/copy/paste, deletion and undo. These
  establish an accessibility workflow to test on Android analogues; they do not
  establish iOS implementation feasibility for Utterleaf. [Apple: VoiceOver onscreen keyboard](https://support.apple.com/en-gb/guide/iphone/iph3e2e3d1d/ios)

## Prioritized QA

1. **Editor integrity:** in native EditText, Compose, browser plain/rich fields,
   messaging and a terminal fixture, type repeated letters and punctuation;
   select and replace text; press Enter/Done/Send; switch fields/apps; rotate;
   hide/reopen; and cancel a hold or pending action. Assert one ordered commit,
   no wrong-field edit and defined unsupported behavior.
2. **Editing and Unicode:** test Shift+Space selection/extension (or record the
   documented refusal), cursor movement at start/end, forward/back delete,
   held-delete cancellation, combining accents, emoji/ZWJ, RTL mixing and
   multiline text. Verify selection and composition ranges after every action.
3. **Accent gesture:** on a Pixel 8 Pro and a 320 dp device, test hint on/off,
   long press, slide across choices, release, slide away, multitouch, case,
   period punctuation, and Tools → Accents → letter. Confirm tap selection
   remains available and no accidental base character is committed.
4. **Accessibility:** with TalkBack and Switch Access, complete enable → type →
   correct → accent selection → cancel → submit → switch keyboard. Check focus
   order, spoken names/states, large labels, no gesture-only essential action and
   no private text announced unexpectedly.
5. **Privacy and resource recovery:** inspect logs/storage after ordinary typing,
   password typing, clipboard population, model import and cancellation. Import a
   wrong file, cancel, rotate and interrupt replacement; verify exact-size/hash
   rejection, old-model rollback and continued ordinary typing.
6. **Correction and vocabulary:** with local resources only, test suggestions,
   reject/restore autocorrection, add/delete/export a personal word, and repeat in
   password/private and terminal fields. Verify no implicit collection, learning or
   correction crosses those boundaries.
7. **Practice and geometry:** type at the secure 256-character practice limit,
   stop/leave the settings screen, and verify the field clears. Exercise default
   and boundary key-height/bottom-spacing values in portrait and landscape; check
   insets, focus and the secure overlay.

The release gate stays open until these checks have dated build/device/editor
results. Passing source tests or a settings preview alone does not close it.
