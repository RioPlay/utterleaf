# Using Utterleaf

[Back to Utterleaf](../README.md) · [Installation](installation.md)

After upgrading to v0.3.7, quit the older running instance and reopen the updated
app. Local recording and Settings commands now use an authenticated protocol;
updated clients will not send control commands to the older protocol.

Microphone busy or missing? Follow the [microphone recovery guide](microphone-troubleshooting.md).

## Dictate and recover text

<img src="assets/brand/utterling-listening.png" width="80" alt="Utterling listening to your first take" />

Utterleaf lives in the system tray as a green leaf. Click it to open Settings.
See [Know your leaf](status-guide.md) for each icon's meaning and what to do next.

1. Hold the hotkey, wait for **Listening** or the start sound, talk, then release. Default is **Ctrl+Win** on Windows, **Ctrl+Shift+Space** on macOS and Linux.
2. The tray icon changes as it records and processes your words. The floating indicator is optional.
3. The sentence lands in the app you were already in. Esc cancels a take.

The microphone opens for a take and is released after its short ending buffer;
it is not kept listening while idle. Microphone checks in Settings open it only
for the check. **0.4.6 RC2 preview:** takes have no duration
countdown. Release the hold shortcut or press the toggle shortcut again to finish;
Esc cancels where supported. The optional speech-end setting can also stop a take.
Audio uses a temporary local file and a short preview tail in memory, then is
recognized in small batches after you finish. The temporary file is removed after processing,
cancellation or quit; it is not recording history or an exported recording.
Storage is not encrypted by Utterleaf, and file removal is not secure erasure.
Temporary storage must be on an OS-reported local filesystem. Network shares,
mapped remote drives and unverified mounts are refused. On Linux this conservative
check also excludes FUSE and overlay filesystems; use a native local temporary
directory. Operating-system backups or other authorized software remain outside
Utterleaf's control.
Available disk space still limits recording; storage failures are reported and
any recovered prefix is never automatically pasted as a complete take.
Up to four takes can wait behind a slow decode;
Utterleaf asks you to wait before accepting more.

If a result does not reach your text field, open the tray menu and choose
**Copy last dictation (2 min)**. Only the latest output is kept in this recovery
slot, in memory, for two minutes. **Forget last dictation** clears it and the
previous edit context immediately; quitting also clears it. Copying deliberately
puts the text on your system clipboard, where your OS clipboard history may
retain it. You can also bind a desktop shortcut to `utterleaf --copy-last` or
clear it with `utterleaf --forget-last`.

If Esc or quit reaches delivery before a paste shortcut is sent, Utterleaf cancels
the delivery and keeps the result available for recovery. If a platform helper or
native edit may already have started, the tray reports that delivery could not be
confirmed. Check the original field before choosing **Copy last dictation (2 min)**
or pasting again, because the text may already be present. Utterleaf preserves a
newer clipboard copy made by you; when a shortcut may have been sent, it keeps the
dictated clipboard payload so a late paste cannot consume unrelated restored text.

## Settings and recovery

Click the tray icon (or right-click → **Settings…**) to open Settings. First launch opens it automatically. Opening Settings again raises the existing window and preserves unsaved edits, including when using `--settings` directly.

- **Dictation:** choose your shortcut, hold or press mode, microphone, recording feedback, and start at login. A five-second microphone check shows input levels without saving audio. The current source layout also groups Output style here; the published Windows RC2 keeps it under Vocabulary.
- **Vocabulary:** add names and custom terms, choose text cleanup options, and preview the result on a sample before saving.
- **Voice commands:** browse the built-in editing and punctuation commands.
- **Speech & privacy:** choose an explicit multilingual or English-only model pack,
  any of the 100 languages supported by the bundled Whisper engine (or Automatic
  detection), processing device, noise reduction, and clipboard behavior. One
  multilingual pack is shared across its supported languages; switching languages
  does not require a separate copy of the same model size. Fresh profiles keep
  missing-model downloads off; use **Download selected model…** for an explicit
  installation.
- **Help:** check whether the app is running, generate a device report, and save it wherever you choose.

