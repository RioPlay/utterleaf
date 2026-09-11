# Foundation dependency and asset inventory

This records the standalone `mobile/latinime` experiment. It does not change the
shipping `mobile/android` app or approve publication. The source bundle in
`notices/` has been reviewed for the bounded selections below; final APK packaging,
component-specific attribution and native member mapping remain separate checks.

## Examined build and packaged assets

The pre-notices unsigned release APK inspected during this work had SHA-256
`89366fc0328c1b9bddebbcf21b6eecb67b45289b0f57f85cd10d4da599919dec`.
ZIP inspection and SDK 36 `aapt2 dump resources` identified:

- 901 PNG files representing 204 logical drawable names: 884 generated imported
  LatinIME resource PNGs, one owned leaf image and 16 AndroidX notification images.
  Families include key backgrounds, keyboard symbols, toolbar/emoji-category icons,
  separators and notifications. Resource names in the release ZIP are shortened;
  logical names were checked through the compiled resource table.
- No packaged font files, binary dictionaries or speech models. The only raw
  resource is `raw/empty`, whose text says the dictionary provider is unavailable.
  `DebugProbesKt.bin` begins with Java class magic `CAFEBABE`; it is a coroutines
  resource, not a model. The imported setup video and image are excluded.
- ARM64 and x86-64 `libjni_latinime.so`, one `classes.dex`, Android resources and
  AndroidX baseline profiles. There were no packaged license/NOTICE documents in
  that examined APK. The new staged bundle must be verified in a later APK.

`app/build.gradle.kts` imports filtered `upstream/common/src`, `upstream/java/src`
and `upstream/java/res`. `excluded-sources.txt` controls omitted Java source;
resource exclusions remove obsolete setup/download UI. No external keyboard
renderer, FUTO code/assets or Hacker's Keyboard code/assets were added.

## AOSP provenance and branding

AOSP LatinIME revision: `127336e9f29d69607eab55982324b210279ae8c5` from
https://android.googlesource.com/platform/packages/inputmethods/LatinIME.
`SOURCE.json` contains 2,695 original imported path/hash records. This is original
source provenance, not a hash manifest of subsequently modified files.

The exact original `upstream/NOTICE` and `upstream/java/NOTICE` are retained in
source and staged as `AOSP-NOTICE.txt` and `AOSP-JAVA-NOTICE.txt`. Their historical
Lexiteria dictionary statement is preserved verbatim. **Those binary dictionaries
are not included**; the statement is not permission to distribute them.
`upstream/UTTERLEAF-NOTICE.md` records modifications and exclusions. Packaging must
refresh these three documents from their original source paths, not assume the
review copies remain current as implementation continues.

`app/src/main/res/drawable-nodpi/leaf.png` exactly matches the existing shipping
`mobile/android/app/src/main/res/drawable-nodpi/leaf.png`. Both have SHA-256
`fa097955b61b73a06c1b41ba19846e21eb887a08dd6cf732aeb1cfbb8d02fbdd`.
This establishes reuse of the existing Utterleaf branding asset; it does not invent
an upstream creator or a new third-party license for that asset.

## Resolved release dependency evidence

The following 47 coordinates were extracted from AGP's
`app/build/intermediates/metadata_library_dependencies_report/release/collectReleaseDependencies/dependencies.pb`.
The graph includes metadata-only/common/BOM coordinates and must not be mistaken
for 47 separate bundled runtime libraries. `notices/runtime-dependencies.json`
records the report hash, each POM source URL/hash, declarations, and locally cached
JAR/AAR artifact hashes. POMs without their own license declare it through a parent.
All resolved coordinates have an Apache 2.0 declaration in the inspected POM or
parent; declarations alone do not settle embedded third-party notices.

