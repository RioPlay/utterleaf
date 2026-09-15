# Android action organization

## Goal

Use FUTO as the useful-capability baseline, and JuiceSSH-style accessory keys as
the usability reference for modifiers and terminal input. Keep everyday shortcuts
in one toolbar, an All Actions replacement layer, and a purposeful text editor.
Preserve Utterleaf's original keyboard layers and long-press hint behavior.
The previous long, mixed Tools strip is not the accepted usability target.

## Area and constraints

Android `TypingPanel.kt`, affected instrumentation tests and mobile documentation.
No desktop, speech, preference-schema, permission or dependency changes. Existing
restricted-field/private-draft guards, cancellation and stale-generation checks
remain authoritative. No FUTO source or assets are copied.

Reference: [FUTO action assignment](https://docs.keyboard.futo.tech/actions/assigningactions),
reviewed September 13, 2026. FUTO separates toolbar favorites from All Actions.
This increment uses fixed useful defaults; action customization remains future work.
The user clarified that FUTO is not a menu template: additional keys must support
actual typing tasks with the convenience of JuiceSSH's accessory keyboard.
FUTO-level everyday capability still requires real offline swipe recognition,
visible alternative candidates and correction/restore. Moving buttons cannot
satisfy that baseline; retain those as explicit incomplete product requirements.

## Interaction and acceptance

- Keep Edit, Emoji and Dictate directly available in the daily toolbar. Tools
  opens All Actions in the letter area, with an always-visible ABC exit.
- All Actions uses four rows of related destinations: text/emoji/draft,
  alternate characters/composition/case, layout/settings/keyboard switching,
  then optional number-row/terminal controls. No scrolling hunt for actions.
- Text actions live in Edit: Undo/Redo/Select all/forward delete together;
  Cut/Copy/Paste alongside a spatial directional pad. Tap Select selects the
  neighboring word through the existing `terminalKey` Ctrl+Shift+Left path;
  hold Select invokes the native Select all editor action.
- In terminal mode, all four arrows stay above the letters alongside Tools and
  Dictate; the existing accessory row retains Esc, Tab, Ctrl, Alt, Nav and Fn.
  Ctrl/Alt stay selected until tapped off, and also work as held chords. Shift
  stays selected for arrows and terminal keys so Ctrl+Shift+Left can keep
  extending a word selection; letter/digit Shift remains one-shot. Field and
  layer changes still cancel local modifiers. Nav uses spatial arrows
  alongside Home/End and Page up/down. Ordinary typing does not gain another row.
- Every displayed menu action fits at 320/360/412dp and in one-hand mode, both
  themes and large labels, with at least 48dp utility targets. No layer exceeds
  the ordinary typing height. A layer change cannot emit pending input.
- Preserve letter hold, comma hold, selection, editor refusal, private drafts,
  raw restrictions, settings persistence and terminal modifiers.

## Verification

`python -m unittest discover -s mobile/android/tools -p test_*.py`

In `mobile/android`, with JDK 17 and Android SDK:
`gradlew.bat testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest`
and affected `connectedDebugAndroidTest` instrumentation classes. Inspect owned
view captures of All Actions and Edit. Emulator results are not phone usability proof.

## Non-goals and stop

No replacement of the consumer APK, automatic history, prediction placeholder or
swipe placeholder. Version/release metadata for unpublished alpha16 lives in the
[snapshot plan](android-alpha16-snapshot.md). Swipe recognition and candidate
repair remain required open work under R4; this menu change does not deliver them.
Stop implementation when the scoped UI, behavior checks and source review pass.
Stop snapshot work after publication and verification.

## Status

Implemented on `feat/android-action-organization`. Version metadata is prepared
as unpublished **0.1.0-alpha16**. Production changes are confined to the Android
IME/editor path: `TypingPanel.kt` plus the existing `terminalKey` /
`TerminalInput` / private-draft navigation routing so Select actually selects in
the host editor and local draft. Source/diff review checked modifier routing,
restricted/private action availability, stale-generation guards and unchanged
preference/resource boundaries. No tag, PR or signed APK yet.

September 13 local evidence on `emulator-5554`, UtterleafFoundation35, API 35:

- 14 Android tooling tests and 31 JVM tests pass. Lint has zero errors and 54
  existing warnings. Debug app and instrumentation APKs build successfully.
- The broad regression rerun completed 149 tests: 148 passed and one retained an
  obsolete expectation that enabling Terminal leaves the Tools menu open. The
  corrected check waits for visible Ctrl/arrows/Delete before exercising the same
  backspace-selection refusal. Earlier missing model fixtures were supplied from
  CI's reviewed sources and both model SHA-256 hashes verified before use.
- Final source verification runs 24 instrumented tests with zero failures,
  errors or skips: `CompactLayerTest`, `HeldModifiersTest`,
  `BackspaceSelectionTest`, `LetterLayoutTest`, and `KeyboardGeometryTest`.
  This includes the corrected toggle check, native held/tap-to-arm Ctrl+Left,
  plain-arrow restoration, geometry, cancellation and selected-state clearing.
- All Actions/Edit targets are checked at 320/360/412dp, both themes, large labels
  and every alignment. Owned-view captures cover normal typing, All Actions,
  settings, Edit, terminal letters and Fn/Nav; dark/full and light/large/one-hand
  views were inspected without disabling production screenshot protection.

Final command in `mobile/android` (JDK 17 and `ANDROID_HOME` configured):

```powershell
.\gradlew.bat testDebugUnitTest lintDebug connectedDebugAndroidTest `
  '-Pandroid.testInstrumentationRunnerArguments.class=org.utterleaf.voice.CompactLayerTest,org.utterleaf.voice.HeldModifiersTest,org.utterleaf.voice.BackspaceSelectionTest,org.utterleaf.voice.LetterLayoutTest,org.utterleaf.voice.KeyboardGeometryTest' `
  '-Pandroid.testInstrumentationRunnerArguments.r2Screenshots=action412' `
  '-Pandroid.testInstrumentationRunnerArguments.r2WidthDp=412' `
  '-Pandroid.testInstrumentationRunnerArguments.r2Light=true' `
  '-Pandroid.testInstrumentationRunnerArguments.r2Large=true' `
  '-Pandroid.testInstrumentationRunnerArguments.r2Alignment=left' --no-daemon
```

Logs, test XML and owned-view captures are retained locally under
`.grok/keyboard-usability/` in the original workspace. Final debug app SHA-256:
`e269ac967e1a7ad6efede2515967f7e673b890d2e32775f29ade4a84ecdb7fc9`.
The source remains uncommitted for review; no consumer APK was replaced or release
published. Physical-phone, TalkBack/Switch Access and broader host compatibility
remain open. Real swipe decoding/candidate repair and the rest of the FUTO
capability baseline are not completed by this increment.