In current unreleased source, device-report and GPU-guidance checks run one at
a time. Device reports use saved settings, not unsaved choices. A failed check
retains the previous report and offers retry guidance; **Details…** shows optional
technical information. Review device names and local paths before sharing a
report. **Save report…** saves the report selected when the picker opened, even
if a pending check finishes meanwhile. Cancelling does not write a file. A failed
save keeps the preview for retry, but the chosen file may be incomplete.

Prefer a clear screen? **Tray icon only** is the default. Switch the overlay on
from the tray's **Floating indicator** toggle, or choose **Tray + floating indicator**
under Dictation → Recording feedback. The dictation preview only runs when the overlay is visible.
Settings uses a dark theme by default. Native system dialogs follow the OS theme.
Controls are grouped by task, with Save and Close visible while you scroll.

**Help → Icons & artwork** explains every icon and mascot, previews them on light
and dark surfaces, and exports a complete asset pack with transparent PNG cutouts.
In current unreleased source, its five tabs are Tray, Badges, Marks, Utterling
and Wordmark. Page Up/Down and Home/End scroll the selected reference; native
notebook navigation remains available. Export and Close stay visible at larger
text sizes. Export failures show retry guidance in the window; **Details…**
opens optional technical information that may contain a local path. Cancelling
the destination picker does not export anything. Closing the guide does not
cancel an export you have already requested.

The window resizes and scrolls, with Save always accessible. **Ctrl+S** (or **Command+S** on macOS) saves without closing; closing with unsaved changes asks before discarding them. Device checks run in the background.
In current unreleased source, Dictation shows the app's applied settings at the
last check separately from the selected speech model's local-file status.
**Refresh status** checks for Ready, Idle, Listening, Processing, or Needs
attention. **Ready · applied speech model loaded** means the app successfully
loaded a model for its applied model, requested processing device, compute type
and language settings; the existing CPU fallback can still apply. It does not
test microphone availability or promise the next take will succeed. Idle remains
possible when matching model-load proof is
unavailable. **Loaded model for applied settings** names the matching model in
that same check; custom names and paths are shown only as **Custom model**.
**Not confirmed** means matching load proof is unavailable. This does not name
the model held by an already-running dictation. Changing or saving preferences
does not update this last-check result: use Refresh status to check again.
Older app versions may provide status without a loaded model name, or only
report that they are running. The app status check does not open the microphone,
inspect hardware, load a model, or send your words or device information.
**Manage model…** opens Speech & privacy. Its selected model can be an unsaved
choice, independent of the app's applied settings. Installed files alone do not
prove that this selected model has loaded successfully.
Speech & privacy uses the same human-readable model name and describes its
language support. The model picker distinguishes multilingual and English-only
packs. The language picker shows human names and codes, and blocks an English-only
pack from being saved or downloaded for another language. Existing configurations
that used a bare size such as `small` keep their prior behavior; choosing a guided
pack in Settings records the scope explicitly. **Model details…** shows the
selected draft's last file check,
including its identifier, processing backend, expected local folder, and missing
files. Custom model identifiers remain editable. Details can include local paths;
review them before sharing. **Download error details…** is a separate action that
appears after a failed download.

**Local model files → Refresh local list** checks guided installations on request.
It does not load a model or use the network. The list distinguishes installed,
incomplete and unreadable/changing files. **Setup file size** measures recognized
setup files only: it excludes extra files and the shared download cache, and is
not a download estimate or reclaimable disk space. Custom locations are not listed.
Refresh again after a download or an external file change.

**Use this model** stages the model field; choose **Save changes** to apply it.
Language and processing-device choices never change automatically. If they do
not match the chosen installation, the list explains which existing control to
change first. Automatic processing can still use a separate NPU installation.
This inventory is a last-checked file snapshot, not the running app's active model.

Current source separates a successful microphone check from speech-model
readiness. Refresh and Test run one at a time; **Stop** remains available during
a check. Changing the input clears the previous check result, and a missing
named microphone is never silently replaced. Device-list and model-download
failures explain how to retry. **Details…** appears only after a failure and
opens technical text locally; it may include device names or paths, so review
it before sharing. Retrying clears the old details. Each model-download retry
still asks for one-time permission and does not change the network preference.
If the download worker cannot start, no download begins and the controls recover
for a fresh attempt. Closing Settings cancels a pending download; partial files
are kept for retry. A download that already finished remains successful even if
Cancel was clicked just before its completion appeared.

