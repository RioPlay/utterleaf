# Utterleaf Next: native core comparison

Independent experimental Android module. Application ID `org.utterleaf.keyboard.next`;
version `0.1.0-core01`. This is the first **literal-input slice of N1**, not a
completed N1 milestone or replacement for alpha13/LatinIME. No release is published.

The [system design](../../docs/android-next/README.md) remains the broader product
contract. New Kotlin code owns the Canvas keyboard, static proximity layout,
editor gateway and Incognito preference. No LatinIME/FUTO/Hacker's Keyboard renderer,
decoder, dictionary or artwork is imported. The older apps remain separate.

Implemented scope (verification recorded separately): English letters/symbols,
Shift, Space, direct Backspace and named Enter; optional number row; Latin accent
and punctuation choices by tap or hold/slide/release; two-pointer taps; main-thread editor
ownership; session/caret/privacy rejection; bounded synthetic decoder boundary;
explicit local Incognito and forced sensitive-field policy. There is no live
decoder, touch learning, correction, swipe, voice/model integration, terminal mode,
composition pipeline, clipboard integration or preference history. Calibration
is unavailable/off in every mode; Incognito is a real persisted policy, not proof
that learning exists elsewhere.

Typing preferences have a local draft, Apply, Discard and Reset. The number row
defaults off; accent long-press defaults on and can be disabled while retaining
the explicit Accents button. Applying a row change refreshes live geometry only
after the preference save is acknowledged. Reset preserves manual Incognito and
user assets. The keyboard switcher remains reachable in Settings → Choose keyboard.

Ordinary Backspace uses a bounded 128-UTF-16-unit ICU grapheme query. A full window
is accepted only when a printable ASCII predecessor proves the final cluster's
boundary; ambiguous truncated context is refused. Restricted fields never query context and use direct
code-point deletion. Broad Unicode/editor behavior and physical touch quality remain
open. Virtual accessibility nodes are implemented; this is not TalkBack acceptance.

## Build and check

Use Java 17, SDK 36 and Gradle 8.13. Reuse of the existing reviewed Gradle wrapper
is build tooling only. Its pinned distribution hash is in the wrapper properties.
Configure `local.properties` with `sdk.dir` or provide `ANDROID_HOME`.

```powershell
./mobile/next-keyboard/gradlew.bat -p mobile/next-keyboard --no-daemon `
  :app:testDebugUnitTest :app:connectedDebugAndroidTest :app:lintDebug :app:assembleRelease
```

The release APK is unsigned. No signing credentials or model/native dependencies
are introduced. Emulated acceptance is not physical-device or release acceptance.
See [execution evidence](EXECUTION-EVIDENCE.md) for actual results.

## Capture synthetic emulator screenshots

Only instrumentation can temporarily clear secure windows, using the explicit
`captureScreenshots=true` runner argument on a debuggable APK. The synthetic host
and capture helper are excluded from release; secure flags are restored in
`finally`. Screenshots use only the disposable debug host. Production has no
capture toggle. The instrumentation checks for a visible keyboard frame before
writing PNGs to the debug app's external cache under `synthetic-captures/` and
copying them to `/data/local/tmp/utterleaf-next-core-*.png` before fixture removal.

## Dependencies and provenance

Runtime dependencies: Kotlin standard library 2.1.20, AndroidX Core 1.16.0,
CustomView 1.2.0 and their Maven dependencies; Apache-2.0 license texts and resolved
transitive inventory are required before distribution. Gradle/AGP and test libraries
are separate build/test dependencies. No third-party keyboard code/assets or binary
dictionaries are bundled. This increment is an internal comparison build; a packaged
notice inventory and release validation remain explicit gates.

AndroidX's baseline-profile installer contributes a non-exported startup provider
and a receiver protected by Android's `DUMP` permission. Instrumentation checks an
exact component/permission allowlist; it rejects extra components or weaker access.
This runtime optimization is not a network or user-content collection feature.

Platform references: [InputConnection](https://developer.android.com/reference/android/view/inputmethod/InputConnection)
and [InputMethodService](https://developer.android.com/reference/android/inputmethodservice/InputMethodService).
Direct deletion avoids the focused-view routing ambiguity documented for ordinary
`sendKeyEvent` use. The no-composition slice intentionally overrides default finish
callbacks so owned editor mutations remain confined to the gateway.
