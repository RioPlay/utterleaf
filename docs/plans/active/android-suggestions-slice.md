# Suggestion strip slice — R3 first increment

[Rebuild plan](android-keyboard-rebuild.md) · [Roadmap](../../mobile-roadmap.md) ·
[Community wants](../mobile-keyboard-community-wants-2026-09.md)

## Goal

The public's number-one ask (FUTO #1334 spellchecker, 42 reactions; HeliBoard
autocorrect-per-field reports; r/fossdroid "weak suggestions drive users away")
is working word assistance. This slice ships the mockup's suggestion strip with
honest, bounded behavior: **completions of the current word only** — the
engine can never replace typed text on its own, so nothing here can silently
change a person's meaning. Reversible auto-correction and next-word prediction
remain later R3/R4 work behind their own gates.

## Area and ownership

- `SuggestionEngine.kt` (pure engine), `SuggestionRepository.kt` (resource
  loader), `res/raw/wordlist_en.txt`, `tools/build_wordlist.py`,
  `tools/test_wordlist.py`.
- `TypingPanel.kt` (strip row, chip completion), `KeyboardIme.kt` (bounded
  before-cursor read, balanced complete transaction, gates),
  `KeyboardOptions.kt` (`suggestions` preference),
  `KeyboardSettingsActivity.kt` (Typing assistance toggle).
- One writer; integrator review before release.

## Dictionary provenance

Two popular frequency lists were evaluated and **rejected**:
`google-10000-english` (GitHub "Other/NOASSERTION" license; corpus editing
notice advises against commercial use) and Norvig's `count_1w.txt` (code MIT
but data derived from the LDC-licensed Google Trillion Word Corpus, no
redistribution rights). The shipped list is derived **solely from
public-domain Project Gutenberg texts** by
`mobile/android/tools/build_wordlist.py` (16 books listed in the script;
reproducible; 10,989 lowercase alpha words, frequency-ordered). Provenance is
recorded in `assets/NOTICE.txt`. Known limitation, recorded: classical prose
under-represents some modern vocabulary; the accepted local-vocabulary idea
(custom/importable lists) is the later expansion path.

## Behavior contract

- Composing word = trailing letter run immediately before the caret, read as a
  bounded `getTextBeforeCursor` window (≤32 code points). No document reads,
  no surrounding-paragraph access, no logs.
- Chips (max 3) are frequency-ranked prefix completions, case-adapted
  (first-char and ALL-CAPS patterns). The composing word itself is excluded
  when it is an exact entry.
- Tap = one balanced editor transaction: batch edit, delete the verified
  composing run, insert the candidate; if the insert fails after the delete,
  the original word is re-inserted. The composing word is **re-verified at tap
  time**, so caret movement after rendering can never delete unrelated text.
- The strip's height is stable while visible; it hides on symbols pages and
  whenever the preference is off. Refresh paths: commits, delete, navigation,
  space (and its selection chord), Enter.
- **Gates:** off when the `suggestions` preference is off (default on, migrated
  once with the redesign defaults), and never on password fields, raw
  `TYPE_NULL` fields, or any field where speech/drafts are already disabled.
  No learning, no auto-replacement, no network, no persisted input.

## Acceptance

- JVM: engine rank/case/exclusion/bounds tests; wordlist resource validation.
- Live IME: strip completes the composing word through the real editor;
  gates verified on preference-off, password, and raw fields.
- Regression: persistence, tuning, geometry, backspace/compose/editor-contract
  classes pass with the strip enabled.

## Verification

- `python -m unittest discover -s mobile/android/tools -p test_*.py`
- `mobile/android`: `gradlew.bat testDebugUnitTest lintDebug --no-daemon`
- Focused instrumentation: SuggestionStripTest, KeyboardTuningTest,
  PersistenceTest, KeyboardGeometryTest, BackspaceSelectionTest,
  ComposeImeTest, KeyboardEditorContractTest.

## Non-goals

Auto-correction, next-word prediction, learning, snippets, dictionaries for
other languages, custom word import, emoji recents. Physical-device, TalkBack
and Switch Access acceptance for the strip remain open; a strip that assists
but never replaces typing does not add a new gesture-only action.

## Stop

Stop when the named checks pass, docs match, and CI is green. Record next
slices (word-delete units, explicit local vocabulary, then reversible
correction) in the roadmap; do not broaden into the R4 prediction engine here.

## Progress

- September 17, 2026: slice implemented and locally verified (JVM engine +
  wordlist tests green; live-IME completion, preference/password/raw gates,
  16-test focused regression, lint, tooling tests). CI pending.