| Resolved coordinate | Local binary artifact | License evidence |
| --- | --- | --- |
| `org.jetbrains.kotlin:kotlin-stdlib:2.1.20` | kotlin-stdlib-2.1.20.jar | Apache 2.0, own POM |
| `org.jetbrains:annotations:13.0` | annotations-13.0.jar | Apache 2.0, own POM |
| `org.jetbrains.kotlin:kotlin-stdlib-common:2.1.20` | Metadata / no local JAR or AAR | Apache 2.0, own POM |
| `androidx.core:core:1.16.0` | core-1.16.0.aar | Apache 2.0, own POM |
| `androidx.annotation:annotation:1.8.1` | Metadata / no local JAR or AAR | Apache 2.0, own POM |
| `androidx.annotation:annotation-jvm:1.8.1` | annotation-jvm-1.8.1.jar | Apache 2.0, own POM |
| `androidx.annotation:annotation-experimental:1.4.1` | annotation-experimental-1.4.1.aar | Apache 2.0, own POM |
| `androidx.collection:collection:1.4.2` | Metadata / no local JAR or AAR | Apache 2.0, own POM |
| `androidx.collection:collection-jvm:1.4.2` | collection-jvm-1.4.2.jar | Apache 2.0, own POM |
| `androidx.concurrent:concurrent-futures:1.1.0` | concurrent-futures-1.1.0.jar | Apache 2.0, own POM |
| `com.google.guava:listenablefuture:1.0` | listenablefuture-1.0.jar | Apache 2.0, parent com.google.guava:guava-parent:26.0-android |
| `androidx.core:core-viewtree:1.0.0` | core-viewtree-1.0.0.aar | Apache 2.0, own POM |
| `androidx.interpolator:interpolator:1.0.0` | interpolator-1.0.0.aar | Apache 2.0, own POM |
| `androidx.lifecycle:lifecycle-runtime:2.6.2` | lifecycle-runtime-2.6.2.aar | Apache 2.0, own POM |
| `androidx.arch.core:core-common:2.2.0` | core-common-2.2.0.jar | Apache 2.0, own POM |
| `androidx.arch.core:core-runtime:2.2.0` | core-runtime-2.2.0.aar | Apache 2.0, own POM |
| `androidx.lifecycle:lifecycle-common:2.6.2` | lifecycle-common-2.6.2.jar | Apache 2.0, own POM |
| `org.jetbrains.kotlinx:kotlinx-coroutines-android:1.6.4` | kotlinx-coroutines-android-1.6.4.jar | Apache 2.0, own POM |
| `org.jetbrains.kotlinx:kotlinx-coroutines-core:1.6.4` | Metadata / no local JAR or AAR | Apache 2.0, own POM |
| `org.jetbrains.kotlinx:kotlinx-coroutines-core-jvm:1.6.4` | kotlinx-coroutines-core-jvm-1.6.4.jar | Apache 2.0, own POM |
| `org.jetbrains.kotlinx:kotlinx-coroutines-bom:1.6.4` | Metadata / no local JAR or AAR | Apache 2.0, own POM |
| `androidx.lifecycle:lifecycle-viewmodel:2.6.2` | lifecycle-viewmodel-2.6.2.aar | Apache 2.0, own POM |
| `androidx.lifecycle:lifecycle-livedata:2.6.2` | lifecycle-livedata-2.6.2.aar | Apache 2.0, own POM |
| `androidx.lifecycle:lifecycle-livedata-core:2.6.2` | lifecycle-livedata-core-2.6.2.aar | Apache 2.0, own POM |
| `androidx.profileinstaller:profileinstaller:1.3.0` | profileinstaller-1.3.0.aar | Apache 2.0, own POM |
| `androidx.startup:startup-runtime:1.1.1` | startup-runtime-1.1.1.aar | Apache 2.0, own POM |
| `androidx.tracing:tracing:1.2.0` | tracing-1.2.0.aar | Apache 2.0, own POM |
| `androidx.versionedparcelable:versionedparcelable:1.1.1` | versionedparcelable-1.1.1.aar | Apache 2.0, own POM |
| `org.jspecify:jspecify:1.0.0` | jspecify-1.0.0.jar | Apache 2.0, own POM |
| `androidx.legacy:legacy-support-v4:1.0.0` | legacy-support-v4-1.0.0.aar | Apache 2.0, own POM |
| `androidx.media:media:1.0.0` | media-1.0.0.aar | Apache 2.0, own POM |
| `androidx.legacy:legacy-support-core-utils:1.0.0` | legacy-support-core-utils-1.0.0.aar | Apache 2.0, own POM |
| `androidx.documentfile:documentfile:1.0.0` | documentfile-1.0.0.aar | Apache 2.0, own POM |
| `androidx.loader:loader:1.0.0` | loader-1.0.0.aar | Apache 2.0, own POM |
| `androidx.localbroadcastmanager:localbroadcastmanager:1.0.0` | localbroadcastmanager-1.0.0.aar | Apache 2.0, own POM |
| `androidx.print:print:1.0.0` | print-1.0.0.aar | Apache 2.0, own POM |
| `androidx.legacy:legacy-support-core-ui:1.0.0` | legacy-support-core-ui-1.0.0.aar | Apache 2.0, own POM |
| `androidx.customview:customview:1.0.0` | customview-1.0.0.aar | Apache 2.0, own POM |
| `androidx.viewpager:viewpager:1.0.0` | viewpager-1.0.0.aar | Apache 2.0, own POM |
| `androidx.coordinatorlayout:coordinatorlayout:1.0.0` | coordinatorlayout-1.0.0.aar | Apache 2.0, own POM |
| `androidx.drawerlayout:drawerlayout:1.0.0` | drawerlayout-1.0.0.aar | Apache 2.0, own POM |
| `androidx.slidingpanelayout:slidingpanelayout:1.0.0` | slidingpanelayout-1.0.0.aar | Apache 2.0, own POM |
| `androidx.swiperefreshlayout:swiperefreshlayout:1.0.0` | swiperefreshlayout-1.0.0.aar | Apache 2.0, own POM |
| `androidx.asynclayoutinflater:asynclayoutinflater:1.0.0` | asynclayoutinflater-1.0.0.aar | Apache 2.0, own POM |
| `androidx.cursoradapter:cursoradapter:1.0.0` | cursoradapter-1.0.0.aar | Apache 2.0, own POM |
| `androidx.fragment:fragment:1.0.0` | fragment-1.0.0.aar | Apache 2.0, own POM |
| `com.google.code.findbugs:jsr305:3.0.2` | jsr305-3.0.2.jar | Apache 2.0, own POM |

