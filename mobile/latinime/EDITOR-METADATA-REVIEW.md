# Editor metadata retention review

Status: the bounded snapshot below is implemented and independently reviewed.
The original source anchors record the pre-change audit; validation results are
tracked in [execution evidence](EXECUTION-EVIDENCE.md). Broader cache retirement,
`mAppliedEditorInfo` and `InputAttributes` lifetime remain separate work.

## Retention and consumers

`KeyboardLayoutSet` keeps `EditorInfo` in `Params` at
`upstream/java/src/com/android/inputmethod/keyboard/KeyboardLayoutSet.java:117`,
assigns the builder's framework object at line 275, and passes it into each
`KeyboardId`. `KeyboardId.mEditorInfo` at
`upstream/java/src/com/android/inputmethod/keyboard/KeyboardId.java:79` is then
reachable from cached `Keyboard` objects. The soft-reference cache is declared
at `KeyboardLayoutSet.java:87`; the four-entry strong/forcible cache is declared
at line 86 and populated at lines 238-241. Clearing the soft cache does not by
itself release keyboards held by the forcible cache.

The direct consumers are:

- `KeyboardId.java:94-100, 105-121, 125-142, 153-174`: full `inputType` and
  `imeOptions` drive password, multiline, navigation, and action behavior;
  `actionLabel.toString()` becomes `mCustomActionLabel`; equality/hash include
  the derived values and label.
- `KeyboardId.java:211-217`: keyboard equivalence compares only
  `inputType`, `imeOptions`, and `privateImeOptions`.
- `KeyboardAccessibilityNodeProvider.java:320-322`: reads the cached editor
  only to call `AccessibilityUtils.shouldObscureInput`; that method at
  `AccessibilityUtils.java:132` reads `inputType` (plus current accessibility
  and audio state).
- `KeyboardLayoutSet.java:272-304`: builder-time mode, no-settings, and
  force-ASCII decisions read the incoming editor. These can be derived before
  the framework object is discarded.

There are separate retention boundaries outside the keyboard cache:
`LatinIME.java:457` stores `mAppliedEditorInfo`, compares it at line 514, and
assigns it at line 528. `InputAttributes` also has its own editor reference.
Removing `KeyboardId.mEditorInfo` does not remove those paths; they require a
separate lifecycle review.

## Implemented sanitized snapshot

Owned Kotlin `KeyboardEditorInfo` captures an immutable, local snapshot when
`KeyboardLayoutSet.Builder` receives the framework object. Its fields are:

```text
inputType: Int
imeOptions: Int
privateImeOptions: String?
actionLabel: String?
```

Copy `actionLabel` with `toString()` and preserve null versus empty. Preserve
the complete integer values rather than masking them: navigation flags,
`IME_FLAG_NO_ENTER_ACTION`, and the action mask all affect layout cases or
keyboard equality. `actionId`, extras, package name, hint/selection metadata,
field IDs, and surrounding text have no consumers in `KeyboardId` or layout
construction.

`Params` should retain the snapshot and already-derived booleans, while the
builder's framework `EditorInfo` remains local to construction. `KeyboardId`
should expose snapshot-derived helpers instead of a framework object. The
accessibility call should accept the copied input type (or an equivalent
keyboard-id predicate) while preserving `InputTypeUtils.isPasswordInputType`
semantics. The equivalence helper should compare snapshots, or compare a
snapshot against transient incoming fields without storing that object.

## Required regression coverage

- Equal snapshots must reuse the same cached keyboard for identical full
  `inputType`, `imeOptions`, and `privateImeOptions` values.
- Different password and visible-password input types must preserve keyboard
  selection and accessibility obscuring behavior.
- Multiline, `IME_ACTION_*`, custom action labels, `IME_FLAG_NO_ENTER_ACTION`,
  and navigate-next/previous cases must preserve layout selection and labels.
- Null and empty action labels must remain distinct; non-String labels must
  retain current `toString()` behavior.
- Cache cleanup/replacement tests must prove no framework `EditorInfo` is
  reachable from either the soft cache or forcible cache after retirement.
- A separate test should cover `mAppliedEditorInfo`/`InputAttributes` once
  their lifecycle changes are designed.

The implementation introduces no passive collection, logging or external data
flow. Upstream modifications are recorded in `upstream/UTTERLEAF-NOTICE.md`.
The declared-field checks establish the cached object structure; they are not
proof that all editor metadata or native cache lifetimes have been retired.
