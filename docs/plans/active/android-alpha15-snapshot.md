# Android alpha15 snapshot

## Goal and area

Publish the next signed Android preview with the compact keyboard layout and
the installed name Utterleaf. Prepare a separate version/release-notes commit
after the compact-layer implementation passes its local acceptance checks and
independent review. Own `mobile/android/app/build.gradle.kts`, Android release
notes and the Android release documentation; keep desktop changes separate.
The Android build workflow must check out the reported PR head SHA explicitly
so its release-input artifact comes from that exact source, rather than GitHub's
temporary merge checkout. Push/manual runs retain their own `github.sha`.

## Scope and constraints

Include the reviewed post-alpha14 Backspace selection gesture, single sliding
Tools strip, replacement settings/edit/navigation layers, comma-hold Settings
access and Utterleaf app/keyboard labels. The optional voice-only provider is
Utterleaf dictation. Preserve alpha14's other features and their documented limits.

Keep application ID `org.utterleaf.voice`, persistent alpha03+ signing identity,
preferences, imported models and privacy boundaries. Increase versionCode to 15
and versionName to `0.1.0-alpha15`; never relabel a version-14 debug APK as a
release. No new runtime dependencies, permission, network access, typing history,
ambient recording or screenshot-protection change is part of this snapshot.
The published alpha14 and desktop RC2 artifacts remain unchanged.

## Acceptance and verification

1. The [compact-layer contract](android-compact-layers.md) passes its named local
   geometry, native gesture, private/editor and settings regression gates.
   Record missing local speech fixtures explicitly; the canonical workflow
   supplies its pinned inference fixtures.
2. Independent review clears the final implementation, updated tests and release
   metadata. Document implemented behavior separately from device verification.
3. Canonical Android CI passes for the exact version-15 source SHA, including
   tooling, JVM, lint, release build and the full API 35 instrumentation suite.
   Preserve its `Android-release-input` artifact for protected signing.
4. Merge the reviewed source through its Android PR. The `android-v0.1.0-alpha15`
   tag must identify the exact verified source and be on main ancestry.
5. Use the existing main-only signing/publishing workflow. It must verify package,
   version, non-debuggable state, zip alignment, certificate continuity and
   signed install/upgrade/reinstall before publishing the APK and sidecars.
6. Independently check the published APK checksum, signer and version metadata;
   confirm the normal update path and deliver the actual signed APK link.

Run the local commands listed in the compact-layer contract before metadata
preparation. After the version change, run Android tooling release-contract
tests and compile the release metadata; canonical CI owns the complete build
and emulator run for the exact final revision. Do not substitute an earlier
green run or a debug installation for these release gates.

## Limits and stop

Physical-phone testing is explicitly deferred by the user to post-release
feedback. It remains unperformed follow-up, as do TalkBack/Switch Access,
landscape, broad editor and real Obtainium acceptance. Emulator and owned-view
evidence do not establish comfort or assistive-technology usability.

Do not expand this snapshot into prediction, swipe typing, new languages,
Incognito, touch heatmaps or longer Android speech capture. Those remain on the
mobile roadmap. Stop snapshot work after publication and verification; broader
Utterleaf development continues in its separate platform plans.

## Status

The compact implementation is committed at `a8e39af` after independent source,
test and visual review. Version/release-note preparation is on
`release/android-alpha15`, using the same build workspace to avoid duplicating
native build artifacts. Local instrumentation summaries were console-only;
canonical CI must preserve its complete exact-revision reports. Alpha14 is still
the current published Android release; no alpha15 tag or signed APK exists yet.

Metadata review is clear. After the version change, `python -m unittest discover
-s tools -p 'test_*.py'` passed all 14 tooling tests. With `ANDROID_HOME` set to the
installed SDK, `gradlew :app:processReleaseMainManifest --offline --no-daemon`
passed (3 tasks, 9 seconds). The generated release manifest reports package
`org.utterleaf.voice`, versionCode 15 and versionName `0.1.0-alpha15`.
`git diff --check` is clean. These metadata checks do not replace canonical CI
or protected signing.
