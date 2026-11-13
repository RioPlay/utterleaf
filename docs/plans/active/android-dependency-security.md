# Android dependency security remediation

## Contract

- Goal: resolve the actual Android app/test/build-tool dependency graphs, repair
  verified advisory matches, and keep a repeatable audit that exposes no inventory
  to an external service.
- Area: `mobile/android`, Android CI and mobile status only. Owning checkout:
  `.grok/worktrees/android-security`, branch `fix/android-dependency-security`,
  baseline `ddf7c78d241c15442d40a47e2b855cbfa69e7671`.
- Constraints: preserve app behavior, permissions, local data, signing, release
  identity and the fast PR/full main CI split. No publication/commit/push.
- Acceptance: all resolvable Maven graphs include app, tests, lifecycle host and
  buildscript dependencies; no applicable advisory matches; applicable tests,
  lint and debug/release native builds pass. Keep runtime/device limits explicit.
- Verification: commands and results below. Stop after focused fixes and checks;
  no unrelated toolchain redesign, device campaign or feature work.
- Authorization: user requested continued remediation of all vulnerabilities.
  Other worktrees and desktop changes belong to their existing owners.

## Findings and changes — November 4, 2026

The resolved baseline contained 250 unique Maven coordinates across 1,359
configuration/component records. Local matching found 55 advisory records,
predominantly AGP/lint/unified-test-platform build tools rather than APK runtime
libraries. Release runtime contains Kotlin stdlib 2.1.20 and annotations 13.0.

| Component | Baseline | Remediation |
| --- | --- | --- |
| Gradle | 8.13 | 8.14.6, official distribution SHA-256 retained |
| whisper.cpp | 1.8.3 / `2eeeba5` | 1.9.5 / `d1be6fde11ac6e0407606b4e42fe72d34add8037`, downloaded source SHA-256 `645445da884df6dbd52b30f82d7be7c01d1767c938714e477e786b88d529e9f4` |
| Netty 4.1 family | 4.1.93 / 4.1.110 | 4.1.137.Final, aligned family; independently versioned tcnative excluded |
| Guava | 32.0.1-jre / 33.3.1-jre | 33.7.2-jre |
| Protobuf Java/Kotlin | 3.24.4 in tool configurations | 3.25.5 |
| Commons Compress | 1.21 | 1.26.0 |
| Commons Lang | 3.14.0 introduced by Compress update | 3.18.0; caught by rescan |
| Bouncy Castle jdk18on family | 1.79 | 1.85, aligned family |
| jose4j | 0.9.5 | 0.9.6 |
| JDOM | 2.0.6 | 2.0.6.1 |

Versions apply before plugin classpath resolution and to every project
configuration, including lint/test tools. The scan exports Gradle's resolved
components directly, rejects unresolved dependencies, and records configuration
coverage. Public OSV Maven advisories are downloaded and matched locally;
affected enumerations and ranges are evaluated as a union. Apache Maven
ComparableVersion 3.9.11 handles qualifiers and release ordering via a tiny
streaming Java helper; its JAR is pinned and hash-verified and its own coordinate
is included in the scan. Unknown range types/events fail instead of passing.