Before each explicit take, current source re-resolves the system-default or
saved input route. If the OS default moved to another enumerated endpoint, the
cached stream is closed and reopened between takes, even when the display name
is unchanged. A missing or ambiguous duplicate-name saved input fails closed;
choose an unambiguous input rather than falling back silently. This is a
within-process route check, not background hotplug monitoring or durable device
identity across rename, unplug, reboot or sleep.

If a microphone refresh, microphone test or app-status check cannot start,
Settings restores the controls and offers a retry. This does not mean the
microphone is unavailable: that check has not run. Your selected input and
unsaved settings stay unchanged. Failed startup checks do not prevent Settings
from opening, and no retry runs automatically.

If the audio driver reports an unsupported format, current source explains that
the microphone cannot use the requested audio format. Choose another input in
Dictation, select Test, and Save changes to apply it. No different microphone is
selected automatically. Technical driver text stays behind Details; unknown
errors retain general microphone-access guidance instead of guessing a cause.

Current source keeps text within a readable width on large windows. Use
**Alt+1–5** (**Command+1–5** on macOS) to open pages in sidebar order, or **F1** for
Help and the shortcut reference. These shortcuts apply only within Settings and
keep pending edits. Compact layouts scroll while Save and Close stay visible.
Choose **Find setting…** or press **Ctrl+F** (**Command+F** on macOS) to search
setting names and help terms. Search never indexes your vocabulary, device names,
model paths or other entered values. Use the arrow keys and **Enter** to open a
result; **Escape** or **Back** returns to your previous focus without discarding
drafts. If a setting needs another option enabled first, search explains that
requirement and focuses its enabling control without changing it. The search
query is cleared when you leave search and is not saved.
Model form rows and download actions stack when larger text needs more room.
The optional sidebar tagline disappears in a short window when it cannot fit;
all five navigation destinations and privacy settings remain available.
With focus on a sidebar item or button, use **Page Up/Down** to scroll and
**Home/End** to reach the page top/bottom. Text fields keep their usual editing
keys. This also lets you read the full Voice commands reference without a mouse.
If a field is invalid, Settings opens its page and focuses it. Invalid vocabulary
lines are selected for correction; validation happens before any files are saved.
Oversized editors keep the insertion or selected validation line in view as you
move the cursor. The read-only device report is reachable with Tab; typing there
does not alter the report.

If Save fails, the alert explains which steps are confirmed saved, which failed
and which were not attempted. If progress cannot be confirmed, it says so.
Your form entries stay available for correction and retry. **Save details…**
shows optional technical information locally; it may include private file paths.
If the settings were saved but the running app could not be notified, quit and
reopen Utterleaf to use them. Any edits made after starting that save remain
unsaved. Settings, vocabulary and start-at-login changes are separate steps,
not one all-or-nothing operation.

Backup review also keeps its preview read-only. Use **Tab** or **Shift+Tab** to
leave the preview; choices and action buttons wrap when larger text needs room.
You still choose what to include or import, review the result, and explicitly
confirm before applying it. Resizing or cancelling does not save anything.

Under Dictation → Recording feedback, **Reset Recording feedback…** stages the
defaults for only the floating indicator, live preview and start/stop sounds.
It leaves every other form edit unchanged. Review the result, then choose
**Save changes** to save all pending edits; closing without saving discards it.
This section reset is intentionally narrower than the app-wide reset below.

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

<img src="assets/brand/utterling-speaking.png" width="80" alt="Utterling introducing spoken commands" />

These also appear in Settings so you do not need this table to start.

| You say | What happens |
|---|---|
| `scratch that` | Discard this take (or remove the last dictation in a verified text field if said alone) |
| `scratch that, [new information]` | Replace the last verified entry with your correction; pauses such as “scratch, that” are accepted |
| `new paragraph` / `new line` | Insert a break |
| `make this shorter` | Drop hedges, keep the point |
| `make it more professional` | Expand slang/contractions, tighten |
| `make a list of …` | Turn the take into bullets |

