# Utterleaf Android 0.1.0-alpha20

- Long Backspace drags now wait for the editor's final selection confirmation,
  so releasing at the first character deletes the complete preview even in
  slower host editors.
- Tapping a word completion adds the expected typing space without doubling an
  existing space or inserting one before punctuation.
- Dictation now presents one clear action for each state: Stop & transcribe,
  Insert text, Fix transcript, Done editing, or Retake. Model and optional
  hold-to-insert controls stay collapsed under Voice options.
- Setup is now a readiness dashboard: the two steps required for typing are
  prominent, privacy guarantees stay visible, and optional offline voice details
  expand only when requested.

This preview polishes the daily keyboard, makes editing easier to reach, adds
dark appearance choices, hardens editor/privacy boundaries, and shortens routine
Android CI feedback. It is a bounded development preview, not completion of the
full A–M keyboard redesign.

## What changed

- Editor capabilities and the action key now use one metadata policy. Password
  fields use a minimal literal-input surface: no suggestions, dictation, draft,
  Tools or surrounding-text inspection. Explicit Paste remains a host action;
  the keyboard does not inspect clipboard contents.
- Field changes and panel detach/reuse clear transient Tools, modifiers,
  alternates and pending gestures. Limited/throwing editors fail locally without
  replaying ambiguous editing actions. Lifecycle tests cover owned cross-app
  transitions and actual IME-process recovery, not every third-party editor.
- Model readiness and native loading require checksum verification tied to the
  installed file. Import progress and failures survive Activity recreation while
  preserving the previous verified model. This does not claim process-death
  continuation of an import.
- Models use **Compact English**, **Medium English** and **Large English** names
  with download sizes and relative resource use. Technical identifiers, filenames
  and checksums are available under **Show technical model details**. Existing
  imports keep their identities; names do not promise accuracy or phone speed.
- Settings show **Customized** for values that differ from defaults. Individual
  and category resets remain staged until Apply; Cancel discards them without
  changing unrelated preferences or deleting installed models.
- Email and URL fields suppress prose suggestions. Private-draft navigation and
  deletion respect combining characters and joined emoji, including a caret
  inside a cluster.
- The stable daily strip keeps Undo, Redo, Cut, Copy, Paste, Select, **Tools**,
  **Edit**, **Emoji**, Private Draft, **Voice**, and Extra Keys directly
  reachable. It uses two rows in portrait and one in landscape.
- Select now follows the documented gesture contract: tap selects the neighboring
  word and long-press selects all. Restricted actions remain visibly unavailable
  or absent in password, raw, and private fields.
- Settings, setup, keyboard, emoji, private draft, and voice surfaces share the
  selected palette. Appearance now offers **System**, **Light**, **Dark**, and
  true-black **OLED** modes.
- A normal mic tap preserves the review-and-correct flow before **Insert**.
  **Hold mic to insert after recognition** remains an explicit opt-in shortcut.
- Each dictation take permits only one direct insertion attempt. If the editor
  reports an uncertain result, Insert stays unavailable even after editing; the
  transcript remains selectable for explicit Copy, with a warning to check the
  receiving field. This avoids accidentally duplicating text after a host failure.
- The mic action now uses an Utterling holding a microphone. The Voice surface
  pairs distinct Utterling states with explicit **Listening**, **Processing
  locally**, **Transcript ready**, **Editing transcript**, and **Needs attention**
  labels; controls and text remain authoritative for accessibility.
- Protected drafts omit voice, password-manager routes, host settings, keyboard
  switching, and preference toggles. Opening Extra keys no longer changes its
  saved preference.
- Extra Keys is now a single grouped, horizontally scrollable Accessory/F-key
  strip. Portrait retains the daily toolbar above it; landscape uses the same
  row as a compact specialist header so Space and Enter remain full-sized in
  full and one-hand layouts. Held modifier-arrow chords remain supported.
- The complete additional-symbol inventory is distributed across balanced rows
  instead of squeezing the final set into one line.
- Layout & size now offers **Split keyboard in landscape**. It preserves the
  complete typing and symbol inventory around a non-clickable center channel,
  divides Space into two equivalent thumb targets, and automatically uses the
  standard layout in portrait. Left/Right hand choices turn split off.
- Superseded pull-request runs cancel automatically. Pull requests perform the
  fast compile, unit-test, lint, and debug-build path; the full emulator,
  privacy/inference, release build, and packaging gates still run on the exact
  main/manual release candidate.

No new permissions, dependencies, ambient recording, text history, clipboard
automation, or network access are added. Live partial transcription into the
receiving editor is intentionally deferred: rewriting host text while speech is
still changing needs a separate editor-compatibility and privacy design.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha20.apk**, version code **20**. The package remains
`org.utterleaf.voice` with the persistent alpha03-and-later signing identity.
Update a signed alpha19 or earlier preview in place; do not uninstall first.
Alpha01/02 used different debug signers and require a one-time reinstall that
removes their app data. The experimental foundation package is a separate channel.

The release includes SHA-256 checksums, signing-certificate information, and
version metadata. Use the signed APK, not an unsigned or CI debug build.

## Verification and limits

Android 8+ ARM64/x86_64 development preview. Exact-candidate Android CI and the
protected signing/install/upgrade checks are required before publication. Emulator
coverage exercises appearance persistence, OLED black backgrounds, daily layers,
private-mode isolation, editing, terminal controls, voice review, and settings.

Emulator success does not establish physical-phone comfort. Pixel 8 Pro/GrapheneOS,
broader editor, TalkBack/Switch Access, phone layout/latency, and real Obtainium
acceptance remain explicit follow-up work.

Split, responsive symbols, and Extra Keys landscape geometry are covered on the
visible API 35 emulator. Physical-phone reach and comfort remain unverified.

No automatic correction, next-word prediction, swipe typing, streaming partial
dictation, or language expansion is added. Typing needs no model or microphone
permission. Dictation remains explicit and unavailable in password fields.
Screenshot protection remains enabled.

Changing fields still cancels/clears dictation rather than carrying a transcript
to another target. Recoverable stale-result delivery and the replacement Tools
composition remain planned. Standalone voice landscape/large-font reachability,
extreme narrow/large-text Settings header wrapping, and the final accessibility
audit remain open; passing emulator bounds checks is not full usability evidence.
