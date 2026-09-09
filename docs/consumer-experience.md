# The Utterleaf experience

Utterleaf should make speaking feel like a dependable input method. The product
earns trust by preserving the user's words, responding promptly, delivering text
where expected, and disappearing when finished. More features do not substitute
for that loop working well.

The [September 2026 user research](offline-stt-user-research-2026-09-08.md)
connects these criteria to public user requests and the resulting changes.

## Product decisions

- Keep local processing and no-account use as the ordinary path. A first model
  download must be explained; a failed local engine must never switch to a cloud
  service silently.
- Release the microphone when a take ends. Give an honest listening signal only
  after the device opens. Do not retain an audio history or log dictated content.
- Keep Dictation focused on the shortcut and microphone. Vocabulary is optional;
  model and hardware choices belong in Engine. Avoid adding a chat assistant,
  meeting workspace, engagement feed, recording library, or account dashboard to
  a small input utility.
- Preserve meaning. Cleanup and spoken commands need examples, predictable
  behavior, and tests for negation, names, numbers, punctuation, and corrections.
  Do not turn dictation into unrequested generative rewriting.
- Protect work already in the target app. Automatic edits need a verified
  insertion. A recovery step is preferable to changing an unrelated field or
  consuming the user's undo history.
- Tell the user what happened and what to do next. “Copied; paste manually” and
  “microphone unavailable; choose an input” are useful. A success state must not
  conceal a failed delivery or save.

## Acceptance evidence before calling it a complete package

| Consumer need | Evidence to collect |
| --- | --- |
| It hears my actual words | A consented, local evaluation set covering accents, quiet speech, noise, names, dates, numbers, punctuation, and short commands. Track word errors and meaning-changing errors separately. |
| It feels immediate | Hotkey-to-listening and release-to-delivery p50/p95 for short and long takes. Measure microphone startup, audio cleanup, model inference, and paste separately on named reference devices. |
| It works where I type | Native editors, browsers, email, chat, terminals, multiline fields, selected text, changing focus, and elevated apps. Record actual delivery and recovery behavior, not just successful key dispatch. |
| My existing work is safe | Intervening typing, caret movement, field/window switches, rich clipboard data, clipboard changes during paste, and unsupported edit adapters. |
| It stays private | Idle microphone state, no persisted speech, debug logs free of dictated text, model-only network access, and an offline run after model installation. Check dependency behavior as well as app code. |
| It is comfortable all day | Idle CPU/memory, repeated takes, bounded queues, cancelled decoding, device unplug/replug, sleep/resume, and model changes. |
| I understand it immediately | A new user can discover the shortcut, recognize readiness, dictate into a real field, cancel, choose a microphone, and recover from an error without reading a developer guide. |
| It belongs on my desktop | Keyboard-only operation, screen-reader names/focus, high DPI, compact screens, light/dark appearance, signed packaging, startup, quit, and uninstall on each supported platform. |

The current automated tests and screenshots support parts of this bar. They do
not establish recognition accuracy, real-device latency, broad editor support,
or screen-reader quality. Publish measured results and known limitations before
claiming universal compatibility or superiority to other utilities.

## Language and UI architecture

Keep the Python speech pipeline for now. Native libraries already perform model
inference and device capture. Measure coordination overhead before deciding to
replace it. The tray rendering issue found in this review was removable work on
the hotkey path, not evidence that the entire application needs another language.

Treat the desktop shell and platform adapters as independent boundaries. Tk can
support the current lightweight settings interface, but native accessibility,
text-field integration, appearance, and packaging should determine whether it
remains the right shell. A replacement shell should reuse a tested speech
service boundary; it should not require rewriting transcription or cleanup.

Do not add another runtime merely to gain visual styling. Prototype the hardest
interaction and accessibility requirements first, measure startup and idle cost,
then choose the smallest architecture that meets them.