Actual DEX inspection confirmed Kotlin coroutines, JSR305 `javax.annotation`,
JetBrains annotations, JSpecify and Guava ListenableFuture classes. AndroidX
version resources corroborate core, lifecycle, profile installer and legacy UI
families. Several older AndroidX version marker contents are Gradle task strings;
use the dependency report/POM evidence for their resolved versions.

The core 1.16.0 and core-viewtree 1.0.0 AARs contain their own license entries.
`ANDROIDX-CORE-LICENSE.txt` and `ANDROIDX-CORE-VIEWTREE-LICENSE.txt` preserve those
entries exactly. General Apache 2.0 text is also supplied. A top-level archive
license search is not an exhaustive nested-AAR/source attribution audit.

JUnit, AndroidX test runner/rules and test extensions belong to test configurations;
they are not declared as main app dependencies. Gradle, AGP, Kotlin compiler, JDK,
CMake and host NDK executables are build tools; their entire licenses are not
attributed as though those executables were bundled in the APK.

## Static native runtime selection

The release Ninja files for both ABIs use Android API 26 targets,
`-shared -static-libstdc++`, and `-llog -latomic -lm`. A read-only NDK 28.0.13004108
Clang `-###` inspection expands the link inputs to `crtbegin_so.o`, static `libc++`,
compiler-rt builtins, `libunwind.a`, Android platform libraries and `crtend_so.o`.
The API-26 `libc++.a` linker script names `libc++_static` and `libc++abi`.
The toolchain's small `libatomic.a` file contains only a comment explaining that
the atomic APIs are provided by compiler-rt builtins; it contains no `INPUT`
directive and is not evidence that a separate GCC atomic runtime ships.
This establishes link inputs, not every archive member retained by `--gc-sections`.