Kotlin plugin [GHSA-r937-wjx7-w2jp](https://github.com/advisories/GHSA-r937-wjx7-w2jp)
remains an explicit **not applicable** record: the [upstream fix](https://github.com/JetBrains/kotlin/commit/bf51df6)
changes KAPT incremental-cache deserialization, and this project applies no KAPT
plugin/configuration. Enabling a KAPT configuration removes that exception and
makes the audit fail. Do not interpret this scoped exception as a patched Kotlin
plugin, or reuse it after changing annotation processing.

Gradle 8.14.6 fixes the October advisories
[SSL repository fallback](https://github.com/gradle/gradle/security/advisories/GHSA-j5m7-59rp-24f5),
[client/daemon deserialization](https://github.com/gradle/gradle/security/advisories/GHSA-xwqc-3h47-hg64)
and [worker/daemon deserialization](https://github.com/gradle/gradle/security/advisories/GHSA-mvvg-497x-hmj8),
plus the January repository-resolution advisories affecting 8.13.
whisper.cpp [CVE-2026-110810](https://github.com/advisories/GHSA-v488-xqq5-cf9f)
is addressed by the [upstream type-bound checks](https://github.com/ggml-org/whisper.cpp/commit/60c0be6ac8fa71b1a2ae2dd938a31a34a508e774)
included in 1.9.5. Both compiled ABI source trees contain these checks. The app's
existing verified-model import remains intact; no arbitrary model loading added.

## Verification and evidence

Environment: Windows; JDK 17.0.20.101 at `C:/Program Files/Eclipse Adoptium/`,
SDK platform 36, NDK 28.0.13004108 and CMake 3.22.1. Set `JAVA_HOME` and
`ANDROID_HOME` for Gradle. Existing Android Studio JBR is Java 25.0.3 and failed
the baseline Gradle invocation; it is not the JDK used for successful checks.

- `python -m unittest discover -s mobile/android/tools -p test_*.py`: **36 passed**.
  Local sandbox temp restrictions required process-local TEMP/TMP to point at
  `mobile/android/build/test-temp`. Default sandbox temp failed; no global setting
  was changed. Tests cover affected/fixed versions, explicit KAPT applicability,
  withdrawn advisories, corrupt/empty input, range-union regression, interval bounds, unknown ranges/events,
  actual Maven qualifier ordering and malformed comparison input
  and replacement of stale success reports when a subsequent audit fails.
- From `mobile/android`: `gradlew.bat --no-daemon -I tools/dependency_inventory.gradle -PincludeLifecycleHost=true securityDependencyInventory testDebugUnitTest lintDebug assembleDebug`:
  **passed**, 102 tasks, 50 JVM tests with no failures/errors; updated native source
  compiled for arm64-v8a and x86_64. An earlier wrapper/native-only check also passed.
- Final command from `mobile/android`:
  `gradlew.bat --no-daemon -I tools/dependency_inventory.gradle -PincludeLifecycleHost=true securityDependencyInventory testDebugUnitTest lintDebug assembleDebug assembleRelease :lifecycleHost:assembleDebug :lifecycleHost:assembleDebugAndroidTest :lifecycleHost:lintDebug`
  **passed**, followed by the offline scan: **236 coordinates (including the comparator), 205 configurations,
  zero applicable advisory matches**, one explicit KAPT not-applicable record.
  Debug and unsigned release APKs were produced; no signing/publication performed.
- `python tools/audit_dependencies.py --download`: **passed** using the exact CI
  entry point. Public database SHA-256:
  `91594435455efd6ca883d7a5b17fb324a87f4d0a308d36ed85915dca9314b13c`.
  Final Gradle run: 178 tasks, 2m26s; existing SDK-XML/deprecation warnings remain.
- `python tools/audit_dependencies.py --database maven-advisories.zip`: initial
  patched scan caught Commons Lang; fixed before final rerun.

Evidence lives locally under `mobile/android/build/reports/security/`, with
baseline inventory/findings and build logs in `mobile/android/build/security-work/`; generated
inventories, public DB snapshot, native archive and command logs are not source.
CI repeats graph export and local matching, retaining the reports for 14 days on
PR/main/manual runs. It does not add an emulator job to PRs.

Automatic approval review rejected a proposed OSV querybatch upload because it
would disclose the private dependency graph to an external service. That action
was not executed or retried indirectly. Downloading OSV's public Maven archive
and comparing locally succeeded, removing the need for that upload/permission.

## Limits and remaining work

This is advisory-based matching, not proof of absence of vulnerabilities. Maven
coverage excludes Gradle's own embedded libraries, JDK, SDK/NDK/build-tools
executables and GitHub Actions runtime images. Native remediation uses upstream
release/source evidence; the Maven scan does not inspect C/C++ code. Physical-device
behavior and hosted CI execution of this exact diff remain unverified. Independent
review completed as recorded below. No signed APK
was published and no existing user installation/data was changed.
Initial `adb devices` found no connected target. The existing `UtterleafLocal35`
API 35 x86_64 AVD was subsequently started headlessly with `-read-only
-no-window -no-audio -no-snapshot -port 5580`; no AVD was created, wiped or saved.
Only this test emulator was stopped afterward. Its userdata was not persisted.

## Independent review correction and focused native acceptance

Independent review demonstrated that the first scanner implementation treated a
nonempty OSV version enumeration as exclusive, skipping the range union. That
was a real detection defect even though an additional current vulnerability was
not established. The implementation now evaluates both enumeration and every
range, uses Apache Maven's comparator instead of handwritten qualifier ordering,
and fails on unsupported types/events even if an enumerated match exists.
Regression cases reproduce the original defect, range boundary/recovery behavior
and qualifier handling. The corrected exact CI entry point was rerun successfully;
the earlier enumeration-only zero-match result is superseded by that result.

Comparator artifact: `org.apache.maven:maven-artifact:3.9.11`, public Maven Central
JAR SHA-256 `0bfd1c121f907642344311d81e4dfd93eba6c24dc712cc0aeae273eb22833022`.
Its helper accepts tab-separated version pairs, rejects malformed input and
continues handling subsequent valid requests. Existing JDK 17 is required.

Focused command, with `ANDROID_SERIAL=emulator-5580`:

```powershell
.\gradlew.bat --no-daemon connectedDebugAndroidTest '-Pandroid.testInstrumentationRunnerArguments.class=org.utterleaf.voice.DeviceTest#verifiedModelTranscribesRealSpeechWithoutNetwork,org.utterleaf.voice.ModelCatalogTest#mutationInvalidatesTheProcessCacheAndCannotReachNativeCode,org.utterleaf.voice.ModelCatalogTest#arbitraryCatalogEntryCannotReachTheImporter'
```

**Passed 3/3, zero failures/errors/skips**, 67 Gradle tasks, 1m09s. This establishes
tiny.en loading and real JFK fixture transcription with whisper.cpp 1.9.5,
cancellation followed by successful new-generation decoding, mutated-model
rejection before native code, and rejection of an unreviewed catalog entry.
The existing tiny.en/JFK test fixtures were copied from the sibling Android
checkout only after checking the same repository-pinned SHA-256 values; no model
was downloaded or imported into an existing user installation. This does not
establish base.en/small.en, ARM64 runtime, physical-phone performance or full UI
acceptance, and it is not a malformed-native-model exploit test.

Receipt: `mobile/android/build/security-work/focused-native-emulator.txt`;
authoritative XML: `mobile/android/app/build/outputs/androidTest-results/connected/debug/`.

The coordinator also authorized pinning Android workflow action references to
live-verified immutable SHAs while preserving the existing action version lines.
All four `android*.yml` workflows now use 40-character commits, verified against
the original public release tags using GitHub's ref/tag API. The local mapping is
`mobile/android/build/security-work/action-pins.json`. This does not complete the
separate Node.js 24/runner maintenance work and is not a hosted workflow run.

Independent reviewer `android_security_review` completed the final bounded review:
confirmed OSV enumeration/range union, Maven qualifier ordering, fail-closed
unknown range types/events, comparator checksum and inclusion of its own
coordinate; independently reproduced **236 coordinates / 205 configurations**
with only the scoped KAPT record, and read the **3/3** emulator XML. No remaining
material finding was reported. Hosted CI execution, ARM64 runtime and
physical-phone behavior remain unverified; local ARM64 compilation and x86_64
emulator inference establish different facts.
