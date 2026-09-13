# Android local emoji picker and search

## Goal and area

Provide a first-class Emoji button, browsable categories, English local search,
and explicit skin-tone variants in the original Android keyboard. Use the full
fully-qualified Unicode Emoji 17.0 catalog with CLDR 48 English annotations;
device font support determines which entries can be displayed. This is a data
integration, not imported keyboard code, artwork or fonts.

Area: new Android catalog, generator, resource notices and picker; `TypingPanel`
entry controls; `KeyboardIme` lifecycle; Android JVM/tooling/instrumentation tests
and mobile documentation. Desktop dependencies, source and releases stay separate.

## Status and ownership

September 12: the local picker, catalog, search, categories, paging and explicit
variants are implemented in unreleased source and passed independent production,
resource and test review. The API 35 emulator exposes 3,944 of 3,944 catalog
entries with its current font. Search uses CLDR 48 English names and keywords,
keeps a 48-character transient query, and clears it on field/subtype change,
hide, exit and disposal. Exact fully-qualified sequences insert once without an
editor action; raw fields disable Emoji. No new permission, clipboard query,
network path, history or saved search was added.

The reviewed toolbar is Tools / Edit / Emoji / Voice. Number-row and Terminal
toggles remain at the top of Tools. Full/Left/Right, both themes and the selected
QWERTY/QWERTZ/AZERTY positions apply to the picker and search keys. All 18 owned
captures passed visual review; the three light/Full examples are published in
the [Android emoji guide](../../android-emoji.md). This source is not released,
and physical-phone, landscape, TalkBack/Switch Access and broad host-editor
acceptance remain open. **Next:** the separate
[private draft editor](android-private-draft.md) is an active plan; it is not yet
implemented or verified.

Catalog owner: `EmojiCatalog.kt`, its JVM tests, `tools/emoji_catalog.py`, its Python
tests, pinned Unicode source data, generated Android resource, Android Unicode
notice and provenance record. Integrator owns panel/lifecycle integration and
existing shared Android tests until explicitly reassigned. No parallel edits to
`DeviceTest.kt` or `PrivacyCoreTest.kt`.

`TypingPanel` owns the separate `EmojiPanel`, reusing its existing aligned column
and already guarded commit callback. This also gives Settings practice and local
voice-transcript editing the same picker without three editor-host implementations.
`KeyboardIme` explicitly supplies raw-field availability. Reset, detach, geometry
change and returning to typing clear the picker; both panel and editor generations
guard insertion.

## Constraints and behavior

- No Internet permission, runtime download, external font, microphone, telemetry,
  editor-context collection, clipboard access or automatic emoji history. Search
  is transient local state, cleared on field change, hide, panel exit and teardown.
- Daily controls become Tools, Edit, Emoji and Voice. Number-row and Terminal
  toggles remain available at the top of Tools with their existing preferences.
  Keep touch targets useful at narrow widths; do not add a permanent toolbar row.
- Emoji has an always-visible ABC return, category chooser, search and bounded
  paging. Respect Full/Left/Right placement, theme, key/label sizing and insets.
  Provide accessible names and selected/disabled states, including variants.
- Search uses a local display and its own letter keys, Space, Delete and Clear.
  It must never use an `EditText`, host composition, editor actions or clipboard.
  Bound the query to 48 characters and normalize search deterministically using
  English names/keywords. The query has no persistence or diagnostic output.
- An explicit emoji tap commits its exact catalog sequence once to the current
  guarded editor, with no added space, newline or submit action. Refusal reports
  failure without retry or another insertion route. Raw `TYPE_NULL` fields show
  Emoji unavailable; explicit insertion into text/password fields is permitted
  without retaining query or history.
- Keep all fully-qualified entries, including gender/ZWJ/flag/tag sequences.
  Standalone components and minimally/unqualified spellings are excluded from
  the palette. Group tone variants by removing only skin-tone modifiers and
  variation selectors for the family key; every selectable member remains an
  exact fully-qualified upstream entry. Keep gendered forms separate rather than
  inventing semantic families. Offer an ordinary tap route to every variant.
- Glyph support filtering uses the device font and never downloads replacements.
  Explain an empty result/catalog and allow returning to typing. Font availability
  does not establish rendering in every host editor or on physical phones.
- Load bounded public catalog data off the UI thread and cache immutable data.
  Stale loads, queries and detached controls cannot update a new panel or field.
  Search ranks deterministically and limits rendered results per page.

## Resource contract

Use [Unicode Emoji 17.0 data](https://www.unicode.org/Public/17.0.0/emoji/emoji-test.txt)
and the official `unicode-org/cldr` release-48 English annotations, pinned to the
resolved commit and exact bytes. Record publisher, URL, version/commit, size,
SHA-256, parsing limits and output identity. Include the Unicode License V3 and
copyright in the Android artifact and source distribution. The
[Unicode terms](https://www.unicode.org/copyright.html) apply the
[Unicode License V3](https://www.unicode.org/license.txt) to these data files;
retain their terms independently of Utterleaf's Apache-2.0 code.

The generator operates offline on vendored pinned data; it must not execute
upstream code or resolve XML external entities/DTDs. An exact known official
DOCTYPE may be removed before parsing; reject any other declaration/entity.
Resource updates require renewed identity, rights and parser review. Raw source
files are development inputs; bundle only the generated catalog and notices.

## Acceptance

1. Deterministic generator verifies every input hash/size; exact fully-qualified
   count, unique valid sequences, category coverage, CLDR annotations and variant
   links match the pinned sources. Check malformed data and resource bounds.
2. JVM tests cover catalog parsing, names/keywords, exact/prefix/token ranking,
   tone families, complete Unicode sequences, invalid data and query bounds.
3. Direct panel tests cover categories, pages, local query/delete/clear, variants,
   glyph filtering, empty/failure states, disabled fields and stale callbacks.
4. Actual IME test keeps synthetic host text/selection unchanged while entering a
   query; a chosen ZWJ/tone sequence replaces the selection exactly once without
   editor action. Verify ABC return, field/hide cancellation, raw-field refusal,
   password privacy, and unchanged synthetic emulator clipboard.
5. Regress existing Tools toggles, typing, editing, voice transitions and layout
   persistence. Review owned browse/search/variant views in both themes and
   Full/Left/Right, narrow and wide columns; retain explicit landscape, physical
   phone and assistive-technology evidence gaps.

## Verification and stop

Final source verification with the configured JDK/SDK:

- `python -m unittest discover -s mobile/android/tools -p test_*.py`: 14 tests
  passed, including the pinned generator and resource identity checks.
- `gradlew.bat testDebugUnitTest lintDebug --no-daemon`: 19 JVM tests across four
  classes passed, including 7 emoji catalog tests; lint reported 0 errors and 47
  warnings.
- The final focused API 35 run of `EmojiPanelTest,EmojiImeTest` passed 9 tests in
  48.953 seconds. The affected regression run passed 59 tests in 110.485 seconds.
  An earlier 13-test integration run passed in 69.387 seconds. Accounting for the
  six repeated panel tests, 75 distinct instrumentation tests passed.
- Eighteen keyboard-only captures (browse, search and variants across both themes
  and Full/Left/Right) total 1,735,114 bytes and passed visual review. The final
  search capture verifies the selected letter layout's key widths and stagger.

The initial capture-width assertion failure was confined to the test and fixed;
the final 9-test run supersedes the earlier failed intermediate log. Independent
review read the final source and recorded results. Stop this slice here. No
recents, preferred-tone persistence, stickers/GIFs, network search, new
dictionaries/correction, copied keyboard code, new model engine, physical
acceptance claim or release belongs to this slice.
