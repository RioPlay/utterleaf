# Foundation lint evidence and triage

Snapshot: `foundation-storage-transaction-acceptance.log`, 12 JVM / 102 API 35
emulator tests. `app/build/reports/lint-results-debug.xml` reports zero errors,
4,021 warnings and one hint. This is a local build; remote CI and physical
accessibility acceptance remain open. No new suppression or baseline was added.

| Finding | Count | Follow-up |
| --- | ---: | --- |
| UnusedResources | 2,041 | Trace source/XML/JNI/reflection references before removing inherited resources. Unused in this experiment does not mean removable from promised features. |
| MissingTranslation | 1,759 | Keep warnings visible; audit owned settings/notices text and supported-language coverage. Do not represent fallback English as localization acceptance. |
| TypographyEllipsis | 64 | Low-priority inherited text cleanup after supported-language review. |
| Typos | 32 | Review actual text and language before changing dictionary or resource names. |
| ObsoleteSdkInt | 24 | Check the foundation's minimum API and upstream provenance before simplifying branches. |
| IconDuplicates | 19 | Compare asset provenance and resource selection before deduplication. |
| DiscouragedApi | 12 | Inspect dynamic lookup callers; graph absence is insufficient. |
| ClickableViewAccessibility | 9 | Audit actual accessibility delegation and action dispatch, then exercise TalkBack on a physical device. Adding performClick solely to silence lint is insufficient. |
| InconsistentArrays | 7 | Check consumers of qualified emoji, keyboard-height and touch-correction arrays. Different resource lengths alone do not establish an indexing defect. |
| StaticFieldLeak | 5 | Trace application versus service/view ownership and actual teardown, including framework-driven recreation. |

The nine accessibility findings cover EmojiPageKeyboardView, EmojiPalettesView
(three touch-listener assignments and delete handling), InputView, MainKeyboardView,
MoreKeysKeyboardView and SuggestionStripView. These are source findings, not a claim
that each is broken or already accessible.

The five static-lifetime findings name AccessibilityUtils, KeyboardSwitcher,
PermissionsManager, RichInputMethodManager and TargetPackageInfoGetterTask. Their
retained fields must be checked against real construction and teardown paths.
Scoped source review confirmed KeyboardSwitcher retains its service/theme/views after
destruction, with additional PointerTracker queue/proxy roots and KeyboardLayoutSet
forced-cache/EditorInfo retention. This is an open lifecycle follow-up at the source
checkpoint; see the execution ledger. Other static-lifetime findings remain unaudited.
Other findings include four DefaultLocale and two Autofill warnings. The latter
refer to inherited user-dictionary layout fields; adding autofill behavior is not
an automatic resolution under the foundation's privacy policy.

Lint points into `app/build/generated/latinime/java` and `res`. Review and edit the
corresponding `upstream/java/src` and `upstream/java/res` originals, never generated
copies. The full XML report remains the authority for smaller categories omitted
from this summary. Counts classify work; they do not certify runtime behavior.
