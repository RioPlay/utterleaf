# Original Latin letter layouts

## Goal and area

Add a small, original letter-position foundation to the Android keyboard:
QWERTY (default), QWERTZ and AZERTY. Users can choose it in Settings or Tools,
see the active choice and return to QWERTY. This begins the language/repair
package; it does not establish German/French spelling, prediction, speech or
complete national keyboard conventions.

Implementation owns `LetterLayouts.kt`, `KeyboardOptions.kt`, `TypingPanel.kt`,
`AlternateCharacters.kt`, `KeyboardSettingsActivity.kt`, a new JVM layout test,
a new instrumentation layout test and necessary tuning/persistence tests.
The integrator owns roadmaps, this contract and `KeyboardGeometryTest.kt`.
Do not edit `DeviceTest.kt` or `PrivacyCoreTest.kt` in parallel. Desktop is separate.

## Status

Implemented in source on September 12, 2026 after a separate layout contract
audit. Independent production/test review found no remaining blocker. The
50-test emulator regression run passed; the final expanded three-test geometry
run passed after correcting stale accessibility snapshots in the test harness.
Twelve JVM tests and seven Android tooling tests pass; lint reports zero errors
and 47 warnings. All 18 final layout/Tools views and empty Settings passed
visual review with no clipping, selection or theme mismatch.
No signed release or physical-device acceptance is claimed. The preceding
alignment evidence remains in [android-one-hand.md](android-one-hand.md).

## Behavior and constraints

- Store an explicit local letter-layout preference. Missing or unknown values
  resolve to QWERTY. Add a trailing defaulted option to preserve existing callers.
- Define fixed lowercase rows in original data:

  | Choice | Top | Home | Bottom |
  | --- | --- | --- | --- |
  | QWERTY | `qwertyuiop` | `asdfghjkl` | `zxcvbnm` |
  | QWERTZ | `qwertzuiop` | `asdfghjkl` | `yxcvbnm` |
  | AZERTY | `azertyuiop` | `qsdfghjklm` | `wxcvbn` |

- Preserve the ten-unit grid and the current QWERTY geometry. Center the home
  row with `(10 - letters) / 2` units per edge. Share the bottom row's remaining
  units evenly between Shift and Delete. The six-letter AZERTY bottom row
  consequently has two-unit Shift/Delete controls.
- Digit/symbol hints follow the key position: top `1234567890`, home
  `@#$%&-+()/`, bottom `*"':;!?`, taking the actual row length. Accent choices
  remain attached to their letters. Alternate menus must end with the currently
  visible hint, without retaining a stale QWERTY hint or adding duplicates.
  Preserve existing QWERTY choices, order and case behavior.
- Both hold/slide alternates and the visible alternate-menu fallback use the
  same selected-layout hint. The secondary-hints toggle controls drawing only;
  it must not silently remove useful alternate choices.
- Settings groups three radio choices under **Letter layout**. Use short scope
  copy: changing letter positions does not add spelling or speech support.
  Tools offers selected QWERTY/QWERTZ/AZERTY choices and stays open after a choice.
- Save immediately, synchronize Settings practice and reopening, and retain
  the chosen one-hand alignment. Reset cancellation preserves preferences;
  confirmed Reset restores QWERTY/Full without deleting models or user data.
- Switching layout cancels pending rollover, held alternates, repeated Delete,
  selection gestures and modifiers; invalidate stale callbacks before rebuilding.
  Letter dispatch, Shift/Caps and Ctrl/Alt use the visible letter.
- Preserve number, symbol, editing, terminal/function and voice behavior.
  Add no network, dictionaries, data collection, copied keyboard code, engine,
  Android subtype/language claim or desktop dependency.

## Acceptance

1. Every choice contains exactly the 26 unique Latin letters and the defined rows.
   Stored values round-trip; missing/unknown values default safely. QWERTY remains
   behaviorally and geometrically unchanged.
2. Normal, Shift/Caps and shortcut dispatch follow visible letters. Accents and
   positional hints agree in both alternate routes, including QWERTZ y/z and
   AZERTY a/q/w/z/m. Symbol layers remain unchanged.
3. Settings and Tools reflect the same stored value across reopen. Reset Cancel
   preserves the choice; Reset restores defaults and retains a synthetic model
   marker. Practice text is still cleared by its existing lifecycle rules.
4. All three choices fit Full/Left/Right on narrow and wide test widths. Keys and
   controls have nonempty, nonoverlapping bounds. Inspect live owned-view renders
   for both themes, including the longer Tools controls and Settings group.
