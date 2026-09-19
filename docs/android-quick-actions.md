# Android quick editing actions

Released in [signed Android alpha12](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha12).

Tap **Edit** in the toolbar for Undo, Redo, Select all, Cut, Copy, Paste, four-way
cursor movement, selection mode, Home and End. The action panel replaces letters
instead of stacking extra rows above them. **ABC** returns to typing.

**Prepared for unpublished alpha16:** Undo, Redo, Select all and forward Delete form
the top Edit row; Cut/Copy/Paste sit beside a directional cursor pad. Tap Select
to select the neighboring word through the editor's Ctrl+Shift+Left equivalent;
hold Select for Select all. The existing Select all action remains on the same
layer. Tools opens a bounded All Actions layer for accents, composition,
layout, settings and keyboard switching. In Terminal mode, arrows remain beside
the letters and Esc/Tab/Ctrl/Alt; Edit and Emoji are available through Tools.
Enabling Terminal from All Actions immediately reveals the accessory keys.
Ctrl and Alt stay selected until tapped off; Shift stays selected for arrows so
Ctrl+Shift+Left can keep selecting words. Field and layer changes still clear
them. See the [action/accessory contract](plans/completed/android-action-organization.md).

Commands go to the current editor through Android's context-menu API. Utterleaf
does not read or retain clipboard contents, listen for clipboard changes, or
maintain a host-editor undo history. Copy/Cut explicitly put selected text on the system
clipboard through the editor. Private drafts omit Cut/Copy/Paste and keep their
own Undo/Redo history in memory. Password Copy/Cut are blocked. Paste remains an
explicit editor action, including in password fields where the editor permits it.

Undo and Redo use the receiving editor's history. Some apps do not implement
these commands or cannot undo a particular change. Rejected commands show **Key
unavailable**. Raw terminal fields receive no context-menu or fallback Ctrl
shortcut; terminal shortcuts remain available through Terminal controls. This
avoids interpreting Copy as Ctrl+C and interrupting a running terminal command.

Actions are guarded by the current editor/panel generation. Leaving the panel or
switching fields prevents old controls from acting on a new editor. The Settings
practice keyboard and local transcript editor use the same action dispatch.

## Design reference and validation

The [official quick-action inventory](https://docs.keyboard.futo.tech/actions/supportedactions)
was reviewed as user-facing behavior, without importing implementation or assets.
Existing Utterleaf actions were retained; the missing editing commands were
implemented independently using
[Android's editor API](https://developer.android.com/reference/android/view/inputmethod/InputConnection#performContextMenuAction(int)).
Clipboard history, multilingual switching, emoji, floating/split layouts and
toolbar personalization are separate capability work, not implemented by adding
these action buttons.

Regression coverage exercises native EditText undo/redo, selection and clipboard
commands; password and raw-terminal guards; invalid connections; stale buttons;
and panel height. Physical-device, external-editor and accessibility acceptance
remain open. Revision `aec275b` passed [Android CI](https://github.com/RioPlay/utterleaf/actions/runs/34498263015):
74 emulator tests with zero failures/skips, JVM tests, lint and release contracts.
[Desktop CI](https://github.com/RioPlay/utterleaf/actions/runs/34498263059) passed.
The first candidate failed an existing live-hold test with a fixed scheduling wait;
the test now awaits the actual overlay within a bounded deadline. The complete
suite passed afterward, including insertion after hold-slide-release.

[Signed publication](https://github.com/RioPlay/utterleaf/actions/runs/34499446037)
verified certificate continuity, package/version identity and emulator
upgrade/reinstallation. Downloaded APK SHA-256:
`c327c5b6d11544f53d2f7da5e503bd18e781939e047091628aad0e3ff2a524d2`.
The practice-panel capture was inspected; the OS clipboard preview overlaps it,
so it is not used as a promotional screenshot. This is not physical-phone QA.
