# Next core execution evidence

Local verification, September 11, 2026. Implementation is a literal-input vertical
slice; the wider N1 composition/decoder/device gates remain open.

## Initial literal-input slice

Java 17, Gradle 8.13, SDK 36; API 35 x86-64 `UtterleafFoundation35`, 1080×2400,
420 dpi. Local command:

```powershell
./mobile/next-keyboard/gradlew.bat -p mobile/next-keyboard --no-daemon `
  :app:testDebugUnitTest :app:connectedDebugAndroidTest `
  '-Pandroid.testInstrumentationRunnerArguments.captureScreenshots=true' `
  :app:lintDebug :app:assembleRelease
```

- 13 JVM tests and 24 emulator tests passed: zero failures, errors or skips.
- Lint: zero errors, five warnings and one hint. Four dependency-update warnings
  and a missing application-icon warning remain; the KTX suggestion is a hint.
  No broad lint baseline or missing-translation suppression is used.
- Debug and unsigned, minified release APKs assembled. The latter is 165,653 bytes
  for this narrow literal-input slice, with no speech/linguistic backend or assets;
  this is not a matched feature/size/performance comparison.
- Real framework IME tests inject screen touches for ordinary typing, symbols,
  deletion and two overlapping pointers. They exercise editor switch, restart,
  hide/reopen, password/no-learning policy and persisted manual Incognito.
- Controlled fake-editor/worker tests cover stale session/revision/privacy gates,
  reentrant host calls, bounded decoder inputs/outputs, Unicode deletion and
  delayed/coalesced selection acknowledgements. There is no production decoder.
- Atomic preference tests cover bounded malformed-record rejection, reopen,
  save failure/retry and preservation of synthetic user assets.

Local log: `C:/Users/unknown/AppData/Local/UtterleafBuild/next-core-acceptance.log`.
Reports are generated under `app/build/reports/` and `app/build/outputs/androidTest-results/`.
After the capture helper's file-retention correction, the three real-IME tests
and lint passed again (`next-core-capture.log`). Retained actual emulator captures:
[typing](evidence/typing.png), [manual Incognito](evidence/incognito.png),
[password field](evidence/password.png). These show the synthetic debug host and
the literal-input slice, not a final product design or physical-device acceptance.
The separate `android-next-keyboard.yml` workflow uploads reports only; no new
APK publication is performed by that workflow.

## Review and corrections

Terra implemented/reviewed the gateway and deterministic worker boundary; Luna
implemented the geometry, Canvas surface and virtual accessibility nodes. A
separate Terra adversarial review was reconciled against source. File ownership
was exclusive and the root agent alone operated Gradle/emulator/Git. Navigation
used scoped Aden CLI trees, searches and symbol/backlink inspection plus source.

Corrections include bounded coalescing/output, reentrant editor ownership,
pointer reflow/release cancellation, small-layout rejection, shared hit/draw/node
geometry and accessibility labels. Ordinary deletion now predicts the exact
UTF-16 caret; restricted deletion and named editor actions discard unknown caret
coordinates until the host acknowledges them. Restricted fields never query text.

The emulator harness waits for the framework's matching field binding and IME
animation completion before injecting touches. It checks visible screen/navigation
bounds; merely being laid out does not establish a usable IME. Captures contain
only disposable synthetic text, temporarily clear secure flags in instrumentation,
reject black keyboard frames, and restore flags in `finally`. The local software
graphics renderer produced black frames, including the launcher; a cold start with
host graphics and Vulkan disabled was used for visible screenshot evidence.

## Number row and accents increment

September 11, 2026: the full command above passed with **17 JVM tests and 35
API 35 emulator tests**, zero failures, errors or skips. This acceptance run used
three-button navigation, matching the CI overlay. Lint remains zero errors,
five warnings and one hint. The unsigned minified APK is 179,889 bytes; speech,
linguistic resources and release notices are still absent from this comparison build.
Log: `C:/Users/unknown/AppData/Local/UtterleafBuild/next-number-accents-acceptance.log`.

- Optional number row on both pages, with local draft/Apply/Discard/Reset and live
  IME reflow after save acknowledgement. Preferences survive storage reopen;
  failed writes retain the previous saved choice. Reset preserves Incognito and
  synthetic user assets. Leaving settings discards an unapplied draft.
- Original Latin accent/punctuation alternatives, Shift-aware display and output,
  explicit Accents/base/choice taps and optional hold/slide/release. The popup has
  a visible Cancel action, balanced 48dp cells and virtual accessibility actions.
- Real IME touch tests cover number entry, uppercase tap choice, held accent
  selection, same-editor reset and typing afterward. Isolated UI tests cover
  extra-pointer, travel, resize, explicit cancellation, hidden base nodes and stale
  popup accessibility actions. These are not physical touch or TalkBack acceptance.
- Popup sizing now uses the same actual-layout snapshot as key drawing, touch and
  accessibility. The detached-view tests use exact measure specs; their initial
  raw integer measure call produced a zero measured width and eight failed popup
  assertions. Those fixture failures were corrected, not suppressed.
- Initial remote CI at `3a55b53` failed one real-IME test with `Typed text missing`.
  Source review found the test could observe a token from `onStartInput` before
  `onStartInputView` activated dispatch. The test now waits for the exact shared
  readiness predicate used by key delivery and still checks the host field ID.
  This closes a real readiness gap; it does not establish the historical failure's
  cause. Remote run `34649191986` at `1dd1b32` still failed the initial typing
  assertion and the number-row text assertion (33 of 35 passed). Merge remains
  gated on resolving the remote failures. Local verification with all three
  animation scales set to zero also passed; disabling animations alone does not
  reproduce the remote result.

Terra implemented the initial layout/popup slice and tests; Luna audited the
[official FUTO capability inventory](../../docs/android-next/FUTO-CAPABILITY-MATRIX.md).
Independent Terra review was reconciled against source; root corrected popup
ownership, case, geometry and lifecycle readiness. Agents had exclusive file
ownership. Aden CLI scoped trees, exact searches, definitions and backlinks were
validated against source, including framework callbacks absent from the graph.

Actual emulator captures: [number row](evidence/number-row.png) and
[accent picker](evidence/accents.png). Only disposable synthetic host text was used.

## Process-death spot check

On the same API 35 emulator at `1dd1b32`, a fresh disposable debug installation
was driven through its real Setup UI. Number row on, accent hold off and Incognito
on were applied and both saved acknowledgements observed. `am force-stop` removed
the process (PID 6918); relaunch created PID 7065 and restored all three choices.
Changing Number row to off without Apply, then force-stopping and relaunching
(PID 7156), restored the saved on state. This verifies a draft is not persisted
even when `onStop` cannot discard it. Original default values were restored through
the UI and the temporary debug installation removed. No private files or production
hooks were used. This is a host-driven emulator spot check, not automated CI,
mid-write/crash recovery, IME process-death or physical-device acceptance.

## Bounded long-field deletion and touch diagnostics

Ordinary Backspace now permits a full 128-unit suffix only when ICU's final
grapheme starts after printable ASCII. That context proves a boundary independent
of an omitted prefix; ambiguous RI/combining/ZWJ/Indic context remains refused.
The pre-copy and post-copy size bounds and sensitive-field no-query path remain.
The guard was proposed by a Terra specialist and independently reviewed against
[Unicode grapheme rules](https://www.unicode.org/reports/tr29/). Root restored the
pre-copy guard after review caught its omission in the initial implementation.

The expanded run had 17 passing JVM tests and 38 emulator tests with one
intermittent synthetic-typing failure, now reproduced locally with animations
disabled (`next-long-field-acceptance.log`). The new long-field gateway cases
and real IME grapheme-deletion check passed. All six real-IME/settings tests then
passed in a focused rerun (`next-touch-diagnostics.log`). These results are not
a clean full-suite acceptance. The test harness retains only a bounded synthetic
touch trace for failed assertions; production has no typing/touch logger. CI and
merge remain blocked pending resolution of the intermittent typing failure.

## Open gates

N1 is incomplete: composition, a real linguistic-backend feasibility result,
matched LatinIME sequences/measurements and a named physical-phone sample remain.
The candidate has no live correction/suggestions, swipe, calibration, voice,
Edit/Terminal or height/theme/feedback preferences. Ordinary deletion conservatively refuses
ambiguous full 128-unit context windows; restricted deletion is code-point based
and waits for host selection acknowledgement before another delete.

Broader process-death acceptance, Unicode/editor compatibility, TalkBack/physical
touch acceptance, complete dependency/asset notices, signing, upgrade/Obtainium
and replacement release gates remain open. No physical or publication result is claimed.

Existing LatinIME test counts and published preview01 do not validate this module.
