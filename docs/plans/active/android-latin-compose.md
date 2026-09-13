# Explicit Latin Compose

## Goal and area

Add a small, original, tap-accessible Latin Compose flow to the Android keyboard.
The user chooses a named mark and then a Latin letter; a supported pair inserts one
NFC result. This advances the R3 composition milestone without adding a dictionary,
suggestions, prediction, learning, language claims or third-party keyboard code.

Implementation owns a new pure `LatinCompose.kt` data module, `TypingPanel.kt`, a
new JVM test, `ComposePanelTest.kt` and `ComposeImeTest.kt`. This plan records the
bounded contract. `KeyboardIme.kt`, existing tests, `DeviceTest.kt`,
`PrivacyCoreTest.kt` and the root roadmaps remain integrator-owned.

## Status

Implemented in source on September 12, 2026. The focused JVM test passes 3/3;
the new direct-panel and actual-IME bundle passes 8/8. A separate direct capture
method produced eighteen owned views covering expanded Tools, both Compose stages,
themes and every alignment. Its nonvacuous bounds check includes enabled and disabled
visible controls and asserts that each render contains buttons. The Tools fixture
matches an ordinary safe IME field, including the four-control Number row, Terminal,
Private draft and Compose row. The views passed
visual review without clipped labels or controls. Lint reports zero
errors and 54 warnings. Existing accent, layout and private-typing panel regressions
passed 13/13. The appended live geometry method encountered the emulator's known
long-session accessibility-node settling timeout, then passed once in isolation in
68.575 seconds. No signed release, browser/editor parity, physical comfort or
assistive-technology acceptance is claimed.

Independent review resolved two source findings: detached controls now remain
invalid while reattaching the same panel rebuilds working ordinary keys, and the
pure table rejects Unicode case mappings outside its declared ASCII bases and
their ordinary uppercase forms. Current-code verification after both fixes:
**31 project JVM tests**, **8 focused panel/IME tests in 16.327 seconds**, and lint
with **0 errors, 54 warnings**. The final corrected geometry/capture method passed
**1 test in 1.952 seconds**, with all 18 views refreshed. The integrator inspected
the large one-hand Tools row including Draft and Compose, alongside both Compose
stages; the implementation owner inspected the full matrix.

The named source slice has passed review and its focused checks. Earlier
accumulated-session IME/window-node failures are not considered fixed by an
isolated pass or cold reboot. Those reliability, physical-device, language-engine
and release gates remain open in the mobile roadmap. The
[user guide](../../android-latin-compose.md) documents the exact supported pairs.

## Behavior and constraints

- Tools exposes **Compose** without requiring a hold. Compose first shows a compact
  chooser of named Latin marks, then the familiar letter rows with a visible pending
  status and Cancel action.
- The reviewed original table covers acute, grave, diaeresis, circumflex, tilde,
  ring, cedilla, macron, caron and dot-above over only their explicitly listed Latin
  bases. Java's platform NFC normalizer creates the final value; a result is accepted
  only when it is one Unicode code point.
- A supported pair is sent through the existing panel commit callback exactly once.
  Shift and Caps choose the uppercase result. A rejected host commit retains the
  pending mark for an explicit retry; it never falls back to keys, clipboard or an
  editor action.
- An unsupported pair changes no host text, stays in Compose and reports
  **Combination unavailable**. Cancel changes no host text. No partial combining
  mark is inserted.
- Terminal/raw mode exposes Compose as unavailable and stays literal. Private-draft
  editing may use Compose because it uses the existing local callback and has no host
  text, clipboard, persistence or escape path.
- Reset, letter-layout/alignment changes, emoji/panel changes, detach, disposal and
  new IME field/subtype/hide/finish/destroy sessions clear pending state. Old view
  references cannot insert into a later session.
- Compose reads no editor or surrounding text, clipboard, microphone, logs or
  preferences and retains no completed or rejected text. It does not claim German,
  French or complex-script composition support.

## Acceptance

1. Pure tests prove every declared mark/base pair produces one NFC code point with
   correct uppercase, unsupported pairs return no value and the table has no
   duplicate mark identities or base letters.
2. Direct-panel tests prove the no-hold route, visible named chooser/status/Cancel,
   zero pre-completion commits, one final commit, Shift/Caps behavior, atomic refusal,
   rejected-commit retry, private-draft support and terminal disabling.
3. Reset, layout/alignment changes, detach and disposal invalidate pending and stale
   callbacks. Subsequent ordinary typing still works.
4. Actual-IME tests prove host text is unchanged until completion, reversed UTF-16
   selection is replaced once, field/subtype/hide/finish lifecycle drops pending
   Compose, raw mode cannot enter it, and the synthetic clipboard remains unchanged.
5. Owned Compose views fit both themes, large labels and Full/Left/Right alignment on
   the dedicated API 35 emulator. Automated evidence does not establish physical
   comfort, TalkBack, Switch Access or broad editor compatibility.

## Verification

With JDK 17 and the Android SDK configured, from `mobile/android`:

```powershell
.\gradlew.bat testDebugUnitTest installDebug installDebugAndroidTest
adb shell am instrument -w -e class org.utterleaf.voice.ComposePanelTest,org.utterleaf.voice.ComposeImeTest org.utterleaf.voice.test/androidx.test.runner.AndroidJUnitRunner
```

Run `lintDebug` and only the smallest affected existing panel/IME regression after
review. Install APKs explicitly; do not use `connectedDebugAndroidTest`, start a
microphone, access a consumer editor or alter the desktop clipboard.

## Non-goals and stop

No word composing range, autocorrection, suggestion strip, dictionary, snippets,
personal vocabulary, learning, complex scripts, swipe, new preference, model or
resource import. Stop once the named local Compose task and lifecycle failures pass
focused review and tests; record broader R3 work separately.
