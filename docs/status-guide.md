# Know your leaf

[Documentation](README.md) · [User guide](user-guide.md) · [All artwork](branding.md)

<img src="assets/brand/utterling-thinking.png" width="88" alt="Utterling helping explain the app's status" />

The tray leaf is the compact status indicator. Utterling is the friendly character
in Settings and these guides. They have different jobs: follow the tray status
and written messages to tell whether a take is recording or processing.

## Tray icons

| Icon | Meaning | What to do |
| --- | --- | --- |
| <img src="assets/brand/tray-idle.png" width="48" alt="Green leaf" /> | **Ready.** Utterleaf is ready for a take. | Focus your text field, then use your shortcut. The microphone is not kept listening between takes. |
| <img src="assets/brand/tray-recording.png" width="48" alt="Coral leaf with a solid dot" /> | **Recording.** Utterleaf is capturing this take. | Speak. Release the hold shortcut, or press your toggle shortcut again, to finish. |
| <img src="assets/brand/tray-busy.png" width="48" alt="Cyan leaf with three dots" /> | **Processing.** The model is loading or speech is being transcribed. | Read the status message and wait for it to finish. This icon alone does not prove text has reached your editor. |
| <img src="assets/brand/tray-error.png" width="48" alt="Coral leaf with an exclamation mark" /> | **Needs attention.** A microphone, model, transcription, or delivery step failed. | Read the message. Check the microphone, model setup, or use the recovery steps below. |

Recording and processing have shape cues as well as different colors. Tray
tooltips or menu status provide more detail where the desktop supports them.
There is no disconnected/error state just because you are offline: local speech
recognition is the normal workflow after the model is installed.

On GNOME, tray visibility requires an AppIndicator extension. If the leaf is
missing on Linux, start with [Wayland setup](wayland.md) or
[Linux installation](installation.md#linux). A missing tray icon is not proof
that the app has stopped.

## Optional recording guidance

<img src="assets/brand/utterling-listening.png" width="80" alt="Utterling listening" />

**Tray icon only** is the default. Enable **Floating indicator** from the tray
menu if you want a visible countdown. **Preview dictation while recording** adds
draft words to that indicator; it uses extra processing and is not a video or
meeting-caption feature. Start/stop sounds are also optional.

The default take limit is 120 seconds. On Wayland use a desktop toggle shortcut;
global hold-to-talk and Escape cancellation are unavailable in the current backend.

## If your words do not arrive

<img src="assets/brand/utterling-error.png" width="80" alt="Utterling drawing attention to a problem" />

1. Open the tray menu and choose **Copy last dictation (2 min)**.
2. Click the intended text field and paste manually.
3. Use **Forget last dictation** to clear the app's recovery slot sooner.

Only the latest result is retained temporarily in memory. Clipboard copies may
remain in your operating system's clipboard history. Forgetting the app's result
does not erase copies already made elsewhere.

For recurring problems: [microphone help](microphone-troubleshooting.md),
[Wayland help](wayland.md), or **Settings → Help → Check this device**.

## Meet the other Utterlings

Typing marks vocabulary, Speaking accompanies voice commands, and Thinking helps
with setup and troubleshooting. During a microphone check, the character can show
listening, success, or concern; the accompanying text explains the result.

All seven expressions and all icon variants are in **Settings → Help → Icons &
artwork**. The [brand guide](branding.md) covers transparent cutouts, light/dark
variants, and export sizes. Illustrations are bundled locally and never replace
important instructions.