You can say **“make a bulleted list one two three”** in a longer take. Utterleaf also recognizes “bullet list” and the common transcription “bolded list.” Digits such as `1 2 3` become separate items. For longer lists, say **“end list”** before returning to prose, for example: “Make a bulleted list first open the ticket second assign it end list That is all.”

For an explicit list with clear item boundaries, try:

> Make a bulleted list. Bullet point cats. Next bullet point dogs. Next bullet point cars. Next bullet point elephants. End list. Now I am talking in a paragraph again.

A list request applies to that take; it does not switch later recordings into a
persistent list mode. Keep multiword items together using “next bullet point”
or actual line breaks. Ordinary text is not made into a list just because it
contains several nouns.

Within a take, clearly separated commands also work: “Cats. New line. Dogs.
New paragraph. Back to prose.” Say “end list” before returning from list items
to a paragraph. Quoted command names and phrases such as “a new line of business”
remain ordinary text; ambiguous words are not treated as commands.

Use editing commands within two minutes, in the same unchanged field.
Utterleaf changes an earlier dictation only when it can verify the field, its
contents, and the caret. Currently this supports standard native Windows Edit
controls; browsers, rich editors, macOS, and Linux use manual recovery. Revised
formatting edits may be copied for manual replacement. A spoken replacement remains
available through **Copy last dictation**: select the original entry, copy the
correction from the tray, then paste. Standalone
“scratch that” asks you to delete manually when the field cannot be verified.
Utterleaf does not send a blind Undo command into your document. Temporary field
snapshots expire after two minutes and are never written to logs. **Forget last
dictation** clears this context sooner.

Completed prose takes include a separating space so a later take cannot become
`sentence.Next` merely because you paused or a window title changed. Existing
newlines are preserved. Literal/code mode does not add this separator.

### 0.4.6 RC2 preview: caret spacing and Markdown

The September 12 source changes improve spacing next to existing text in supported
native Windows Edit fields. Completed prose retains its separator at the end of
the field, including after a long pause. Cleanup suppresses a final full stop before
an existing `.`, `,`, `;` or `:`; it preserves question/exclamation marks, quotes and
parentheses. It changes the inserted payload, not the surrounding document. Browser
editors, rich fields, macOS and Linux still use the existing conservative delivery
path; arbitrary caret-aware joining is not established there.

Explicit lists now end with a structural line break. In the current source layout,
choose **Settings → Dictation → Output style → Markdown** for Markdown block
spacing and explicit headings. In the published Windows RC2, the same choice is
under **Settings → Vocabulary → Output style**. **Prose** remains the default.
Examples:

| Say | Markdown output |
| --- | --- |
| `heading two Project notes` | `## Project notes` |
| `heading level one Release plan` | `# Release plan` |
| `make this a heading 3: Open questions` | `### Open questions` |
| `make a bulleted list apples and pears` | Two lines: `- Apples` and `- Pears` |

Heading levels one through six work as words or digits. Headings and Markdown lists
are separated from following prose with a blank line. Existing **new paragraph**,
**new line**, list-item and **end list** commands retain their explicit scope.
A heading title is treated as content, including a question mark or exclamation;
it does not run further commands embedded in the title.

Use **Preview clean text** before saving to try the output. The choice stays local,
can be included in a selective backup, and Reset to defaults restores Prose without
deleting vocabulary or models. Closing without saving preserves the old preference.
Turning **Clean up dictated text** off or using literal/code input bypasses Markdown
formatting. Markdown does not summarize your speech, answer questions or send it to
another model. Markdown formatting is included in the Windows RC2 preview;
the compact Dictation layout is a later source change.

### 0.4.6 RC2 preview: bounded delivery cancellation

Esc and quit now signal the current final-delivery job even while another delivery
step holds the capture lock. On macOS and Linux, owned paste-helper processes have
bounded waits and cleanup. Utterleaf does not try another paste method after a
launched helper fails, times out or is cancelled, because the first helper may
already have inserted some or all of the text. Partial Windows shortcut dispatch
is handled the same way and releases possibly held paste keys.

