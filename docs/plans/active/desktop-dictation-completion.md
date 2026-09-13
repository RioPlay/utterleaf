# Desktop dictation and formatting completion

## Goal

Make successive hold-to-talk takes read naturally without fused words or
punctuation, provide useful explicit list/paragraph commands and an optional
Markdown output mode. Preserve intent, local processing and safe delivery to the
current editor. The broader [desktop roadmap](../../desktop-roadmap.md) remains
the status authority.

## Area

Desktop cleanup/formatting, `dictation_spacing.py`, native `edit_target.py`,
`app.py` delivery plumbing, local config/settings and focused desktop tests.
Android source, dependencies, tests and releases remain separate. Preserve the
existing dirty settings/polish changes and the
[settings pass](desktop-settings-pass.md).

## Constraints

- No ambient recording, passive typing/context collection, clipboard probing or
  unverified destructive editing. Do not restart the active dictation app during
  implementation or treat source tests as installed-build proof.
- Raw transcription/literal/code remain explicit ways to avoid prose rewriting.
- Use existing supported native-field snapshots only for immediate insertion
  neighbors; unsupported editors retain a documented conservative fallback.
- No blind leading/trailing spaces around every punctuation mark. Preserve URLs,
  decimals, paths, quotes, Unicode, existing whitespace and structured newlines.
- Optional Markdown changes formatting; it does not summarize, invent content,
  answer questions, execute code or send prompts to another service.
- Preferences save/reopen/restart and Reset to defaults must work; reset preserves
  vocabulary, models and other user data. Cancelling settings preserves old values.

## Acceptance

1. Repeated completed prose takes do not become `sentence.Next`; internal fused
   punctuation regressions preserve abbreviations, URLs, numbers and literal text.
2. Explicit bullets/numbered lists do not run into the next take or following
   caret text. List scope and exit commands are predictable.
3. In supported native Windows Edit fields, insertion beside existing words,
   punctuation or selected text uses valid UTF-16 boundaries and verified receipts.
   Failed/unsupported inspection never expands into an unverified edit.
4. Markdown is an explicit local output choice with deterministic examples and
   tests for headings, lists and paragraph separation; ordinary prose and quoted
   command names remain text. No promise of unrestricted natural-language reasoning.
5. Focused source tests and any changed settings captures pass. Installed-build
   live dictation and browser/macOS/Linux limitations are recorded separately.

## Verification

- `\.venv\Scripts\python -m pytest tests/test_dictation_spacing.py tests/test_polish.py tests/test_app.py tests/test_edit_target.py tests/test_inject.py`
- If settings/config change: `\.venv\Scripts\python -m pytest tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py`, affected settings tests,
  then full desktop pytest as required by AGENTS.md.
- Settings visuals: `\.venv\Scripts\python tests/capture_settings.py` (no microphone).
- Native-field and installed-app end-to-end tests remain a separate explicitly
  controlled session; never collect real conversation audio for test fixtures.

## Non-goals

No background capture, ambient screen reading, general assistant, cloud provider,
arbitrary model execution, desktop UI framework rewrite or Android code changes.
No packaging/release claim or restart of the user's running app in this source pass.
Model/download/provider extensions have a separate
[resource policy](../../model-resource-policy.md).

## Stop

Stop this slice when supported boundaries and Markdown behavior have focused
regressions, the necessary settings checks pass, independent review is complete
and docs match source. Keep broader editor adapters and inferred semantic
formatting as explicit follow-up work, not implicit feature claims.

## Progress

- September 12: user reports fused sentences and list friction while using the
  desktop app. Source already includes completed-prose suffixes; dirty-tree
  punctuation fixes exist. Running-build applicability is under investigation.
- Implemented list boundaries, UTF-16-safe native Edit insertion neighbors and
  explicit Markdown heading/list layout. No new context provider or remote path.
- Added persisted `output_format` (Prose default), matching Settings preview,
  save/cancel/reset checks, invalid-control routing and selective backup validation.
- Independent review found and resolved end-of-field separator loss, horizontal
  whitespace versus block boundaries, heading/prose joins and right-side full-stop
  duplication. Tests compose the final text, not only helper return values.
- Final independent full run, `\.venv\Scripts\python -m pytest -ra`: 763 passed,
  18 skipped in 25.70 seconds. Skips were 11 real-codec tests requiring an explicitly
  verified FFmpeg, 6 file-review UI tests blocked by this Python installation's Tk
  setup, and 1 Linux symlink test unavailable under Windows privileges. These are
  not verified coverage. Focused
  privacy/config/boundary and backup/settings tests pass. The repository boundary
  test now prunes Android generated dependencies while still inspecting own source.
- Root reran `tests/capture_settings.py` without microphone capture and inspected
  the final Vocabulary screenshot. No running desktop version was established by
  the read-only process check; no installed app was restarted or updated.

## Remaining

Browser/rich-editor and macOS/Linux caret adapters, actual installed-build
dictation, physical microphone delivery and broader natural-language formatting
remain unverified or planned. The source fixes are not a packaged release. The
resource/provider work remains separately scoped by its policy and roadmap.

The later request for optional speech-end stopping and automatic insertion is a
separate capture/session feature. Audit the existing local VAD/runtime and define
its cancellation, review and manual-start boundaries before adding it; the
formatting fixes above do not imply that feature exists.
