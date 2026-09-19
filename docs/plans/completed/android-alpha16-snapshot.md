# Android alpha16 snapshot

## Completion - September 18, 2026

Published as android-v0.1.0-alpha16 on September 15; implementation merged through PR #43.

This bounded increment is closed. The evidence below is historical; earlier
pending/unreleased statements describe that stage, not current work. Physical,
editor and accessibility limits remain open in the [platform roadmap](../../mobile-roadmap.md).

## Goal and area

Publish the next signed Android preview with All Actions, the spatial Edit pad,
latched Terminal modifiers and neighboring-word Select. Prepare version and
release-note metadata after the action-organization implementation passes its
local acceptance checks. Own `mobile/android/app/build.gradle.kts`, Android
release notes and the Android release documentation; keep desktop changes
separate.

## Scope and constraints

Include the reviewed All Actions layer, spatial Edit pad, Select tap/hold,
latched Ctrl/Alt, Shift that stays on for arrows, compact Terminal accessory
keys and the complete US punctuation pages. Preserve alpha15's Utterleaf names,
Backspace selection gesture, comma-hold Settings and earlier verified features.

Keep application ID `org.utterleaf.voice`, persistent alpha03+ signing identity,
preferences, imported models and privacy boundaries. Increase versionCode to 16
and versionName to `0.1.0-alpha16`; never relabel a version-15 debug APK as a
release. No new runtime dependencies, permission, network access, typing history,
ambient recording or screenshot-protection change is part of this snapshot.
The published alpha15 and desktop RC2 artifacts remain unchanged.

## Acceptance and verification

1. The [action-organization contract](android-action-organization.md) passes its
   named local geometry, modifier, private/editor and settings regression gates.
2. Independent review clears the final implementation, updated tests and release
   metadata. Document implemented behavior separately from device verification.
3. Canonical Android CI passes for the exact version-16 source SHA, including
   tooling, JVM, lint, release build and the full API 35 instrumentation suite.
   Preserve its `Android-release-input` artifact for protected signing.
4. Merge the reviewed source through its Android PR. The `android-v0.1.0-alpha16`
   tag must identify the exact verified source and be on main ancestry.
5. Use the existing main-only signing/publishing workflow. It must verify package,
   version, non-debuggable state, zip alignment, certificate continuity and
   signed install/upgrade/reinstall before publishing the APK and sidecars.
6. Independently check the published APK checksum, signer and version metadata;
   confirm the normal update path and deliver the actual signed APK link.

After the version change, run Android tooling release-contract tests and compile
the release metadata; canonical CI owns the complete build and emulator run for
the exact final revision. Do not substitute an earlier green run or a debug
installation for these release gates.

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

Implementation is on `feat/android-action-organization` in the Android worktree,
still uncommitted at snapshot preparation. Version metadata is `0.1.0-alpha16`
/ versionCode 16. Alpha15 remains the current published Android release; no
alpha16 tag or signed APK exists yet.

September 14 local metadata checks on this tree:

- `python -m unittest discover -s tools -p test_*.py`: 14 passed.
- `gradlew :app:processReleaseMainManifest testDebugUnitTest lintDebug --offline --no-daemon`:
  the generated release manifest reports package `org.utterleaf.voice`,
  versionCode 16 and versionName `0.1.0-alpha16`. 31 JVM tests passed. Lint has
  0 errors and 51 existing warnings. `git diff --check` is clean.
- Earlier focused API 35 runs on `emulator-5554` covered Select, latched
  modifiers, TerminalInput, CompactLayer, LetterLayout, OneHandLayout and
  KeyboardEditorContract. Those do not replace the full exact-revision suite.

Canonical CI must preserve complete exact-revision reports. Do not treat
focused emulator runs as the full suite. No commit, PR, tag or signed APK yet.