When delivery may have happened, the tray reports an uncertain result. Check the
original field before using recovery to avoid inserting the same dictation twice.
Windows clipboard reads and writes now use a separate process with a one-second
operation limit plus cleanup. Utterleaf reads the previous text only when needed
for restoration, and restores it only if the clipboard still belongs to that
delivery. A failed or cancelled copy can leave dictation on the clipboard even
though no paste shortcut was sent. Cancel does not start another restoration
operation or clear your OS clipboard history. Copy and Copy last dictation use
the same write limit; an unconfirmed copy leaves recovery available in memory.

The macOS/Linux clipboard backends and native field replacement remain
synchronous. Cancellation cannot interrupt or undo a native edit after it starts.
Native metadata/input calls also retain their platform limits. Isolated Windows
clipboard/editor acceptance remains open. Frozen diagnostics and offline file
transcription passed for the Windows RC1 preview; live delivery still needs native
editor validation.

### 0.4.6 RC2 preview: stop after speech

In **Settings → Dictation → Stop after speech**, enable **Stop after speech and a
pause** and choose a pause from 0.5 to 3 seconds (default 1.2). Start every take
yourself with the existing hold or toggle shortcut. Detection runs locally during
that take; it does not listen while idle or restart recording after stopping.
Silence before detected speech does not end the take. Manual stop and Esc remain
available; continuous recording no longer imposes a duration countdown.

**Insert immediately after automatic stop** is a separate option, off by default.
With it off, a temporary window shows the result with **Copy**, **Insert** and
**Discard**. The preview clears after two minutes; Copy keeps text on your
clipboard. Closing the window leaves the current recovery slot available until
it expires or is replaced; Discard clears that reviewed result.

Insertion requires a supported native Windows Edit field whose text and caret
remain unchanged. If that cannot be verified, use Copy and paste into your chosen
field. Browser/rich editors and macOS/Linux use this manual fallback. Moving to
another window while recording disables automatic stopping for that take; stop
manually. Changing the field during processing prevents automatic insertion and
opens review when the take is still current.

The result uses the take's cleanup and Prose/Markdown preferences. Automatic stops
never execute spoken editor commands such as “scratch that”; those words remain
literal. Ordinary manual-stop command behavior is unchanged.

Only the [reviewed local detector](desktop-vad-resource.md) is admitted. If it is
loading, missing, unsupported or fails, the recording status tells you to stop
manually. No detector is downloaded automatically. Quiet speech, noise, another
speaker or a thinking pause can affect when detection stops; choose a longer pause
if needed. Physical microphone/noise/latency acceptance remains pending for this
Windows RC1 preview.

## Model setup and windows

In the unreleased desktop source, file transcription, file-format setup and
dictation review keep their action buttons visible in compact windows and at
larger text sizes. Long content scrolls. Use Tab/Shift+Tab to enter and leave
read-only transcript previews; their arrow and text-navigation keys still work.
With focus on an action button, Page Up/Down and Home/End scroll the content.
These layout changes do not change file export, decoder consent or insertion
verification, and are not part of the published RC2 binary.

Current source also explains file transcription, export and file-format setup
failures with a next action. **Details…** opens bounded technical information
only when requested; it can contain private paths, so review it before sharing.
Changing the operation's status clears old details. An export failure keeps
the transcript preview available for retry; check the destination before
retrying because a failed export does not prove that nothing was written.
Choosing FFmpeg still requires explicit trust confirmation, and forgetting it
removes only Utterleaf's selection, not the installed program.

To check model installation, open **Settings → Speech & privacy → Model &
installation**. The status distinguishes missing or incomplete files from an
installed selection. **Download selected model** authorizes a single download;
your ongoing network preference stays unchanged. Cancel stops that download.
Installed means required files are present, not that every device can load them.

Clicking the tray's default Settings action brings the existing window forward
and preserves unsaved edits. Windows may restrict keyboard focus, so activation
also raises the requested window without leaving it permanently always-on-top.

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
model = "small.en"      # or small.multilingual; other guided sizes work likewise
device = "auto"         # auto | gpu | cpu
language = "en"         # or auto / another supported language code
microphone = ""         # empty = system default
```

Polish is local rules. There is no cloud path.

Start at login: Windows Startup folder, macOS LaunchAgent, Linux `~/.config/autostart`.
