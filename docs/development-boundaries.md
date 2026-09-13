# Desktop and mobile development boundaries

[Development guide](development.md) · [Roadmap hub](roadmap.md)

Utterleaf uses one repository with separate application roots, dependencies,
builds, tests and releases. A repository split is unnecessary to enforce these
boundaries; it remains an option if ownership or release operations later require it.

| Concern | Desktop | Android | iOS |
| --- | --- | --- | --- |
| Product plan | [Desktop roadmap](desktop-roadmap.md) | [Mobile roadmap](mobile-roadmap.md) | Dedicated iOS track in the mobile roadmap |
| Application source | `utterleaf/` | `mobile/android/app/src/main/` | Not implemented; future root `mobile/ios/` |
| Dependencies/build | Root `pyproject.toml`, Python, `packaging/` | `mobile/android/` Gradle, Kotlin, NDK/CMake | Future native Apple project |
| Tests | Root `tests/` | Android `src/test/` and `src/androidTest/` | Future native test targets |
| CI | `.github/workflows/build.yml` | `.github/workflows/android.yml` | Separate workflow when implemented |
| Versions/tags | Python version; stable `v*` tags; Windows preview `desktop-v*` tags | Android versionCode/versionName; `android-v*` tags | Reserve `ios-v*`; no release today |
| Distribution | Three-platform stable archives; separate Windows-only prerelease | Separate Android prerelease and signed APK | Separate Apple distribution |

## Rules for changes

- Keep Android dependencies out of `pyproject.toml` and desktop dependencies out of
  Gradle. Desktop package discovery includes only `utterleaf*`; pytest targets `tests/`.
  `tests/test_repo_boundaries.py` fails closed if those imports or discovery rules drift.
  Its Android inventory excludes Gradle/native generated dependencies and build
  outputs; handwritten source (including a package named `build`) stays checked.
- Do not move desktop source just to make the tree symmetrical: that would churn
  imports, packaging and CI without improving isolation.
- Share reviewed specifications, test examples, brand artwork and security principles.
  Do not share transcript/config stores or runtime credentials between applications.
- Reuse native code only through an explicit versioned dependency with its own
  licensing and tests. Similar features do not require a common application runtime.
- Keep focused commits/PRs by platform. Describe shared changes and validate each
  affected platform; passing one platform's tests does not validate the others.
- Update the platform's roadmap, user guide and release notes together. Shared
  roadmap entries link to platform evidence instead of duplicating status.

## CI and release isolation

Desktop push/PR CI ignores changes confined to `mobile/**`, `docs/mobile*.md`, or
an Android workflow. Other paths conservatively keep the desktop checks running.
Desktop `v*` tags still run the release build regardless of changed file paths.
Windows `desktop-v*` preview tags use a separate Windows-only build and publish as
a prerelease with `latest=false`; they do not replace the stable desktop release.
Android CI is scoped to Android source/build changes and its workflow; Android
Markdown-only edits do not rebuild native binaries. Both workflows can be run manually.

Shared brand/license changes must be reviewed for both products; dispatch Android
CI explicitly if they affect its packaged inputs. Some Android artwork and notices
are bundled copies, so updating a documentation asset alone does not update an APK.

The desktop release publishers accept their distinct stable or preview tag forms
and verify the matching desktop jobs and source revision. Android release publication uses a separate manually dispatched signing workflow after CI;
do not upload Android artifacts to a desktop release or replace desktop's stable
latest release with a mobile alpha. The mobile release key is kept in a main-only GitHub environment. Physical update
testing and offline key backup remain acceptance gates.

If branch protection later requires always-present checks, use a routing/gate job
instead of workflow path skipping so unrelated changes do not wait on missing checks.