The selected local source is NDK 28.0.13004108 `NOTICE.toolchain`, SHA-256
`69f10d9ba1dd4b21b886b680926056ba43fe37dbbb7e41edf548a39125a17f2a`.
These exact, inclusive line slices preserve complete sections, including LLVM
exceptions and legacy license alternatives. The independent reviewer checked the
source hash and section boundaries.

| Staged document | Source lines | Scope |
| --- | --- | --- |
| LLVM-PROJECT-NOTICE.txt | 1833?2112 | LLVM project Apache 2.0 with exceptions and legacy notice |
| COMPILER-RT-NOTICE.txt | 2113?2424 | compiler_rt notice, including legacy alternatives |
| LIBCXX-NOTICE.txt | 2425?2736 | libc++ notice, including legacy alternatives |
| LIBCXXABI-NOTICE.txt | 2737?3048 | libc++abi notice, including legacy alternatives |
| APACHE-2.0.txt | 1837?2039 | Complete Apache 2.0 text and appendix, without LLVM exceptions |

`notices/provenance.json` records hashes of every exact copy/slice. Unrelated
preceding host-tool GPL sections and the following OpenMP section were not copied
or represented as bundled runtime components. This selection does not relicense
Utterleaf or claim every component in the NDK is distributed.

### Component-specific libunwind and startup notices

The local toolchain `manifest_12896553.xml` (SHA-256
`3c77c503ce286fdf5a94bcf285bd72a2be479136dd06eca33ca289854cb214a2`)
pins LLVM revision `97a699bf4812a18fb657c2779f5296a4ab2694d2` and bionic
revision `b86008a9cd14a7748867d2232e6de439e4809c10`. These identify the sources
used for the following attribution. The compiler manifest does not independently
prove that each packaged NDK CRT object was built from that bionic revision.
The source selection is corroborated by the actual object symbols and include
relationships; reproducible source-to-object identity remains unverified.

| Document | Pinned source and preserved bytes |
| --- | --- |
| LIBUNWIND-LICENSE.txt | Entire `libunwind/LICENSE.TXT`, including explicit libunwind legacy NCSA/MIT notices |
| ANDROID-CRT-2012-NOTICE.txt | `libc/arch-common/bionic/crtbegin_so.c`, lines 1–27; identical notices in included `atexit.h` and `__dso_handle_so.h` are represented once |
| ANDROID-CRT-2013-NOTICE.txt | `libc/arch-common/bionic/crtend_so.S`, lines 1–27 |
| ANDROID-CRT-ATFORK-NOTICE.txt | Included `libc/arch-common/bionic/pthread_atfork.h`, lines 1–15 |
| ANDROID-CRT-ARM64-NOTICE.txt | Included `libc/private/bionic_asm_arm64.h`, lines 1–36, preserving Berkeley attribution and source identifiers |

Exact pinned Gitiles URLs, whole-source hashes, slice ranges and output hashes
are recorded in `notices/provenance.json`. The reviewer inspected local downloaded
bytes and source selection; an independent remote re-fetch failed with HTTP 503.
The libunwind license references `CREDITS.TXT`, which returns HTTP 404 at the pinned
revision; that historical reference is preserved without inventing a credits list.
No source implementation or new runtime dependency was imported by this work.

The ARM64 unstripped release library retains `_Unwind_RaiseException`,
`__on_dlclose`, `__on_dlclose_late`, `__dso_handle`, `atexit`, `pthread_atfork`
and `__FRAME_END__`. The map confirms explicit contributions from `crtbegin_so.o`.
The `__FRAME_END__` symbol alone does not prove that the original `crtend_so.o`
bytes survived: LLD processes/merges `.eh_frame`, and the map does not list a
nonzero contribution from that input. Its source notices are retained
conservatively for the known startup link input and ARM64 assembly include.
The broad sysroot NOTICE has not been copied wholesale or represented as
entirely bundled platform code.

### Retained native member evidence

