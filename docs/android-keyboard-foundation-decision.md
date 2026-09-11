# Android keyboard foundation decision: AOSP LatinIME

Status, September 11, 2026: the pinned experimental LatinIME port has bounded build,
typing, privacy and persistence evidence, and a separate
[signed preview01](https://github.com/RioPlay/utterleaf/releases/tag/android-foundation-v0.1.0-preview01).
It is not the shipping keyboard replacement. The user has since requested a
[new Kotlin-owned core design](android-next/README.md); that design supersedes the
sole-LatinIME-renderer decision for the new candidate, while this document remains
the experiment's provenance and historical evaluation. Preserve both current apps.
See the [foundation record](../mobile/latinime/README.md) and
[execution evidence](../mobile/latinime/EXECUTION-EVIDENCE.md) for tested scope and
remaining gates. The following initial adoption analysis is historical.

## Source reviewed

The review used the AOSP repository's `main` branch at commit `127336e9f29d69607eab55982324b210279ae8c5`, resolved with `git ls-remote` on September 10, 2026. The repository is [platform/packages/inputmethods/LatinIME](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/). `main` is a moving branch; pin this SHA or a named Android release tag for any future evaluation.

LatinIME is a complete AOSP product module, not a small public-SDK keyboard library. Its current [Java Android.bp](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/java/Android.bp) declares a `LatinIME` `android_app`, Soong static libraries (`android-common`, `latinime-common`, JSR-305 and AndroidX), an AOSP JNI library, product-specific packaging, `sdk_version: "current"`, and an APK target of min SDK 21 / target SDK 30. The checked-in [legacy Gradle build](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/build.gradle) uses an old Android Gradle Plugin/toolchain and platform-style source sets. A standalone Gradle build against only public Maven/Android SDK artifacts is therefore not an established path.

The implementation includes Java IME, keyboard rendering, event/composition logic, dictionary/suggestion services and native C++ dictionary/proximity code. The [native JNI build](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/native/jni/Android.bp) is substantial. Reusing it means taking on a C++/JNI ABI, resource, shrinker, generated/build-system and lifecycle integration surface, not just copying a layout.

## Trust and privacy boundaries

LatinIME's [manifest](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/java/AndroidManifest.xml) requests or declares substantially more capability than Utterleaf's current core: network-state and download permissions, contacts/profile and account/sync access, read/write user-dictionary access, boot completion, external storage, credentials and vibration. It also includes dictionary download/update receivers and dictionary services. These declarations describe source behavior and packaging, not proof that every path runs on every build, but they are enough to reject a drop-in adoption under the current no-network/no-contacts/no-background-update contract.

The source and localized settings explicitly expose contact-name suggestions and personalized suggestions learned from communications and typed data. The English resources say that personal dictionaries can sync to Google servers when cloud sync is enabled. This is a materially different privacy product from Utterleaf's current no-implicit-learning, no-contact-access, no-clipboard-history and no-raw-input-diagnostics foundation. Disabling a preference is not by itself an audit of every dictionary, service, receiver or JNI path.

LatinIME can still be a useful code reference for local composition, dictionaries, gesture decoding, editor actions, accessibility patterns and lifecycle handling. Any Utterleaf integration must preserve these contracts:

* no `INTERNET`, contacts, account, credential, sync, external-storage or boot/update permission in the core APK unless a separately approved feature requires it;
* no dictionary/network update receiver or background downloader in the core IME;
* no contact-derived suggestions, cloud sync, typed-data learning, clipboard history or raw text/audio diagnostics;
* password, no-personalized-learning and unknown-sensitive contexts use Utterleaf's conservative context/learning rules, independently verified against real editors;
* imported dictionaries/models remain data-only, bounded, provenance-checked and atomically replaceable; no arbitrary executable add-ons;
* the existing IME session-generation gate, terminal dispatch rules, secure window and local STT cancellation remain authoritative.

These are Utterleaf requirements, not guarantees made by AOSP LatinIME. AOSP's visible source and Apache license do not constitute a security audit of its current APK, dictionaries, dependencies or downstream device builds.

## Licensing and asset provenance

The Java build declares Apache-2.0 and includes a [Java NOTICE](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/java/NOTICE). The repository-wide [NOTICE](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/NOTICE) separately says the distribution includes dictionaries © Lexiteria LLC used by permission. Therefore “LatinIME is Apache-2.0” is too broad for redistribution of the entire tree or its dictionary assets. Each Java, native, resource, dictionary, AndroidX and build dependency must have a recorded source revision, license text, NOTICE obligations and redistribution decision. Utterleaf must retain prominent modification notices for modified files and the relevant NOTICE text if it ships derived work.

## Comparison with the current foundation

| Concern | Current Utterleaf custom foundation | AOSP LatinIME reuse implication |
| --- | --- | --- |
| Build | Ordinary Android app module with pinned native speech dependency | Requires Soong/platform modules or a nontrivial extraction; old Gradle path is not proof of standalone buildability |
| Default data path | No Internet permission, no contacts/accounts/sync, no persistent typed text or clipboard history | Manifest and code include optional download, contact, user-dictionary, account/sync and boot/update paths that must be removed or isolated |
| Input surface | Native buttons, explicit edit/terminal layers, session-generation guards, Shift-space selection and local STT. `KeyboardSurface` deliberately accepts only Shift-first + Space selection; arbitrary multitouch is cancelled and the current surface is not mature overlapping two-thumb/sliding input. | LatinIME offers mature composition/dictionary machinery and pointer/gesture infrastructure worth evaluating, but would require adapting its view/event lifecycle to these contracts and measuring whether it improves the current bounded gesture behavior |
| Learning | Off by default; future local learning must be inspectable and erasable | Existing personalization and contact features are opt-in product paths, but need code-level removal and tests before claiming compatibility |
| Assets | Reviewed speech model catalog with hashes; no arbitrary native model/add-on import | AOSP dictionaries and JNI are separate provenance/licensing/supply-chain review items |
| Evidence | Current live IME and focused gesture/delete/session tests, with physical/accessibility gates open | AOSP tests show upstream intent, not compatibility or privacy evidence for an extracted Utterleaf APK |

## Migration plan

1. **Reconnaissance fork:** pin the SHA, preserve the full source/NOTICE inventory outside the product tree, and produce a dependency/license/permission manifest. Record the intended platform build as upstream context; first attempt a standalone public-SDK build in an isolated module rather than making a full Android platform checkout a prerequisite.
2. **Small extraction spike:** determine whether the Java composition/dictionary pieces can compile in Utterleaf's app without platform-private libraries. Keep AOSP JNI and dictionaries in an isolated module; do not connect them to the live IME yet.
3. **Permission/privacy reduction:** remove dictionary download/update receivers, contacts/accounts/sync, user-dictionary writes, boot behavior and cloud paths. Prove the resulting APK manifest and runtime traces match Utterleaf's offline contract.
4. **Adapter boundary:** retain Utterleaf's `KeyboardIme` session generation, sensitive-field policy, `InputConnection` contracts, persistent visible terminal Ctrl/Alt/Shift plus Esc/Tab/Fn controls, the guarantees against stray commits from cancelled gestures and local STT. Treat LatinIME as a candidate composition/suggestion engine behind an interface with bounded context and cancellation. Separately evaluate its pointer tracking/sliding-input model; do not assume it is interchangeable with the current Shift-first chord or ordinary tap surface.
5. **Matched validation:** compare the candidate with the current keyboard on literal text, Unicode/graphemes, selection, password/no-learning fields, field changes, terminal shortcuts, TalkBack/Switch Access, cold start, memory, battery and thermal behavior. Record host app, OS, build and language.

## Go/no-go gates

**Next step: a bounded standalone-build spike**, with a pinned source and a dependency/license inventory. Reproducible buildability and a reduced manifest are outcomes to establish in that spike, not claims from this review. It may evaluate pointer handling, composition and dictionaries without changing the shipped default; no consumer adoption occurs until the gates below pass.

**No-go for product adoption** if standalone buildability depends on unavailable platform-private modules; if removing contacts, cloud, download/update, sync, user-dictionary or boot paths breaks ordinary typing; if any input/context path cannot be bounded and cancelled at field transitions; if the JNI/dictionary provenance cannot be documented; or if accessibility, terminal, lifecycle and sensitive-field tests regress against the custom foundation.

The initial review recommended **evaluate selectively, do not adopt yet**. The subsequent product decision authorized a separate LatinIME fork and standalone port work. The experiment now builds with a restricted manifest and bounded automated evidence. Product adoption still requires the gates above, including remaining lifecycle/privacy work, complete attribution, feature parity, physical accessibility and migration acceptance.

## Primary evidence

* [AOSP LatinIME repository at pinned commit](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/)
* [Current Java Soong module](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/java/Android.bp)
* [Current LatinIME manifest and declared permissions/components](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/java/AndroidManifest.xml)
* [Current native JNI module](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/native/jni/Android.bp)
* [Legacy standalone Gradle file](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/build.gradle)
* [AOSP Java NOTICE](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/java/NOTICE) and [repository NOTICE](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/NOTICE)