5. Switching while a second ordinary touch is pending, an alternate is held,
   Delete repeats or a modifier is armed produces no stale insertion/deletion.
   A new key works after the switch.
6. Independent source review and named test output support the claimed scope.
   Emulator evidence remains distinct from physical reach, landscape, TalkBack,
   Switch Access and complete language support.

## Verification

```powershell
.\.venv\Scripts\python -m unittest discover -s mobile/android/tools -p test_*.py
```

With `JAVA_HOME` set to the installed JDK 17, in `mobile/android`:

```powershell
.\gradlew.bat testDebugUnitTest lintDebug installDebug installDebugAndroidTest
```

Run the named new layout instrumentation class plus affected
`KeyboardTuningTest`, `PersistenceTest`, `OneHandLayoutTest`,
`TypingRolloverTest`, `KeyboardGesturesTest`, `HeldModifiersTest`,
`TerminalInputTest` and `KeyboardGeometryTest` with `adb shell am instrument`.
Use the dedicated API 35 emulator and synthetic debug editor only. Capture owned
keyboard/empty Settings views; retain screenshot protection. Record exact counts
and paths after inspecting runner output and captures.

## September 12 evidence

- `testDebugUnitTest`: 12 tests, zero failures/errors/skips across
  `AlternateCharactersTest`, `LetterLayoutsTest` and `PrivacyCoreTest`.
  The integrator inspected the XML under `app/build/test-results/testDebugUnitTest`.
- `lintDebug installDebug installDebugAndroidTest`: passed. The lint XML contains
  47 warnings and no errors; Python Android tooling passed seven tests.
- The implementer's named emulator run passed 50 tests in 89.211 seconds:
  `LetterLayoutTest` (4), `KeyboardTuningTest` (3), `PersistenceTest` (3),
  `OneHandLayoutTest` (3), `TypingRolloverTest` (6), `KeyboardGesturesTest` (11),
  `HeldModifiersTest` (3), `TerminalInputTest` (14), `KeyboardGeometryTest` (3).
  Its receipt is in the implementer's tool console, not a saved local log.
- The integrator expanded the live geometry method to exercise all nine
  layout/alignment combinations, both themes, selected Tools states, persisted
  choices, every visible key's bounds, ordered rows and native-editor insertion
  from the top/home/bottom rows. Final command:

  ```powershell
  adb -s emulator-5554 shell am instrument -w -r -e class org.utterleaf.voice.KeyboardGeometryTest -e r2Screenshots letter-layouts-verified org.utterleaf.voice.test/androidx.test.runner.AndroidJUnitRunner
  ```

  Result: **3 passed in 43.642 seconds**. Both integrator and reviewer inspected
  `.grok/android-letter-layout-geometry-final.txt`. These three tests replace
  the earlier geometry evidence; they are not three additional distinct tests.
- The first expanded run reported overlapping accessibility bounds during a
  Tools rebuild. Its owned keyboard image showed the rows separated. The test
  now clears the accessibility cache on API 34+ before fresh geometry snapshots;
  the full overlap assertion remains and includes both rectangles on failure.
  The unchanged production layout passes the final run. See Android's
  [`UiAutomation.clearCache`](https://developer.android.com/reference/android/app/UiAutomation#clearCache())
  contract. This fix does not establish TalkBack behavior.
- Final captures: `artifacts/screenshots/android-letter-layouts/letter-layouts-verified/`:
  43 PNGs, 4,067,986 bytes, including nine daily states, nine Tools states,
  empty Settings and the preceding utility-layer checks. They render only owned
  views and retain `FLAG_SECURE`; they omit editors and system UI. The initial
  failure image is retained separately for diagnosis.
- Visual review split between integrator and an independent reviewer covered
  all nine daily layout/alignment states, all nine corresponding Tools states
  and empty Settings. Letters/hints, selected choices, larger AZERTY bottom-row
  utility keys and the unused side strip remain readable and consistently themed.
  No visual blocker was found; this is screenshot evidence only.

Physical reach, landscape, TalkBack/Switch Access, named external editors and
native-speaker language acceptance remain open. Spelling/correction, compose,
emoji and prediction/swipe are separate packages.

## Non-goals and stop

No autocorrection/prediction/swipe, automatic language detection, multilingual
speech, complete localized symbol inventories, general layout importer, layout
editor or release publication. Stop this slice when the above source workflow,
checks and independent review pass, record external acceptance gaps, then advance
the gauntlet. Do not label the overall language package complete.