The passing `foundation-property-bulk-notices-acceptance.log` build produced
release link maps at
`app/.cxx/RelWithDebInfo/191n4j6l/<ABI>/jni_latinime.map`. The inventory below
counts archive input members with a nonzero map contribution inside an output
section marked `SHF_ALLOC` by `llvm-readelf` on the matching unstripped library.
An independent reviewer separately parsed ELF section flags and confirmed both
member sets and all map/library hashes. Debug-only sections and zero-size markers
are excluded. This is evidence of
retained members, not a claim that every byte of those members is shipped.

| ABI | Map SHA-256 | Matching unstripped library SHA-256 |
| --- | --- | --- |
| arm64-v8a | `f6322ac552e99abd21d0e969f6f152cb044e26d3d687ae28a3ed64a053747064` | `32f0c6c17229995ae4980dc20e5ea946c7cfd839507830a44d2a87e7c6cf8658` |
| x86_64 | `7be7fccf76635b78c597d3246e5e6a6e27a9928275fcd060ae5fb54016766749` | `564ee2f6b523ab0de42309d379bf389733414a76d3aebdffd468958d203fc2a5` |

Both ABIs contain these explicit members:

- `libc++_static.a` (12): `call_once.cpp.o`, `error_category.cpp.o`,
  `exception.cpp.o`, `hash.cpp.o`, `ios.cpp.o`, `ios.instantiations.cpp.o`,
  `locale.cpp.o`, `memory.cpp.o`, `new_helpers.cpp.o`, `stdexcept.cpp.o`,
  `string.cpp.o`, `system_error.cpp.o`.
- `libc++abi.a` (15): `abort_message.cpp.o`, `cxa_default_handlers.cpp.o`,
  `cxa_demangle.cpp.o`, `cxa_exception.cpp.o`, `cxa_exception_storage.cpp.o`,
  `cxa_guard.cpp.o`, `cxa_handlers.cpp.o`, `cxa_personality.cpp.o`,
  `cxa_virtual.cpp.o`, `fallback_malloc.cpp.o`, `private_typeinfo.cpp.o`,
  `stdlib_exception.cpp.o`, `stdlib_new_delete.cpp.o`, `stdlib_stdexcept.cpp.o`,
  `stdlib_typeinfo.cpp.o`.
- `libunwind.a` (4): `UnwindLevel1.c.o`, `UnwindRegistersRestore.S.o`,
  `UnwindRegistersSave.S.o`, `libunwind.cpp.o`.

ARM64 `libclang_rt.builtins-aarch64-android.a` contributes seven members:
`aarch64.c.o`, `emutls.c.o`, `outline_atomic_cas8_4.S.o`,
`outline_atomic_ldadd4_4.S.o`, `outline_atomic_ldadd8_1.S.o`,
`outline_atomic_ldadd8_4.S.o`, `outline_atomic_swp8_4.S.o`.
x86-64 `libclang_rt.builtins-x86_64-android.a` contributes `emutls.c.o`.
No separate atomic or additional runtime archive appears in this retained-input
set. Linker-synthesized/merged regions may not retain per-input attribution, so
the map does not eliminate the source-to-object or nested-notice review limits.

The expanded 18-document catalog was verified byte-for-byte against current
sources in both debug and release APKs after this build. The unsigned release APK
SHA-256 is `badab22b179d96c5f41f19036dc39eb1359e2f34e65dc05a211b18e7b1a8edf2`.
This verifies packaging; it does not resolve all component licensing obligations.

## Remaining checks before publication

- Keep the verified 18-document APK catalog synchronized with build inputs;
  refreshed upstream modification notes must have fresh output hashes.
- Finish component-specific attribution review, including nested AAR material and
  any notices absent from published JAR/POM metadata. POM license fields are evidence,
  not a substitute for applicable source notices.
- Reconcile the selected libunwind and Android CRT/bionic attribution against
  the retained link members, and resolve the CRT source-to-object provenance
  limitation above. The map/member inventory narrows the actual component set;
  it does not independently settle component-specific nested license notices.
- Keep newly imported dictionaries, models and any gesture implementation outside
  this inventory until their source, license, bounds and verification are reviewed.

This is a partial provenance/notice implementation, not a completed legal audit,
signed release, verified upgrade or publication approval.
