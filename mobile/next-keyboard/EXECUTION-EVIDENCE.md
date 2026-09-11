# Next core execution evidence

Local verification, September 11, 2026. Implementation is a literal-input vertical
slice; the wider N1 composition/decoder/device gates remain open.

## Implemented and checked locally

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

## Open gates

N1 is incomplete: composition, a real linguistic-backend feasibility result,
matched LatinIME sequences/measurements and a named physical-phone sample remain.
The candidate has no live correction/suggestions, swipe, calibration, voice,
Edit/Terminal or comfort preferences. Ordinary deletion conservatively refuses
a full 128-character context window; restricted deletion is code-point based
and waits for host selection acknowledgement before another delete.

Process-death acceptance, broader Unicode/editor compatibility, TalkBack/physical
touch acceptance, complete dependency/asset notices, signing, upgrade/Obtainium
and replacement release gates remain open. No physical or publication result is claimed.

Existing LatinIME test counts and published preview01 do not validate this module.
