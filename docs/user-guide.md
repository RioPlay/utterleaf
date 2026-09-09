# Using Utterleaf

[Back to Utterleaf](../README.md) · [Installation](installation.md)

After upgrading to v0.3.7, quit the older running instance and reopen the updated
app. Local recording and Settings commands now use an authenticated protocol;
updated clients will not send control commands to the older protocol.

Microphone busy or missing? Follow the [microphone recovery guide](microphone-troubleshooting.md).

## Dictate and recover text

Utterleaf lives in the system tray as a green leaf. Click it to open Settings.

1. Hold the hotkey, wait for **Listening** or the start sound, talk, then release. Default is **Ctrl+Win** on Windows, **Ctrl+Shift+Space** on macOS and Linux.
2. The tray icon changes as it records and processes your words. The floating indicator is optional.
3. The sentence lands in the app you were already in. Esc cancels a take.

The microphone opens for a take and is released after its short ending buffer;
it is not kept listening while idle. Microphone checks in Settings open it only
for the check. Audio stays in memory for processing and is not saved as a
recording history. Takes stop automatically at 120 seconds by default, with a
notice to start another take. When enabled, the floating indicator shows the remaining time.
Up to four takes can wait behind a slow decode;
Utterleaf asks you to wait before accepting more.

If a result does not reach your text field, open the tray menu and choose
**Copy last dictation (2 min)**. Only the latest output is kept in this recovery
slot, in memory, for two minutes. **Forget last dictation** clears it and the
previous edit context immediately; quitting also clears it. Copying deliberately
puts the text on your system clipboard, where your OS clipboard history may
retain it. You can also bind a desktop shortcut to `utterleaf --copy-last` or
clear it with `utterleaf --forget-last`.

## Settings and recovery

Click the tray icon (or right-click → **Settings…**) to open Settings. First launch opens it automatically. Opening Settings again raises the existing window and preserves unsaved edits, including when using `--settings` directly.

- **Dictation:** choose your shortcut, hold or press mode, microphone, recording feedback, and start at login. A five-second microphone check shows input levels without saving audio.
- **Vocabulary:** add names and custom terms, choose text cleanup options, and preview the result on a sample before saving.
- **Voice commands:** browse the built-in editing and punctuation commands.
- **Speech & privacy:** choose a model, processing device, language, noise reduction, and clipboard behavior. Missing model downloads can be disabled.
- **Help:** check whether the app is running, generate a device report, and save it wherever you choose.

Prefer a clear screen? **Tray icon only** is the default. Switch the overlay on
from the tray's **Floating indicator** toggle, or choose **Tray + floating indicator**
under Dictation → Recording feedback. Live captions only run when the overlay is visible.
Settings uses a dark theme by default. Native system dialogs follow the OS theme.
Controls are grouped by task, with Save and Close visible while you scroll.

**Help → Icons & artwork** explains every icon and mascot, previews them on light
and dark surfaces, and exports a complete asset pack with transparent PNG cutouts.

The window resizes and scrolls, with Save always accessible. **Ctrl+S** (or **Command+S** on macOS) saves without closing; closing with unsaved changes asks before discarding them. Device checks run in the background.
If a field is invalid, Settings opens its page and focuses it. Invalid vocabulary
lines are selected for correction; validation happens before any files are saved.

To recover from unwanted configuration changes, use **Help → Restore default
settings…**. Confirm, review the form, then choose **Save changes**. This resets
advanced preferences as well as the visible controls, turns off start at login,
and restores the default model/hardware. Download and clipboard preferences are
preserved, including an offline-only choice.
Vocabulary entries and downloaded models are preserved. Closing without saving
discards the staged reset. See the [Help screenshot](screenshots.md#help-and-recovery).

On **Wayland**, Utterleaf disables global key listening. Bind a desktop shortcut to the absolute path of the executable followed by `--toggle`, for example `/home/you/Utterleaf/utterleaf --toggle`. Press once to record and again to transcribe. XWayland and a working `DISPLAY` are required for the current Tk/Xorg components. Install `wl-clipboard` and a compatible paste helper (`wtype` on supported compositors, or a configured `ydotool`); support varies by compositor. The shortcut must point to the same executable you launched.

On **macOS**, grant Microphone and Accessibility when asked. Without Accessibility, the hotkey and the paste both do nothing.

## Voice commands

These also appear in Settings so you do not need this table to start.

| You say | What happens |
|---|---|
| `scratch that` | Discard this take (or remove the last dictation in a verified text field if said alone) |
| `new paragraph` / `new line` | Insert a break |
| `make this shorter` | Drop hedges, keep the point |
| `make it more professional` | Expand slang/contractions, tighten |
| `make a list of …` | Turn the take into bullets |

You can say **“make a bulleted list one two three”** in a longer take. Utterleaf also recognizes “bullet list” and the common transcription “bolded list.” Digits such as `1 2 3` become separate items. For longer lists, say **“end list”** before returning to prose, for example: “Make a bulleted list first open the ticket second assign it end list That is all.”

If you only say an editing command, use it within 20 seconds in the same field.
Utterleaf changes an earlier dictation only when it can verify the field, its
contents, and the caret. Currently this supports standard native Windows Edit
controls; browsers, rich editors, macOS, and Linux use manual recovery. Revised
text is copied for you to select and replace the original yourself. Standalone
“scratch that” asks you to delete manually when the field cannot be verified.
Utterleaf does not send a blind Undo command into your document. Temporary field
snapshots expire after 20 seconds and are never written to logs.

## Personal vocabulary

**Vocabulary → Clean up dictated text** is on by default. Turn it off to insert
the speech model's transcript without Utterleaf's vocabulary replacements,
editing commands, grammar cleanup, or extra punctuation between takes. The
preview follows this setting. This preserves model output, not a guarantee of
word-perfect speech recognition; command phrases such as “scratch that” become
literal text in this mode.

In Settings, one line per name:

```
utter leaf = Utterleaf
```

## Advanced configuration

Created on first run. Everyday use is Settings. The toml is for people who want a model or device override.

- Windows: `%APPDATA%\Utterleaf\config.toml`
- macOS: `~/Library/Application Support/Utterleaf/config.toml`
- Linux: `~/.config/utterleaf/config.toml`

```toml
hotkey = "ctrl+win"     # macOS/Linux default is "ctrl+shift+space"
mode = "hold"           # hold | toggle
model = "small"         # tiny, base, small, distil-small.en
device = "auto"         # auto | gpu | cpu
language = "en"
microphone = ""         # empty = system default
```

Polish is local rules. There is no cloud path.

Start at login: Windows Startup folder, macOS LaunchAgent, Linux `~/.config/autostart`.
