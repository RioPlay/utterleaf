# Desktop modernization

Status: active. This is the owning contract for the post-RC2 desktop experience
work. It supersedes chat-only planning, but not the desktop roadmap or the
bounded contracts linked below.

[Desktop roadmap](../../desktop-roadmap.md) ·
[UI baseline](../../desktop-ui-baseline.md) ·
[Interface guide](../../interface.md) ·
[Consumer experience](../../consumer-experience.md)

## Goal

Make Utterleaf Desktop feel like a quiet, fast, native local utility: immediately
clear about readiness, capture, processing, failures, and recovery while staying
out of the user's way.

The work should modernize the existing Tk desktop shell incrementally. It must
not rewrite the stable speech, capture, delivery, or settings architecture for
visual fashion.

## Area

- Desktop application surfaces under `utterleaf/`, primarily the Settings shell,
  tray, status indicator, theme, brand presentation, device/model presentation,
  and reusable recovery copy.
- Focused desktop tests under `tests/`, deterministic screenshot tools, and
  desktop documentation.
- Shared terminology and reviewed brand assets only where a cross-platform
  change is explicitly assigned and validated for both platforms.

Android source, dependencies, builds, tests, and releases remain separately
owned. Desktop product work must not import Android runtime code or dependencies.

## Constraints

- Security first, privacy second, convenience third. No ambient recording,
  passive text collection, hidden cloud fallback, transcript history, or
  unverified model loading.
- Preserve local processing as the normal path. Explain the one-time model
  download exception and keep network permission explicit.
- Retain the current native Tk architecture unless measured accessibility, DPI,
  platform integration, maintenance, or interaction failures justify a decision
  gate. Rounded corners and fashion are not justification.
- Keep the five existing primary destinations stable until evidence shows a
  different information architecture is needed. Evolve the Dictation landing
  surface before adding another primary route.
- Keep common controls visible and move technical identifiers, paths, checksums,
  backend names, and deep recovery into progressive disclosure.
- Preferences stay local. Save/apply, cancellation, persistence, staged defaults,
  and reset behavior must remain explicit and tested. Reset must not remove
  models, vocabulary, or unrelated user data.
- Never silently substitute a different named microphone. If a documented safe
  fallback is introduced later, disclose it at the moment it happens.
- Utterling remains decorative. Text and the operational leaf/status treatment
  must communicate every meaningful state without relying on color or artwork.
- Do not claim screenshots, mocked states, an emulator, or unit tests establish
  physical-device, screen-reader, mixed-DPI, installed-build, or idle-performance
  acceptance.
- One integrator owns `utterleaf/app.py`, `config.py`, `settings.py`,
  `settings_ui.py`, and `__main__.py`. Rebase later UI-bearing OBS branches
  individually after this stream stabilizes; do not merge the old stack as-is.

## State and language decisions

Preserve stable runtime keys and asset names. The shared desktop artwork labels
and indicator error headlines now follow this mapping. Settings separately
requires a matching successful model load before reporting Ready; the idle
artwork alone proves neither model readiness nor microphone availability:

| Semantic state | Existing asset/runtime source | User-facing label |
| --- | --- | --- |
| Ready | `idle` | Ready |
| Listening | `recording` | Listening |
| Processing | `busy` | Processing |
| Error | `error` presentation override | Needs attention |

Specific error headlines take precedence over the generic label: for example,
“Microphone unavailable,” “Speech model unavailable,” or “Couldn't insert text.”
Loading and transcribing are useful Processing details. “Installed” means required
files are present; it must not be relabeled “Ready” until model loading succeeds.

Use **speech model** in ordinary UI. Reserve engine/backend names, file paths, and
checksums for details and diagnostics. Use **on-device processing**, **works
offline after the speech model is installed**, and **no account required**. Do
not claim the desktop app never uses the network because explicit model downloads
are supported.

## Delivery sequence

The lettered milestones retain the product brief's order. A later milestone may
be researched in parallel, but user-visible implementation should remain in
small reviewable slices with its own acceptance evidence.

| Milestone | Deliverable | Current status and gate |
| --- | --- | --- |
| A | Desktop baseline | Primary Settings/state and native indicator captures are inspected. Guarded file/decoder/review, backup, artwork, diagnostic-report, Settings-save, check-dispatch and model-management before/after sets are recorded. Remaining auxiliary/native dialogs and physical acceptance stay open. |
| B | Desktop design tokens | Existing shared palette, type roles, spacing, and radius philosophy documented in the interface guide. Values are retained; shared artwork and pill labels now use Listening and speech-model terminology. |
| C | Application shell | First source slice implements a scale-aware readable content width and retains the five destinations. Further hierarchy and progressive disclosure remain. |
| D | Home/status surface | Dictation and Help name the matching loaded model for applied settings in one last-checked runtime snapshot, separate from the selected draft and local files. Custom paths remain private; Ready needs successful matching proof. Compact actions stack without changing navigation. Physical microphone availability and active-take identity remain separate. |
| E | State communication | Fixed, text-free snapshots preserve active capture/processing and failures across model warmup/reload. Loading/failure returns after brief result feedback. Stale/quit callbacks cannot publish. Shared artwork and indicator labels align Listening/model-failure/shared-attention terminology; wider tray controls remain open. |
| F | Device management | Settings refresh/test feedback is serialized; input changes invalidate old check results and enumeration failures offer retry and optional Details. Worker-start failures restore controls without probing or recording; failed background checks no longer abandon Settings construction. Cached capture now revalidates a within-process numeric route between explicit takes, including OS-default and same-name route changes; named duplicates/missing devices fail closed. Persistent native identity, rename continuity, monitoring and physical failure acceptance remain. |
| G | Model management | Canonical names and factual language support appear in summaries/download feedback. An explicitly refreshed inventory lists guided installations, measured setup-file sizes and compatible draft-only selection; download dispatch/confirmation/stale callbacks recover safely. Cached Model details keeps identifiers/paths optional. Runtime load proof is separate from inventory; neither identifies an active take. No download-size or reclaimable-space claim. Removal/Update is gated on trusted immutable revisions/hashes, managed-path defenses, shared leases, active-take unload acknowledgement and quarantine/rollback; it must not be improvised from file presence. |
| H | Settings | The Recording feedback section now has one explicitly scoped reset for indicator, live preview and sounds; real isolated-storage tests preserve unrelated drafts, global reset semantics and saved data. Broader regrouping still requires a persistence/reset migration contract. |
| I | Keyboard shortcuts | Window-local page navigation, F1 Help, Page Up/Down/Home/End and Ctrl+F/Command+F Settings search accompany Save/Close/focus movement. Static search covers all 21 preferences and five destinations without indexing private values. Native editing keys remain untouched; broader platform shortcut validation remains. |
| J | Tray | Current tray keeps status, Settings, two-minute recovery, indicator, secondary Tools and Quit. Tray start/stop and microphone switching remain gated: clicking the tray changes focus, so paste-target ownership and per-platform menu/keyboard behavior need an explicit contract before those controls are safe. |
| K | Notifications | Routine states remain in-app. No notification was added without measured need; user-requested model completion, critical device failure and required action still need per-platform permission/lifetime and duplicate-suppression acceptance before becoming first-class notifications. |
| L | Errors/recovery | Device-list, model-download, file transcription/export, decoder setup, artwork export and diagnostics/report export failures lead with impact/retry guidance and expose bounded local technical text only via Details. Settings-save now preserves confirmed progress separately from app notification, with safe alerts and explicit Save details; scoped verification is recorded below. Remaining failures still need convergence. |
| M | Empty states | Explain why dictation is unavailable and offer one next action for missing microphones/models. Avoid decorative art that adds no comprehension. |
| N | Window/layout | Readable widths, responsive model/sidebar layout and fixed wrapping auxiliary actions are implemented. File/decoder/review content scrolls; compact/wide round trips cover 1×/1.5×/2× Tk text scales. Physical scaling, maximized/mixed-monitor DPI and other native platforms remain open. |
| O | Accessibility | Reference-page scrolling, oversized-editor insertion/validation-line reveal, held-key repeats, and read-only report Tab traversal have source coverage. An intermittent Tcl Tab-command failure is recorded, not waived by later green runs. Names, dialogs, screen readers, physical scaling and Windows UI Automation acceptance remain open. |
| P | Performance | A bounded real-Tk Settings-only baseline/candidate comparison records construction, 12-second idle CPU and memory on named Windows hardware. Full application startup, tray overhead, sustained use and recognition latency remain unmeasured gates; no full performance clearance is claimed. |
| Q | Framework decision | Consider a migration only after the current toolkit fails a measured accessibility, DPI, integration, maintenance, or required-interaction gate. Reuse the speech-service boundary. |
| R | Mobile/desktop convergence | Align terminology, semantic colors/icons, privacy/error/model/help language. Keep navigation, density, layout, input, and system integration platform-native. |

## Remaining release gates after source gauntlets

The bounded source work above is complete without a framework rewrite. These
items are intentionally not converted into speculative code:

- **Model Remove/Update:** first obtain and independently review immutable
  publisher revisions and SHA-256 values for every guided model. A later
  destructive contract must add exact managed-root/no-link checks, shared
  setup/removal and runtime leases, active-take unload acknowledgement,
  same-filesystem quarantine/rollback, cancellation and shared-cache exclusion.
- **Native device identity:** current numeric route keys are within-process only.
  Persistent endpoint identity, rename continuity, USB/Bluetooth unplug/reconnect,
  OS-default notifications, sleep/wake and driver behavior require native API
  design plus physical hardware acceptance on each supported platform.
- **Accessibility and display:** screen-reader names/roles, native dialogs,
  Windows UI Automation, keyboard focus under real assistive technology,
  maximized/mixed-monitor DPI and OS text scaling require physical/native runs;
  Tk source and screenshot checks are not certification.
- **Whole-product performance:** measure cold app startup, tray idle CPU/memory,
  sustained use and recognition latency on release hardware. The Settings-only
  sample cannot clear these gates.
- **Tray/notifications:** start/stop from a tray must not paste into a target lost
  when the menu took focus. Notification permission, lifetime, suppression and
  recovery behavior need platform contracts and user-value evidence.
- **Release:** packaging, signed binaries, package doctor, multi-OS CI and manual
  device/accessibility acceptance remain release activities. The managed host's
  Windows OBS native-pipe/private-DACL tests are currently blocked by sandbox
  timing/ACL semantics; security checks are not weakened to manufacture a pass.

## Milestone A acceptance

- A deterministic capture command records all five primary pages at the standard
  window size and Dictation at compact and wide sizes.
- Presentation-only captures cover no microphone, missing selected microphone,
  opening/listening/low-input/success/error feedback, model
  missing/incomplete/downloading/cancelled/installed/error, unsaved/saving/partial
  save/invalid input, and tray app running/not running.
- Native Windows indicator captures cover Loading, Listening, Processing, and a
  recovery-oriented microphone error. Ready remains a hidden-pill state and is
  represented by the tray artwork, not a fabricated idle overlay.
- The capture path opens no microphone, performs no model/network operation, and
  writes no user preference. Output stays under ignored `artifacts/`.
- The baseline document identifies absent surfaces and unverified physical-device,
  screen-reader, DPI, performance, and installed-build behavior.
- Existing Settings, config, theme, brand, and indicator tests pass.

## Acceptance for the full modernization

- Major desktop screens use one visual and language system; navigation remains
  predictable and state is understandable without logs.
- Device and model failures identify impact and a safe next action.
- Common Settings are scannable, advanced controls recede, and save/reset
  behavior remains repeatable.
- Keyboard and screen-reader paths, focus, contrast, scaling, dialogs, and error
  states pass the documented accessibility matrix.
- Named performance measurements show no material startup, idle, tray, or
  recognition regression.
- Current dictation, recovery, privacy, and delivery behavior survives.
- Any framework change includes the evidence and prototype that passed Gate Q.

## Verification

Activate the shared desktop Python environment, then run the smallest applicable
set from the owning desktop worktree. Keep its import root on this checkout:

```powershell
$py = (Get-Command python).Source
$env:PYTHONPATH = (Get-Location).Path
& $py -m pytest tests/test_settings_ui.py tests/test_config.py tests/test_theme.py tests/test_brand_assets.py tests/test_indicator.py -q
& $py tests/capture_settings.py
& $py tests/capture_indicator.py
& $py tests/capture_settings.py --output artifacts/screenshots/desktop-candidate
git diff --check
```

The native indicator capture is Windows-only. When preference, privacy, or
repository boundaries change, also run:

```powershell
& $py -m pytest tests/test_settings.py tests/test_settings_instance.py tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py -q
```

Run the full desktop suite only when an integration change can affect broader
behavior. Packaging, live microphones, external editors, and physical display
checks use their own acceptance gates.

## Non-goals

- A framework rewrite, web shell, remote fonts, or animation runtime.
- A chat, account, team workspace, engagement dashboard, recording library, or
  passive background assistant.
- Automatic cloud recognition or an unreviewed model/provider catalogue.
- Visual parity with the Android keyboard.
- Treating mocked screenshots as functional or accessibility acceptance.
- Reworking OBS, Android, the speech pipeline, or delivery internals as part of
  desktop visual polish.

## Stop

The baseline review found and corrected mixed scenario state, abbreviated copy,
and loss of the indicator's compact/expanded regression checks. The corrected
39 Settings captures and eight indicator captures ran on September 26; the
indicator passed three creation/update/shutdown cycles. The Settings harness
regression checks passed (3 tests). Modal-dialog, auxiliary-window, physical
device, and accessibility coverage remains open.

### Completed source slice: landing information and shell

Area: `utterleaf/settings_ui.py`, focused Settings tests,
and desktop docs. Keep app/capture/IPC/configuration schemas unchanged.

Acceptance:

- Dictation shows the last app-presence check with an explicit Refresh action
  and selected speech-model installation information with a management action.
- App presence never claims engine readiness. Model files being installed never
  claims a successful load. A selected model may be an unsaved form selection.
- Checks run once when Settings opens or when requested, with no added periodic
  work. A failed check gives an actionable status and preserves all form edits.
- Wide pages have a scale-aware maximum readable width. Compact pages keep
  scroll access and the persistent Save/Close footer.
- Keyboard navigation uses window-local shortcuts, has a Help reference, and
  preserves unsaved edits. Existing Save, Close, and focus movement survive.
- Focused UI tests cover those behaviors and the corrected capture suite runs
  with the new shell into a separate candidate artifact directory.

Stop this slice after implementation, focused regression checks, visual review,
and independent review. Live operational state needs a separately tested status
contract; model/device lifecycle changes and remaining milestones keep their
individual acceptance gates.

### Completed source slice: microphone and model recovery

Goal: failures explain the affected operation and next action without leading
with raw technical output. A passed audio check must not imply model readiness.

Area: `utterleaf/settings_ui.py`, its focused tests, the deterministic Settings
capture harness, and desktop documentation.

Constraints: preserve explicit microphone testing and one-time model-download
consent, cancellation, local preferences, named-input selection, and existing
audio/download workers. No background device monitoring, silent fallback,
automatic retry, new dependencies, or changes to runtime capture/IPC schemas.

Acceptance:

- Device-list and model-download failures show useful safe copy; technical
  details are available only through an explicit Details action.
- Retry clears obsolete details; failure preserves unsaved edits and selection.
- Settings device refresh and microphone testing cannot overwrite each other's
  feedback; Stop remains available during a test.
- A successful microphone test reports audio detection, not dictation readiness.
- Focused tests cover error/retry/cancellation, operation overlap, stale
  selection, and close handling without opening real audio or downloading files.
- Captures show primary recovery copy without invoking native technical dialogs.

Verification: run `python tests/capture_settings.py --output
artifacts/screenshots/desktop-candidate`, then `python -m pytest
tests/test_settings_ui.py tests/test_capture_settings.py tests/test_model_setup.py
tests/test_audio.py -o addopts='' -p no:cacheprovider -q` and `git diff --check`.

Non-goals: a full model catalogue, model removal, hotplug monitoring, new native
device identity, live readiness, framework changes, and release packaging.
Stop after focused regression checks, visual inspection, and independent review.
Physical devices, screen readers, macOS/Linux UI, and performance keep their
separate acceptance gates.

Known limit: device enumeration runs in a worker but the underlying native
`query_devices()` call has no timeout. Refresh and Test wait for it to return;
the rest of Settings remains usable. This slice does not introduce detached
retry workers or claim bounded native enumeration.

### Completed source slice: last-reported operational status

Goal: Settings can report the app's last published Idle, Listening, Processing,
or Needs attention presentation instead of only process presence.

Area: `utterleaf/app.py`, `settings_ui.py`, a small shared status-message module,
focused app/IPC/Settings tests and captures, and desktop docs.

Constraints and contract:

- Add a read-only authenticated `status` command; preserve `ping` and all control
  commands and their existing authentication. Do not alter transport, port files,
  tokens, recording, engine loading, delivery, or preference schemas.
- Cache one fixed versioned token when the app publishes its existing tray
  presentation, after loading/error overrides. Do not infer Listening from the
  internal recording flag, which is set before the microphone opens.
- Expose only `status-v1:idle`, `status-v1:listening`, `status-v1:processing`,
  `status-v1:attention`, or `status-v1:unknown`. Never expose raw tray captions,
  dictated text, field/app names, paths, microphone names, or preferences.
- Settings uses an exact allowlist and fixed local copy. Unsupported older-app
  replies retain a presence-only message; unauthenticated legacy endpoints require
  restart. Malformed replies are not displayed as text or treated as readiness.
- Query only once on opening or explicit Refresh. Keep the last-check label,
  draft preservation, overlap guard, and closed-window guard; add no polling.
- This is last-published presentation, not an atomic capture/engine readiness
  snapshot. Idle must not be called Ready. A full live readiness contract remains
  a separate milestone.

Acceptance: state-transition tests cover loading/listening/processing/error/idle;
an authenticated loopback test rejects unauthenticated status requests; the reply
contains no private sentinels; queries trigger no capture/model/file/worker work;
client tests cover compatibility/malformed replies and preserved drafts; captures
cover each new visible state.

Verification: `python tests/capture_settings.py --output
artifacts/screenshots/desktop-candidate`; focused pytest for status, app, IPC,
Settings, capture, privacy/config/boundaries; then `git diff --check`. Because
the app's shared status publisher is touched, run the full desktop pytest suite
after the focused checks. Packaging and physical device checks remain separate.

Non-goals: a live subscription, new timers, actual Ready proof, tray redesign,
capture state-machine rewrite, detailed device/model status, or release work.
Stop after focused/full checks, visual inspection, and independent review.

### Completed source slice: keyboard page scrolling

Goal: keyboard users can read all of a long reference page, including Voice
commands, without a mouse. Its labels do not participate in focus traversal,
and the current ttk scrollbar has no page-key bindings.

Area: `utterleaf/settings_ui.py`, focused Settings tests, and desktop guides.

Constraints: preserve native text editing, picker/slider keys, focus, unsaved
drafts, Save/Close, and existing navigation. Bind only within the Settings
window; do not intercept modified key combinations, add global shortcuts,
change settings schemas, invoke actions, or add background work.

Acceptance: Page Up/Down scroll the active page from navigation and ordinary
buttons; Home/End reach its limits. Text fields and key-consuming controls keep
their native behavior. Real Tk events cover compact reference pages at ordinary
and larger text scales, focus/draft preservation, and bounds. Help documents the
keys. Explicit scrolling must survive a pending page-opening idle reset; rejected
keys must leave it intact. Existing focus, picker, navigation, and save/reset
checks still pass.

Verification: `python tests/capture_settings.py --output
artifacts/screenshots/desktop-candidate`, then `python -m pytest
tests/test_settings_ui.py tests/test_capture_settings.py tests/test_settings.py
tests/test_settings_instance.py -o addopts='' -p no:cacheprovider -q`, with
`PYTHONPATH` scoped to this checkout; `git diff --check` and independent review.

Non-goals: screen-reader certification, oversized text-editor caret reveal,
framework migration, runtime readiness, or physical display acceptance. Stop
after the bounded checks, capture inspection, and review pass. The separate
oversized-editor focus issue remains follow-up work.

### Completed source slice: oversized-editor keyboard access

Goal: focus, vocabulary validation, and keyboard cursor movement keep the
relevant line visible even when a text editor is taller than the page viewport.
The read-only device report must be reachable by keyboard without becoming
editable.

Area: `utterleaf/settings_ui.py`, focused Tk tests, desktop guides/captures.

Constraints: preserve native editing, selection, drafts, and ordinary focus
reveal for controls that fit. No global key collection, background caret checks,
new timers, preference writes, audio, models, or framework change. Use existing
focus handling plus local input events; read-only output remains read-only.

Acceptance: first and later invalid vocabulary lines are visible after focus;
cursor movement inside oversized editors remains visible at compact
1×/1.5×/2× text scales; repeated focus does not oscillate; events after focus
leaves or Settings closes do nothing. Tab reaches and exits the device report.
Existing click/picker, scrolling, Save/Close/reset, and native key tests pass.

Verification: scoped `PYTHONPATH`; `python -m pytest tests/test_settings_ui.py
-k 'oversized or diagnostic_report_keyboard' -o addopts='' -p no:cacheprovider
-q`; capture Settings; then the four-file Settings regression listed above and
independent review. Record any broader regression justified by shared changes.

Non-goals: screen-reader certification, physical DPI, or a new text editor.
Stop after source checks and visual review pass; retain external gates.

### Completed source slice: consistent model presentation

Goal: selected-model information uses one human-readable name and factual purpose
throughout Settings, with technical identifiers, backend, expected path, and
missing files available through explicit Model details.

Area: a pure `utterleaf/model_presentation.py` helper, Settings model UI,
presentation/Settings tests, capture scenarios, and desktop guides.

Constraints: retain existing identifiers, editable custom-model entry, selection,
local file inspection, download consent, cancellation, attempted-model identity,
and persistence. Do not add network access, model loading, directory scanning,
deletion, estimates, performance recommendations, or a new model catalogue.
Installed files still do not prove readiness; technical/error details stay
separate and explicitly requested.

Acceptance: known names and English-only/multilingual purpose are consistent;
unknown/custom identifiers never leak into the primary summary; details refer to
the selected draft. Choosing and inspecting do not save/download/load anything.
Download messages retain the attempted model when selection changes. Existing
save/cancel/reset and explicit one-time consent remain covered.
Compact model pickers and download actions must retain their requested widths
at 1×/1.5×/2× text scales, stacking when horizontal space is insufficient;
resizing must preserve drafts, focus order, and access to the fixed footer.

Verification: pure presentation tests, focused Settings/model-setup/capture tests,
all model-state captures plus compact/text-scale checks, and independent review.
Non-goals: removal/update lifecycle, precise size catalogue, active-engine proof,
or silently changing raw custom identifiers. Stop at bounded source acceptance.

## Gauntlets through completion

### Completed source slice: Settings search

Goal: find an existing setting by its user-facing name without remembering its
page, changing the five primary destinations or exposing a larger default form.

Area: Settings' local control metadata, search presentation/navigation and
focused tests/captures. Inspect the existing widget/focus registry before
choosing an implementation; `fields` alone is not the complete control index.

Constraints: index static labels/help terms, never private field values,
vocabulary contents, transcripts, device inventory or model paths. No new
network/model/audio work, polling, dependency, preference or persistence schema.
Search navigation preserves drafts and validation behavior. Retain native
editing keys, Save/Close, page shortcuts and the fixed navigation hierarchy.

Acceptance: a discoverable local search with Ctrl+F (Command+F on macOS), useful
empty/no-match feedback, keyboard result selection and focus on the matching
visible control. Escape dismisses search without closing Settings or discarding
edits; search dismissal/selection has an explicit focus destination. Results
cover all existing user-facing settings and primary-page reference destinations.
Compact and large text layouts preserve readable results and reachable actions.

Read-only audit: the UI constructs 21 preference concepts across Dictation,
Vocabulary and Speech & privacy; `fields` contains only nine. Register static
search metadata alongside control creation, using page/section ancestry rather
than another duplicated label catalogue. Help and Voice commands remain stable
reference destinations. The query belongs outside `vars` and `_snapshot()`.
After navigating, cancel the queued `_page_reset` before focus reveal. Disabled
dependent settings should explain their prerequisite and focus its enabling
control without toggling it. Wayland-disabled shortcuts need informative
fallback. Actual key-event tests must check binding order so Ctrl+F does not
first move an editor caret; search-list scrolling must not also scroll the page.

Verification: pure matching/index checks, real-Tk shortcut/focus/draft/close and
no-side-effect tests, guarded captures and independent review. Retain the
separate screen-reader/platform gate. Non-goals: changing primary destinations,
full-app command search, section resets, new settings or a toolkit migration.
Stop after those bounded checks, with remaining A–R work still active.

Implementation: 21 preference concepts and five page destinations register their
static labels/sections alongside existing controls. Find setting and local
Ctrl+F/Command+F open the same pane; it temporarily replaces the content canvas,
not the sidebar or Save/Close footer. Arrow keys select results, Enter reveals
the existing control, and Escape/Back clear the ephemeral query and restore
focus. Disabled dependent results explain and focus their prerequisite without
changing it. Search adds no preference, worker, global input hook or polling.

The first real-key/layout run reported 26 passed and four failed: two Escape
focus regressions, a collapsed 2× results list, and a test-fixture geometry
manager conflict. A guarded probe confirmed canvas descendants report unmapped
inside the dismissal callback and remap afterward; that temporary state no
longer discards valid editor focus. Hiding the redundant launcher while search
is open and shortening the result count restores result space. The fixture now
uses the root's compatible geometry manager. All 30 search cases then passed,
including all 26 destinations with a complete result row, full selected detail
and contained actions at compact 1×/1.5×/2×. Independent review confirmed native
sidebar-click focus, editor/caret restoration and binding cleanup, and found one
missing static alternate label: Tray icon only. The index now takes that term
from the existing radio control, with two added regression queries. Singular
result-count grammar is also corrected. No blocking privacy or workflow finding
remains; final-source search/capture verification is complete.

With scoped `PYTHONPATH`, the combined regression command
`python -m pytest tests/test_settings_search.py tests/test_settings_ui.py tests/test_capture_settings.py tests/test_settings.py tests/test_settings_instance.py tests/test_model_presentation_ui.py tests/test_sidebar_layout.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`
passed **181 tests in 139.54 seconds, no skips**. This includes persistence,
cancellation, defaults, keyboard, model layout and capture safety. That run
preceded only the final alternate-label addition and its two query cases; the
separate final-source search/capture receipt follows below.

- `python -m pytest tests/test_settings_search.py tests/test_capture_settings.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **37 passed in 51.82 seconds, no skips** after the alternate-label correction.
- `python tests/capture_settings.py --output artifacts/screenshots/desktop-search-final`:
  **55 images completed**. Six new search states cover empty, results, no match,
  prerequisite guidance and compact 2× results/prerequisites. Reviewed the new
  states, ordinary compact Dictation and Help; all selected detail/action copy
  remains readable. The earlier candidate is retained separately.
- Independent review is clear after the alternate-label fix. No framework,
  preference schema, microphone/model operation or personal-data write changed.
  Native macOS/Linux key delivery, physical DPI and screen-reader/UIA acceptance
  remain open; this source slice does not complete the overall A–R plan.

### Completed source slice: backup preview keyboard and layout

Goal: retain the existing explicit backup review workflow while making its
preview escapable in both Tab directions and its controls usable at minimum
window size with enlarged text.

Area: `backup_ui.py`, focused backup UI/layout tests, guarded captures and docs.
Constraints: no backup-format/storage/import changes, no automatic selection or
confirmation, no overwrite permission change, no personal-preference access in
captures, no OBS/artwork source changes in this slice. Preserve reviewed-import
staleness checks and privacy exclusions. Reuse existing native layout helpers.

Before-state evidence: source review identifies disabled Text consuming native
Shift+Tab, while old tests call `tk_focusNext()` rather than dispatching a key.
The current two-column preferences and horizontal vocabulary/footer rows require
compact baseline measurement; do not claim clipping until it is reproduced.

Acceptance: record synthetic export/import/preview-failure baseline before layout
edits; actual Tab/Shift+Tab; full natural action bounds and reachable choices at
480×460 and baseline×1/1.5/2 text scales, including compact→wide→compact. Preserve
selections, preview/review and no-write cancellation. Existing backup behavior
tests and independent review must pass. Native picker/confirmation internals,
physical DPI, screen readers and other platforms remain separate gates.

Verification: guarded before/after screenshots; focused backup/layout and harness
tests with `--capture=sys`; existing backup/core persistence checks only where
the change can affect them; `git diff --check`. Stop after those bounded checks.
Artwork keyboard/recovery and the broader device/model/performance work remain
subsequent separately scoped work.

The before-state is secured as eight images and a source-hashed manifest in
`artifacts/screenshots/desktop-backup-before-20260926`. At compact 2×, Apply
requests 364 pixels but receives 229; Save requests 287 but receives 229. The
second choice column reaches x=602 in a roughly 465-pixel viewport, and the
vocabulary checkbox requests 502 pixels. Both compact import/export images were
inspected. The new real-key/round-trip regression first reported **9 passed,
8 failed**: five natural action-width failures and three trapped Shift+Tab cases.

The production delta reuses `ActionRow`, `wrapped_label` and `readonly_preview`
for responsive choices/vocabulary/actions, fully wrapped copy and explicit
preview traversal. The vocabulary checkbox keeps its existing comments exclusion
in a two-line caption, revealed together with the control. No backup format, storage, preview
calculation, confirmation, staleness or overwrite logic changed.

`python -m pytest tests/test_backup_layout.py tests/test_backup_ui.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`
passed **27 tests in 12.01 seconds, no skips**. This covers all choice bounds,
natural button sizes, minimum viewports, real keys, read-only text/selection,
compact→wide→compact stability, cancellation and existing import/export safety.
The capture harness then passed **12 tests without skips**, including synthetic
read boundaries, rejected writes/native actions, output preservation, incomplete
manifests and native input interception before mapping. Eight candidate images
completed with all action/choice bounds passing; those candidate artifacts are
retained at `desktop-backup-final-20260926` despite the historical directory name.

Independent review found two further issues not covered by natural control
bounds: a separate comments-exclusion hint fell below the viewport when its
checkbox received focus, and ancestor FocusIn moved an already-visible checkbox
40 pixels during its first mouse press. The disclosure is now inside the
two-line checkbox caption; focus reveal ignores ancestor containers and accepts
only actual option controls. Re-review finds no residual source defect.

- Final-source command: `python -m pytest tests/test_backup_layout.py tests/test_capture_backup.py tests/test_backup_ui.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **41 passed, no skips**. New 2× export/import mouse cases center the first
  checkbox 40 pixels inside the viewport, verify unchanged scroll/position during
  press, then release at the original screen point and confirm exactly one
  intended toggle with no writes or unrelated selection changes.
- `python tests/capture_backup.py --output artifacts/screenshots/desktop-backup-reviewed-20260926`:
  **eight reviewed images completed**. All action/choice bounds and five source
  hashes, harness hash and shared capture-helper hash match. Root and independent
  reviewer inspected the compact 2× disclosure/action results. The before-state
  and earlier candidate remain separate; neither was overwritten.
- Independent final review is clear. `git diff --check` passes. Backup format,
  storage, consent, overwrite and reviewed-import staleness remain unchanged.
  No actual backup or personal-preference file was read/written by the captures.
  Native dialogs, screen readers, physical DPI and other platforms remain open.

### Completed source slice: artwork reference keyboard and recovery

Goal: make the full existing Icons & artwork reference keyboard-readable and
give an actionable export failure with optional bounded technical details.
Area: `appearance.py`, dedicated guarded baseline/captures and focused tests.
Audit evidence: notebook traversal changes tabs but does not scroll their
label-only contents; the native scrollbar has no page-key binding. Before this
slice, export errors displayed raw exception text in an automatic modal dialog.

Constraints: preserve asset generation, export consent, worker/close lifecycle,
the five reference tabs, native Tk and all packaged artwork. No new preference,
OBS work, storage format or generic framework. Reuse existing layout/recovery
helpers only where baseline evidence calls for them.

Acceptance: record normal/compact/enlarged reference and failure states first;
actual local Page Up/Down/Home/End without hijacking notebook/native keys; whole
actions and readable content at the existing 720×540 minimum with baseline×1,
1.5 and 2 text scales. Export failure should explain impact/retry, keep raw text
behind explicit Details, and retain close/retry safety. Capture must block real
exports, dialogs, personal values, audio, clipboard and network work.

Verification: exact-key/layout/recovery/guard tests, retained before/after
captures, existing artwork inventory/export tests, independent review and diff
check. Stop at those scoped checks. Native dialogs, assistive technology,
physical displays and other platforms require separate acceptance evidence.

Before-state evidence: nine guarded captures and source hashes are retained in
`artifacts/screenshots/desktop-artwork-before-20260926`. At compact 720×540 and
2× Tk text scaling, Export and Close are unmapped (1×1 geometry), and full tab
labels are truncated. The native failure modal is intercepted, not certified.
Two before-source UI test runs stalled inside Tk update at 1.5× layout; only
their verified test processes were terminated. A separate 1× page-key case
failed. These are not a completed red-suite count; the precise hang cause is
unproven. Fixed-width wrapping removes the old natural-width feedback path,
and the subsequent three-scale roundtrip completes without a hang.

The source keeps the five tab identities/order but gives the first three stable
concise labels, uses wrapped row text and a fixed wrapping action footer, and
adds local page keys. Export failures and progress use the existing recovery
helper; picker/thread-start failures remain retryable, cancellation retains a
previous error, and close cancels only UI polling. Asset generation and atomic
archive replacement are unchanged. The first candidate passed 19 focused cases
and produced nine captures; review found its compact 2× error viewport too
shallow, so the intro/recovery copy was shortened and the viewport assertion
strengthened. Review also corrected an inaccurate incomplete-pack warning to
"Export did not finish." Final-source verification follows below.

- The strengthened recovery check then found **20 passed, one failed**: compact
  2× error content had 83 pixels, below the 100-pixel reference viewport floor.
  Reduced outer padding reclaimed 20 pixels without shrinking text/actions or
  weakening the assertion.
- `python -m pytest tests/test_appearance_ui.py tests/test_capture_appearance.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **21 passed in 27.08 seconds, no skips**. Coverage includes all five tabs and
  compact→wide→compact at three scales; actual page/native editor/notebook keys;
  safe bounded Details, retry, duplicate export, cancelled retry preserving the
  error, picker/thread-start failure, repeated close and late callbacks.
- `python -m pytest tests/test_brand_assets.py tests/test_settings_ui.py -k 'brand or appearance' --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **six passed, 99 deselected in 5.03 seconds**. Existing asset catalogue,
  atomic export preservation and Settings guide reuse remain covered. This run
  preceded only the final copy/padding adjustment, covered by the 21-case run.
- `python tests/capture_appearance.py --output artifacts/screenshots/desktop-artwork-reviewed-20260926`:
  **nine reviewed images completed**. All mapped action, row-text width and tab
  label bounds pass; all six source, two helper and harness hashes match. Root
  inspected compact 2× normal and export-failure Wordmark states. Failure retains
  a 661×103-pixel reference viewport with full recovery/Details/Export/Close;
  ordinary reference content has a larger viewport. No native modal was opened.
  Before-state and first candidate remain separate, neither overwritten.
- `python tests/capture_settings.py --output artifacts/screenshots/desktop-artwork-settings-20260926`:
  **55 images completed**, refreshing all five integrated guide views. Final
  artwork hashes still match after the Settings capture. Independent source,
  test, documentation and visual review is clear. Native dialogs, physical
  devices/displays and assistive-technology acceptance remain separate gates.

### Completed source slice: diagnostic report recovery

Goal: report checks and explicit report export fail safely with actionable copy,
preserving the last successful locally reviewed report and unsaved settings.
Area: `SettingsWindow._help`, `diagnostics`, `cuda_setup`, `export_report` and
focused Settings/capture tests. Root retains sole ownership of `settings_ui.py`.

Audit: diagnostic and GPU guidance checks share one report but currently launch
independently. Each completion replaces its preview; failure erases exportable
content and displays a raw exception. Callbacks lack closed/stale guards and
thread-start failure leaves controls disabled. Export's picker is outside its
error handler; direct `Path.write_text` may truncate a destination on failure.
A native picker event loop may also accept a newer report callback before the
chosen report is written. These are source findings, not live-device evidence.

Constraints: retain explicit checks and report review/share consent; diagnostics
uses saved configuration, not an unsaved draft. Do not change hardware probing,
model/network permissions, report schema or data collection. No automatic
upload, clipboard mutation, dependency, preference or architecture change.
Keep existing native picker/overwrite consent and distinguish primary recovery
from potentially private technical names/paths in explicit Details.

Acceptance: one shared in-flight report check; reject overlap and restore
controls on worker-start failure. Closed/stale callbacks do nothing. A failed
check retains previous report text/selection and says so, or explains that no
report is available. Retry clears stale Details; success remains read-only.
Report export snapshots the reviewed content before opening its picker,
handles picker/write failures without raw automatic modals, preserves cancellation
and prevents writes after close. If direct writing is retained, do not promise
that a failed destination is untouched. Recovery and Details must be fully
readable/reachable at compact 1×/1.5×/2× text sizes without moving focus or losing
drafts. Other-page completion must not jump navigation.

Verification: guarded before/after synthetic captures; focused report lifecycle,
export, privacy/draft and real-Tk layout/keyboard tests; existing Settings,
hardware-report and capture tests; independent review and `git diff --check`.
Use explicit pytest `--capture=sys`. No real probes, report exports or personal
preferences in capture/test fixtures. Stop after those scoped checks; native
dialogs, physical hardware, assistive technology and other platforms remain
separate. Non-goals: redesigning device enumeration, GPU setup, atomic report
storage or the global Settings worker/save machinery.

Before-state: nine guarded images and source hashes are retained in
`artifacts/screenshots/desktop-diagnostics-before-20260926`. Actual report/export
methods run against held worker targets and synthetic probe results. Device/GPU
failures erase previous reports and show raw synthetic exception text; picker
failure escapes its handler, while write failure opens an intercepted raw-error
modal. No live probe, export, personal preference or native modal occurred.
The baseline Settings hash is
`f61b76c2f0e0c523474f86b8e7f2c07291aff9e1fb6ddd8a40e4d7c393c8476b`.

Implementation uses a local identity-checked report operation and a separate
reentrant-export guard, without changing the shared worker or hardware module.
Both check buttons are disabled during a check; an existing report remains
exportable. Failure retains the preview/selection, and recovery uses the shared
bounded Details helper. A local geometry reveal shows the complete feedback
only on its mapped page; Details focus uses that same reveal. Export snapshots
before the native picker and checks close before writing. Direct-write failure
copy explicitly warns that the chosen file may be incomplete. Review caught an additional native-picker
edge: a newer report can replace the preview while the earlier snapshot is being
saved. Success/failure copy now identifies the earlier report and the newer
preview rather than implying they are the same. No extra report cache or stale
preview restoration was added.

- Initial independent test run: 30 passed, two exact-copy expectation failures
  and four temporary-directory setup errors. The expectations now match the
  equivalent implemented no-report wording; no product behavior was weakened.
- Root's combined `python -m pytest tests/test_diagnostic_report_ui.py tests/test_capture_diagnostics.py --capture=sys -o addopts='' -o faulthandler_timeout=30 -p no:cacheprovider -q --tb=short`:
  **37 passed in 16.53 seconds, no skips**. This precedes the extended
  three-scale GPU/write and pointer-regression checks below.
- `python -m pytest tests/test_hardware.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **23 passed in 0.09 seconds**. Hardware report content/generation source is
  unchanged; no full-suite or packaging rerun is required for this UI slice.
- Independent review requested a precise Details mouse check: with the button
  already visible near the viewport top but the preceding error text clipped,
  its FocusIn reveal moved it during Button-1 and the original release missed.
  The new test reproduced **one failure, 35 deselected in 1.35 seconds**. A local
  native `pressed`-state guard now leaves the pointer target stationary while
  preserving full keyboard reveal and ordinary offscreen-control handling.
- Final focused command (same combined modules and flags above): **48 passed in
  24.47 seconds, no skips**. The expanded matrix covers device, GPU, write and
  earlier-report write errors at all three text scales; complete feedback/Details,
  actual first-click stability, and both successful/failed snapshot exports are
  asserted. No GUI assertion was relaxed to obtain the result.
- `python tests/capture_diagnostics.py --output artifacts/screenshots/desktop-diagnostics-reviewed-20260926`:
  **nine images completed**. Root and independent reviewer inspected both compact
  2× errors. Full error labels/Details fit the actual canvas viewport at natural
  dimensions, fixed footer controls fit, previous reports are retained where
  applicable, and primary copy excludes the raw synthetic error. No intercepted
  modal or uncaught exception remains. All five source, three helper and harness
  hashes match; Settings source is
  `84d7fecb4db0e8d585e0e8c71c536fb82e9f44349d94eb08e6b337b2bfa031e9`.
  Capture alignment is explicitly synthetic; automatic reveal is proven only by
  the separate real-Tk tests. Independent source/test/visual review is clear.
- `python tests/capture_settings.py --output artifacts/screenshots/desktop-diagnostics-settings-20260926`:
  **55 images completed**. Post-capture source/helper/harness checks still match,
  and all Tk scaling receipts restore their starting value. This is the latest
  Settings integration capture set; older sets retain their original scope.
- Final-source Settings regression, checkout-scoped `PYTHONPATH`:
  `python -m pytest tests/test_settings_ui.py tests/test_settings_search.py tests/test_capture_settings.py tests/test_settings.py tests/test_settings_instance.py tests/test_model_presentation_ui.py tests/test_sidebar_layout.py tests/test_ui_feedback.py --capture=sys -o addopts='' -o faulthandler_timeout=30 -p no:cacheprovider -q --tb=short`:
  **195 passed in 131.00 seconds, no skips**. Save/reset/cancel, keyboard/search,
  model presentation, compact layouts, capture guards and shared recovery pass.
- Independent review and `git diff --check` are clear. No hardware-probe,
  preference schema, worker architecture, dependency, Android, packaging or
  publication changes occurred. The mixed recovery checkout retains only its
  pre-existing unrelated Android plan. This completes the diagnostic slice,
  not the full A–R product/release gates.

### Completed source slice: Settings-save recovery

Goal: save failures explain confirmed durable progress and recovery without
leading with raw technical errors, preserving drafts and safe repeatable saves.
Area: `settings_ui.py`, a pure `save_presentation.py` formatter, guarded save
captures/tests and desktop documentation. Root owns Settings UI and existing
integration tests; the formatter and dedicated test/capture files have separate
writers. Prior goal turn completed artwork and diagnostic recovery with source,
test and capture evidence; it was progress, not a wait or no-progress turn.

Audit evidence: `apply_form` validates before three ordered, individually atomic
operations: dictation settings, vocabulary (optional outside this UI), and start
at login. `SettingsSaveError.saved/failed/pending` records known progress, but its
string embeds the raw cause. The automatic save alert currently displays that
string. Generic exceptions do not prove nothing saved; an app-reload exception
can occur after successful writes or replace a structured partial-save error.
Worker-start failure also leaves Save and Close stuck in the saving state.

Constraints: retain storage/validation, operation order, reload attempts, save
snapshot semantics, staged defaults, privacy preferences, close/discard and
field/line focus. No configuration migration, transaction/rollback, automatic
retry, new dependency, global worker rewrite, microphone/model/clipboard/network
operation, or preferences written by captures. Preserve the native save alert,
but give it safe problem/progress/retry copy; add only an error-specific footer
"Save details…" action for bounded technical information. Ordinary footers and
navigation stay unchanged. Native dialog interiors remain a separate gate.

Acceptance:

- Only canonical structured progress is rendered as confirmed saved/failed/not
  attempted components, using fixed names. Malformed/unknown metadata stays
  uncertain and cannot inject private strings into primary feedback.
- Unknown errors do not claim rollback or no writes. A worker that never started
  can truthfully report that this attempt wrote nothing.
- A private save outcome keeps confirmed full success even if app notification
  raises, and keeps structured partial progress if its reload attempt raises.
  Do not add/remove persistence operations or retry/reorder reload attempts.
- Save tracks one operation, rejects overlap and stale/closed callbacks, and
  unlocks controls after a start failure. Success advances the captured baseline;
  later edits remain dirty. Failure preserves draft, baseline and staged reset.
- Raw causes/paths appear only on explicit Save details, bounded with the existing
  technical-details helper. Retry, new edits, reset and close clear obsolete
  details; hiding a focused Details action leaves useful visible focus.
- Native validation messages still route to the correct field/line. The new
  recovery alert must not steal that focus path or change validation/save order.
- At compact 1×/1.5×/2× text scaling, status, Save details, Save, Close and all five
  destinations remain fully reachable, with actual keyboard/pointer checks and
  compact→wide→compact preservation of drafts.

Verification: retain a guarded before set, then pure progress/privacy tests and
fake-I/O real-worker/controller tests; focused Settings/config/reset/capture
regressions with `--capture=sys`; source-matched after captures, independent
review and `git diff --check`. Native alerts are intercepted and recorded, not
visually certified. Stop after those scoped checks. Device/model lifecycle, tray
controls, notifications, whole-app performance, terminology convergence and
native/accessibility release gates remain open in the full A–R plan.

Implementation: the native save alert now uses a pure, private-data-free
presentation helper. Only exact canonical progress splits are trusted; generic
or malformed progress stays uncertain. A private `_SaveOutcome` separates local
writes from app-notification failure without changing the persistence sequence
or reload attempts. The captured baseline advances after confirmed full writes,
including when notification raises; later edits remain dirty. Failure retains
the original draft/baseline/reset. A single operation token rejects duplicate,
stale and closed completions. Worker-start failure unlocks Save/reset and explains
that this attempt made no changes. Validation retains its original alert and
field/line focus path. Optional bounded Save details clears on new intent and
does not affect ordinary footer layout.

Before evidence: `artifacts/screenshots/desktop-save-before-20260926` contains
ten guarded post-alert states at original Settings source hash
`84d7fecb4db0e8d585e0e8c71c536fb82e9f44349d94eb08e6b337b2bfa031e9`.
The real held worker with synthetic `apply_form`/IPC reproduces stuck worker-start
failure and notification errors obscuring full/partial write progress. Alerts
are intercepted, not visually certified; no personal preferences, startup,
vocabulary, device, network, clipboard or real IPC work is performed.

Independent review found a focus-order defect: retry from focused Details hid
the button and focused Save immediately before disabling it. Save is now
disabled first, so hiding Details transfers focus to enabled Close. The initial
UI run recorded **31 passed, two failed in 30.06 seconds**: that reproduced
defect and one obsolete expected footer string. Final actual Ctrl/Command+S
coverage verifies focus during retry and after clean success.

Verification receipts (owning desktop checkout and explicit `PYTHONPATH`):

- `python -m pytest tests/test_save_presentation.py --capture=sys -o addopts='' -p no:cacheprovider -q`:
  **38 passed in 0.11 seconds**, no skips. All actual three/two-stage splits,
  malformed metadata, private text, unknown/start failure and reload guidance.
- `python -m pytest tests/test_save_recovery_ui.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **34 passed in 30.41 seconds**, no skips. Real `apply_form`/held-worker/queue
  paths use synthetic sinks; all persistence stages/order, reload/start failures,
  drafts/reset/privacy, validation, overlap/staleness/close and keyboard/pointer
  cases pass. Twelve compact→wide→compact cases cover four failure states at
  1×/1.5×/2× with natural footer and sidebar-parent navigation bounds.
- `python -m pytest tests/test_capture_save_recovery.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **13 passed in 2.73 seconds**, no skips. Inventory, forbidden operations,
  native-alert interception, held worker isolation and incomplete/exclusive
  receipt preservation are covered.
- `python -m pytest tests/test_settings.py tests/test_config.py tests/test_privacy.py tests/test_repo_boundaries.py tests/test_save_presentation.py tests/test_startup.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **81 passed, one skipped in 0.57 seconds**. The existing Linux startup symlink
  test requires unavailable Windows symlink privilege (`WinError 1314`); this is
  an explicit prerequisite gap, not a pass. No persistence source changed.
- `python tests/capture_save_recovery.py --output artifacts/screenshots/desktop-save-reviewed-20260926`:
  **10 of 10** completed. Root and independent reviewer inspected both compact
  2× images. Every mapped action/status and all five parent-clipped destinations
  fit natural dimensions. All drafts remain unchanged, only full-write success
  advances the baseline, and no raw synthetic error enters primary text. No
  uncaught error or stuck saving state remains; native validation correctly has
  no Save details action. Six source/four helper/harness hashes match; scales
  restore. Final Settings source is
  `95c07bbdc738f72413437e3b429ca2bb8a8b6ba68107c4231a2333544cd86064`.
  Independent source/test/capture review is clear after the focus correction.
- Root combined integration command:
  `python -m pytest tests/test_settings_ui.py tests/test_settings_search.py tests/test_capture_settings.py tests/test_settings.py tests/test_settings_instance.py tests/test_model_presentation_ui.py tests/test_sidebar_layout.py tests/test_ui_feedback.py tests/test_save_recovery_ui.py tests/test_capture_save_recovery.py tests/test_diagnostic_report_ui.py tests/test_capture_diagnostics.py --capture=sys -o addopts='' -o faulthandler_timeout=30 -p no:cacheprovider -q --tb=short`:
  **290 passed in 192.20 seconds, no skips**. Existing Save/reset/cancel,
  navigation/search, device/model, report recovery and new save behavior pass
  together on the final source. No broad desktop suite or package build was
  required for this scoped UI/presentation change.
- `python tests/capture_settings.py --output artifacts/screenshots/desktop-save-settings-20260926`:
  **55 images completed**. Root inspected clean and partial-save views; ordinary
  footer remains unchanged and Details appears only after a failure. All six
  reviewed save-source hashes still match after integration capture. The normal
  `git diff --check` passes with this checkout's configured line-ending handling.
  The mixed checkpoint still has only its pre-existing unrelated Android plan.

This goal turn is **progress**: Settings-save source acceptance is complete,
not the full desktop modernization or native release gate. All A–R obligations
remain in the milestone table; no framework or persistence rewrite was made.

### Completed source slice: Settings check dispatch recovery

A separate read-only Aden/source/test audit identified a reproducible dispatch
gap in `SettingsWindow.refresh_mics` and `test_mic`. Both set busy flags and
disable controls before `_worker` starts its thread. If starting fails, Refresh
remains busy with Refresh/Test disabled; Test remains checking, says Stop, and
leaves the picker/Refresh disabled. A fake-control, raising-worker reproduction
confirmed both states without running enumeration or audio. Initial background
refresh also occurs during Settings construction. Current result-failure tests
replace the worker and do not cover its start failure.

Current-source revalidation also found the same unguarded dispatch in
`refresh_connection`, which runs immediately after the initial microphone
refresh. Handling only the microphone failure would still let the second check
abandon construction when threads cannot start. Include this handler so the
actual startup path, rather than a selectively mocked version, is recoverable.

Goal/area: handle dispatch failure in these three Settings handlers. Preserve
selection, drafts/baseline, readonly picker, current page/focus and the existing
overlap/Stop/input-change/close behavior. Explain that the operation could not
start rather than asserting a microphone fault; expose bounded technical text
only through existing explicit microphone Details. App-status failure keeps its
existing safe-text-only surface. Restore idle controls and allow one explicit
retry, without automatic retry, polling, new global-worker behavior or a token
redesign unsupported by a reachable stale-result race. Root owns production,
existing integration tests and docs; separate owners cover a new focused UI
test module and guarded capture/harness files. No audio, storage, configuration,
IPC, framework or dependency behavior changes. Previous goal turn was progress:
completed Settings-save source acceptance with 290 combined passing checks and
source-matched reviewed/integration captures.

Acceptance:

- Actual `Thread.start` failure restores each check's flags/controls. Both
  background startup failures can occur together without abandoning Settings;
  the window finishes construction with its ordinary poll/close behavior.
- No enumerator, Recorder or IPC query runs if its worker did not start. Failure
  copy makes no device-permission, availability or recording-success claim.
- Existing callbacks/result errors, empty/missing input handling, no silent
  fallback, explicit one-operation retry, Stop, input-change cancellation,
  closed callbacks, keyboard focus and save/reset/drafts remain intact.
- Private exceptions are absent from primary text. Microphone Details remains
  local, bounded, explicit and cleared on retry/input changes.
- Compact/wide roundtrips and 1×/1.5×/2× text scaling retain visible/reachable
  recovery, controls and stable navigation; no new focus jump is introduced.

Verification: guarded before/after dispatch-failure captures for all three
handlers at standard and compact 2× sizes; new actual held-worker/controller
tests in `tests/test_mic_dispatch_ui.py`; smallest affected microphone/status
Settings tests, followed by the Settings/search/capture/save regression modules
with `--capture=sys`. Run capture-harness guard checks and independent source,
test and image review; finish with `git diff --check`. Do not rerun unrelated
full-suite/package or every historical capture set for a local dispatch fix.
Stop this slice once those named checks pass and documentation matches source.

Non-goals: stable device identity, OS-default monitoring, a native enumeration
timeout or hotplug support. The enumerator still returns deduplicated names and
native `query_devices()` remains unbounded. Those and the remaining A–R work
continue as separate active obligations; this audit does not close milestone F.

Implementation uses each handler's existing completion path with a private
`started=False` distinction when dispatch raises. Normal result/cancellation
paths are unchanged. Failed starts restore idle flags and controls; microphone
copy states that the list was not checked or that this check recorded no audio.
App-status copy offers Refresh status without claiming app availability. Both
background failures can occur together and construction still registers its
ordinary poll and close handling. No global worker, audio, IPC or timing code
changed.

Before evidence: six states in
`artifacts/screenshots/desktop-mic-dispatch-before-framed-20260926` use the actual
three handlers with failing `Thread.start`, at standard and compact 2× sizes.
All six reproduce escaped errors and stuck busy controls on source
`95c07bbdc738f72413437e3b429ca2bb8a8b6ba68107c4231a2333544cd86064`.
The original label-only framed set remains in `desktop-mic-dispatch-before-20260926`;
the corrected set also frames the relevant retry action, without claiming
automatic scrolling. No enumeration, recording, IPC, personal settings or
native dialogs run; the app-status action is the mapped Dictation button.

Targeted red tests (`tests/test_mic_dispatch_ui.py -k 'dispatch_failure_restores or constructor_survives'`)
recorded **seven failed, 19 deselected in 6.36 seconds**, all at actual worker
dispatch, not at fixture boundaries. The first complete post-fix UI run recorded
**23 passed, three failed in 23.42 seconds**. All dispatch/lifecycle cases passed;
the three 2× layout assertions assumed automatic reveal after refocusing an
already-focused widget or that the whole status paragraph was visible at page
Home. Independent review requires real Tab-away/return and keyboard scrolling
to prove full message/action reachability, not synthetic canvas alignment or
an unsupported claim of automatic resize reveal. The layout acceptance retains
natural bounds, unchanged drafts/text, navigation and keyboard/pointer actions.

Final scoped receipts (owning checkout, explicit `PYTHONPATH`):

- `python -m pytest tests/test_mic_dispatch_ui.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **26 passed in 23.56 seconds, no skips**. Real held workers, guarded external
  boundaries and both failed startup checks are covered. Real Tab-away/return
  reveals full microphone text/Details after reflow; status Home/Page Down
  views overlap by at least a rendered line and expose all text, with preserved
  focus and enabled visible retry after traversal. No canvas alignment substitutes
  for keyboard evidence and no automatic resize reveal is claimed.
- `python -m pytest tests/test_capture_mic_dispatch.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **11 passed in 3.60 seconds, no skips**. Guards, inventory, real dispatch,
  exclusive/incomplete receipts and honest framing constraints pass.
- `python -m pytest tests/test_settings_ui.py -k 'microphone or refresh or status or landing' --capture=sys -o addopts='' -o faulthandler_timeout=30 -p no:cacheprovider -q --tb=short`:
  **41 passed, 59 deselected in 30.51 seconds**, no skips. Existing result,
  overlap, selection, readiness and closed-window semantics pass unchanged.
- `python tests/capture_mic_dispatch.py --output artifacts/screenshots/desktop-mic-dispatch-reviewed-20260926`:
  **six of six** completed. Root and independent reviewer inspected all three
  compact 2× images; retry/message/Details groups fit in the scroll viewport,
  as do footer/navigation. All flags clear, drafts/baselines are unchanged, no
  raw exception appears in primary text and no native dialog/uncaught error
  occurs. Five source/four helper/harness hashes match and six scaling receipts
  restore. Final Settings source:
  `ce9fd4a1631556964aebfeeb03c4da6d24b45c17431521afc9ebb7d209516767`.
  Independent source/test/capture review has no remaining bounded findings.
- Root combined regression:
  `python -m pytest tests/test_settings_ui.py tests/test_settings_search.py tests/test_capture_settings.py tests/test_save_recovery_ui.py tests/test_mic_dispatch_ui.py tests/test_capture_mic_dispatch.py --capture=sys -o addopts='' -o faulthandler_timeout=30 -p no:cacheprovider -q --tb=short`:
  **208 passed in 171.53 seconds, no skips**. Existing Settings/search/save and
  guarded capture paths pass alongside new dispatch checks on unchanged reviewed
  source. `git diff --check` passes. The mixed recovery checkpoint still has only
  its pre-existing unrelated Android plan. No full desktop suite, package build
  or unrelated historical capture refresh was needed for this local change.

This turn is **progress**: the check-dispatch source contract is complete. The
full modernization remains active, including device/model lifecycle, native
dialogs, physical/accessibility acceptance and full-application performance.

### Completed source slice: guided installation inventory and download lifecycle

The initial read-only model-flow audit identified this milestone-G package:
an explicitly refreshed local inventory of the 16 guided model/backend pairs,
human-readable file state and measured required-file storage, with selection
staged through the existing form/Save path. Scope storage honestly: required
files only, excluding shared hub/cache/extra files; not download size or
reclaimable disk space. Keep custom identifiers, language/device choices and
five primary destinations. No recursive store inventory, network lookup,
model loading or active-model claim is needed for this surface.

Before implementation, `download_model` left downloading/Cancel state stuck if
worker dispatch failed and did not recheck closed/reentrant state after
confirmation. This package strengthens that operation contract with bounded
dispatch/cancellation/stale-completion verification alongside the inventory.
The bounded implementation contract follows.

Goal: list guided local model installations on explicit request, describe their
file state and setup file size, and stage compatible selections through the
existing Save path. Downloads recover from dispatch failure and reject stale
completion and reentrant confirmation.

Area: new `model_inventory.py` / `model_inventory_ui.py`, Settings integration,
dedicated inventory/download UI tests, guarded captures and desktop guides.

Constraints: inventory construction does not scan. Refresh checks only the
16 known model/backend locations and recognized setup filenames; no recursive
enumeration, downloads, engine loads, hardware probes or preference writes.
Sizes are logical bytes, exclude shared-cache/extra files, and are not download
or reclaimable sizes. Files changing or becoming inaccessible during checking
have unknown size and explicit error state. Installed does not mean loaded.
Keep custom identifiers and all existing defaults. Use stages only the model
field; incompatible language/backend choices get guidance, never silent changes.
Automatic acceleration is not an active-backend guarantee. Reset deletes no data.

Acceptance: local inventory has readable names/purpose/state/size, explicit
empty/retry/error states and bounded optional Details. Retain the previous list
after a failed refresh; preserve selected identity across a successful refresh.
Single worker tokens ignore duplicate, superseded, closed and destroyed-window
callbacks. Dispatch failures release controls. Confirmed downloads retain the
consented identity, never change network preference, and keep cancellation/reaping
alive after close. A successful completion wins over a late Cancel. Native
keyboard traversal and compact/wide layouts remain usable at 1×/1.5×/2× Tk scale.

Verification (owning checkout and scoped `PYTHONPATH`, shared desktop Python):
`python -m pytest tests/test_model_inventory.py tests/test_model_inventory_ui.py tests/test_settings_model_inventory.py tests/test_model_download_ui.py tests/test_capture_model_management.py tests/test_model_setup.py tests/test_model_presentation.py tests/test_model_presentation_ui.py tests/test_settings_ui.py tests/test_settings.py tests/test_config.py tests/test_privacy.py tests/test_repo_boundaries.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`.
Run guarded before/after `tests/capture_model_management.py`, existing Settings
capture integration, independent source/evidence review and `git diff --check`.
Use serial real-Tk checks; a synthetic capture is not screen-reader or device QA.

Non-goals: Remove, Update, active model identity, revision/checksum catalogue,
download progress/size predictions, recommendations, runtime engine changes,
new navigation, notifications, automatic scans or physical/platform clearance.
Stop editing this slice after its named checks and independent review pass;
remaining A–R work stays active and separately scoped.

Removal/update and active identity remain real requirements, not implied by
this inventory. Source lacks a revision/hash catalogue, shared runtime/setup
lease, unload acknowledgement and managed-path/reparse protection. IPC reports
fixed status, not model identity; asynchronous reload and partial saves make
`SettingsWindow.cfg` an unreliable active-model authority. These need separate
evidence-based lifecycle contracts before destructive or active-state actions.

Verification receipts (September 26, owning checkout; no skips):

- Temporary-store inventory coverage: **28 passed in 0.56 seconds**. An agent's
  attempts could not access its pytest temporary directories before any test
  body ran; the root runner completed the unchanged tests. The grouped
  `test_model_inventory`, `test_model_setup`, `test_model_presentation`,
  `test_settings`, `test_config`, `test_privacy`, `test_repo_boundaries` run
  passed **94 in 2.19 seconds**.
- New real-Tk `test_model_inventory_ui`, `test_settings_model_inventory` and
  `test_model_download_ui` passed **72 in 34.90 seconds**. Includes read-only
  refresh, per-entry/global failure, worker-start recovery, consent reentry,
  close/destroy/stale/duplicate results, retained identity, safe Details,
  captured consent, late cancellation, draft-only selection, Save/discard/reset
  and three-scale compact/wide keyboard and pointer behavior.
- Existing `test_settings_ui`, `test_model_presentation_ui`,
  `test_settings_search`, `test_save_recovery_ui`, `test_mic_dispatch_ui` and
  `test_capture_settings` passed **216 in 196.81 seconds**. The new capture
  harness adds **16 passing checks in 10.45 seconds**. These four grouped runs
  cover **398 distinct focused tests**; all use the stated `--capture=sys`
  flags and scoped import root. A final stronger actual-Tab/Space download
  Details check at all three scales passed with the whole integration module:
  **25 in 19.06 seconds**, without production changes.
- The authoritative ten-image before set is
  `artifacts/screenshots/desktop-model-management-before-worker-20260926`,
  Settings hash `ce9fd4a1631556964aebfeeb03c4da6d24b45c17431521afc9ebb7d209516767`.
  It reproduces escaped worker-start failure and stuck busy controls. An earlier
  capture set patched the download dependency after its closure captured it;
  that set is retained but superseded by the corrected guarded receipt.
- **20 reviewed images** in `desktop-model-management-reviewed-20260926`
  cover download and inventory states at standard/compact 2× text. Its manifest
  verifies eight sources, five helpers, harness hash and 20 restored scales.
  Drafts/baselines stay unchanged; there are no unintended operations or escaped
  exceptions. **55 existing Settings images** were refreshed separately in
  `desktop-model-inventory-settings-20260926`; that harness emits no manifest.
  Production hashes remained unchanged across both runs.
- Reviewed Settings hash:
  `2226b8827e62dc60a787ce1c19040cca981eedd831fa5358e2149c90059af4b5`;
  inventory helper `57d0572fb6962bd5782ff0f39a48dda7fe18b0cf633f8cd94f254ddc30b59dc7`;
  panel `556514ea238658dadeddf1462ceb36e0b441a3ee304c07a60a9ef23b56194d45`.
  Root independently reviewed the delegated helper/panel and inspected the
  key compact/standard captures. A separate reviewer checked the root-owned
  Settings/download integration and final hashed evidence, with no blocking
  findings. No model/setup/runtime persistence source was
  changed; no full suite, package, real download or microphone run was needed.

At compact 2× text, complete inventory panels require scrolling (installed
group 779 px; error group 1,000 px versus a 414 px viewport). Inventory recovery
plus Details fits locally (252/215 px). Download start/failure groups are
445/477 px; their Details is below the initial frame. The actual keyboard tests
prove reachability, not simultaneous full-group visibility. Captures are manually
framed, not automatic reveal, screen-reader, physical DPI or platform clearance.

This inventory slice is progress, not completion of A–R. Its follow-up is a read-only,
authenticated **loaded model for applied settings · last checked** snapshot.
The runtime's successful `_engine_config_key` must match one captured applied
configuration; inventory, saved preferences and the Settings draft are not
authority. Use a versioned allowlisted token (canonical public model or custom),
never arbitrary identifiers, paths, text or backend IDs. Preserve old status
clients; reject stale reload/quit proof and clear previous claims on failure.
The contract below chooses a combined status version after reviewing
cross-request consistency. Matching load proof still does not identify an
already-running take's model. The race/privacy/UI contract below governs this
implementation; Remove/Update and destructive lifecycle remain out of scope.

### Completed source slice: loaded model for applied settings

Goal: Dictation and Help show the runtime's matching successful model-load proof
alongside the last-checked app state, distinct from the Settings draft, local
inventory and a model retained by an already-running take.

Area: `transcribe.py` read-only accessor, pure model presentation/status codec,
`app.py` authenticated snapshot, opt-in exact IPC reply framing, Settings refresh, focused runtime/IPC/UI tests,
guarded captures and desktop guides. Root owns app/Settings integration; parallel
writers own only the assigned accessor, codec or test/capture modules.

Constraints: no new model cache, polling, engine loading, hardware/device probe,
capture, inference lock acquisition, preference mutation, dependency or framework.
The existing immutable successful `_engine_config_key` must match captured
applied model/device/compute/language preferences. Reset, changed preferences,
superseded warmup, failed replacement and Quit cannot provide stale identity.
Backend fallback retains requested-preference semantics. No transcript, caption,
device name, arbitrary model identifier, path or exception enters the reply.

Protocol decision: use one authenticated `status-detail` request returning
`status-v2:<state>:<model-token>`. Keep `status`/`status-v1` unchanged. A combined
snapshot avoids joining operational and model claims from separate requests.
State is one existing public enum; model is one canonical public token, `custom`
or `unconfirmed`. Ready requires confirmed matching proof. Parse exact tokens,
never render arbitrary server text. Only an exact older-server `unknown` reply
may trigger the existing `status` request, with loaded detail marked unavailable.
No fallback request follows transport failure, missing authentication or malformed
data. The new request opts into `ipc.send(..., exact_reply=True)`: preserve
payload whitespace, require a bounded newline-terminated reply and reject
truncation before parsing. Existing send callers retain their default behavior.
A snapshot is a last check, not continuous monitoring or active-take ownership.

Acceptance: sample captured applied preferences and successful-load metadata
without waiting on native work; detected configuration/generation/presentation/
shutdown changes yield conservative unknown/unconfirmed output. Confirmed names
use fixed local labels; every custom identifier is reduced to `custom`. Native
load/inference locks do not delay the read-only request. Old clients still get
their unchanged status. Authenticated loopback is required, with legacy endpoints
never receiving the new command. Settings clears old proof when checking or on
failure, ignores stale/duplicate/closed results, recovers from dispatch failure,
preserves unsaved drafts and does not infer runtime identity from Save outcomes.
Compact/wide keyboard reachability and full wrapped feedback are tested at three
Tk text scales. Summary actions stack below their text at narrow/larger-text
widths and restore side-by-side layout when space returns without changing
focus order or drafts; dialogs and physical accessibility remain separate gates.

Verification: shared desktop Python and scoped `PYTHONPATH`; run new accessor,
codec, app/IPC and UI modules first with `--capture=sys -o addopts='' -p
no:cacheprovider -q --tb=short`. Then existing transcribe/readiness/app/status/IPC,
Settings/search/save/dispatch/privacy/config/boundary regressions. This integration
changes runtime protocol/import paths, so run the full desktop pytest gauntlet
after focused tests. Capture before/after via `tests/capture_loaded_model.py`,
refresh existing Settings evidence, inspect source hashes, obtain independent
review and run `git diff --check`. No package/release or real model/microphone run.

Non-goals: active-take engine identity, backend disclosure, Remove/Update,
checksums/revisions, recording controls, automatic refresh, notifications or
physical/platform certification. Stop this slice after the named runtime,
privacy, compatibility, UI and full-desktop checks pass; the full A–R plan remains.

Gauntlet findings (September 26): independent review caught universal-newline
normalization in the new exact-reply path. Binary bounded framing now preserves
CR, requires LF and decodes UTF-8 strictly; the default transport is unchanged.
Actual-wire regressions cover CR/CRLF, padded/embedded-CR `unknown`, oversized,
truncated, private and invalid-UTF-8 replies. The first complete-suite attempt
was **aborted, not passed**: many later UI tests failed, and faulthandler located
an unexpected native error dialog in the snapshot-save test at about 81%.
Its earlier orphan `_poll` warning came from the model-download test's deliberate
external window destruction, which now cancels its unrelated Tk timers.

The broader isolation failure was reproduced separately: all 13 download tests
passed, but same-interpreter postchecks found `Thread.start` still replaced by
the capture guard and download/confirmation functions still mocked. The fixture
had let its capture contexts exit before pytest's monkeypatch undo restored those
temporary guards. It now undoes test overrides inside the guards and asserts
original function identities after teardown. The same-process download/inventory/
real save-worker rerun passed **48 in 17.81 seconds** with all three identities
restored. Unexpected error dialogs in the snapshot-save success test now fail
that test rather than hanging unattended validation. An initial shared-fixture
placement of this guard conflicted with the save-recovery module's intended
dialog mock: the fail-fast rerun stopped at **2,042 passed, 11 skipped, 1 failed
in 236.29 seconds**. Narrowing the guard to the success test resolved the
conflict; all **four affected cases passed in 3.04 seconds**. A bounded independent audit found no second matching
global teardown-order leak. These are test-harness corrections, not runtime
workarounds; the full suite is rerun on unchanged production source.

Final full-desktop receipt (September 26, owning worktree, shared desktop Python
with `PYTHONPATH` scoped to this checkout):
`python -m pytest --capture=sys -o addopts='' -p no:cacheprovider -q -ra --tb=short -x -o faulthandler_timeout=30`
passed **2,648 tests, with 14 explicit prerequisite skips, in 398.78 seconds**.
No Tk tests skipped, no assertion failures and no orphan Tcl-timer warning.
The skips are 11 verified-FFmpeg codec checks, one unavailable local public JFK
speech fixture (no automatic download), one unavailable Windows symlink
privilege, and one opt-in Windows clipboard-isolation acceptance check.

Earlier focused receipts are subsets, not additive full-suite counts: **431
runtime/readiness/status/transcribe/IPC/privacy/config/boundary tests** passed
in 3.97 seconds; **75 new app-snapshot/IPC/security checks** passed in 3.25 seconds;
and **43 final responsive/UI/capture-fixture checks** passed in 39.02 seconds.
The independent source review is clear after the binary-framing correction;
the layout and behavior-documentation follow-ups are also reviewed clear.

Frozen production SHA256 values for this full run:

- `app.py`: `07c153b53511a3f68f8b00a6e6b275b0cd1f97159bd110c55a5a3b924537de36`
- `transcribe.py`: `8d2cd28f439a37b0bb32bb49312e2bd66b4ca51eeba6548ea9cdc78094436777`
- `ipc.py`: `090df6638d72c16482792c1838e766eb77b8f09ea1c863b4989b4ca704bcb72d`
- `settings_ui.py`: `02c61dbe3f163afa99a24e62ba754cba8d72bfc44d7525bae89108e43a8fa5e7`
- `model_presentation.py`: `6f5ac1b9c6e16a2baf79edc177f23a7087679cfd50d94873646be78bf3780671`
- `app_status.py`: `dbed963ac12bcd8e1e48e8bf502e114b949fa4ec0f260be3f95d4ea5ca7e82ac`

The first completed capture receipt, `desktop-loaded-model-final-20260926`,
contains **12 images** (six states at standard and compact 2×), but it predates
the later section-reset source change and is retained as intermediate evidence.
The source-matched replacement,
`desktop-loaded-model-source-final-20260926`, contains the same **12 completed
images**. Its seven source, six helper and harness SHA256 values match current
source, including Settings `6bb4ec8e530e131d916c5f10a37c2a2a43cba2b7562efda519a158b611c6603e`
and capture helper `8592d1a814b2856431a4e1ff255d9a1a4ab13d41bc3af03716e26db79adb34bd`.
All drafts and
baselines remain unchanged, scales restore, and recorded action/footer/sidebar/
text bounds pass. At compact 2× the complete heading, detail and Refresh group
is 260 px for confirmed/custom/listening/legacy states and 186 px for malformed/
failure states within a 414 px viewport; the text allocation is 430 px wide.
Visual inspection confirms fixed names, fixed custom/unconfirmed copy, no raw
malformed payload and the new stacked actions. Its source-matched companion
`desktop-section-reset-settings-final-20260926` contains **56 Settings images**,
including the staged Recording feedback reset.
These are synthetic Windows/Tk presentation receipts, not live app/model,
active-take, screen-reader or physical-DPI evidence.

### Completed source slice: Recording feedback section reset

Goal/area: add one local Reset action to the existing Recording feedback section
in `settings_ui.py`, covering only `indicator`, `live_preview` and `beep`, with
focused `tests/test_section_reset_ui.py`. Read defaults from `Config()`; keep the
five primary destinations, existing controls and preference schema unchanged.

Constraints: stage only those three form values after explicit confirmation.
Keep `cfg`, baseline and `_reset_pending` unchanged: that flag governs the
existing global reset's advanced-default replacement at Save. Preserve it even
if global reset is already pending. Never write preferences, change privacy or
startup choices, clear vocabulary/models, stop checks, send IPC or load models.
The prompt must say that unrelated edits remain and Save saves all pending edits.
Guard closed/saving/reentrant confirmation and recheck after the dialog returns.

Acceptance/verification: declining preserves the entire draft/flags/focus;
confirming changes only the three fields; an already-default section creates no
dirty state. Preserve focus when disabling preview. Test Save success/failure,
newer edits, advanced preferences, global-reset coexistence and discard/reopen
using isolated storage. Run section-reset plus existing Settings/save/config/
privacy tests with scoped `PYTHONPATH` and the standard `--capture=sys` flags.
Capture compact/wide keyboard access at three text scales; obtain independent
review and update user guidance.

Non-goals/stop: no new categories, global-reset rewrite, automatic apply,
destructive cleanup or release work. Stop after those bounded checks; other
settings groups need their own reset field contract before adding actions.

Completion receipt (September 26): the production action stages exactly the
three named `Config()` defaults, restores focus after a declined native prompt,
moves focus when preview becomes disabled, and keeps the reentry latch safe even
when focus lookup or the dialog raises. Save success/failure/newer edits, both
global-reset orderings, active microphone-check state, and real UUID-scoped
config discard/reopen are covered. The new module passed **16 tests**; the
Settings/save/config/privacy/boundary regression passed **192 tests in 85.98
seconds** using a workspace-safe pytest temp root; independent review found no
remaining issue. Capture/section tests passed **21 tests in 19.35 seconds**.
The deterministic Settings harness produced **56 images** in
`desktop-section-reset-settings-final-20260926`; the staged view was inspected
and includes the scoped button, default values and unsaved status. Frozen hashes:
Settings `6bb4ec8e530e131d916c5f10a37c2a2a43cba2b7562efda519a158b611c6603e`,
section tests `b7759a7014784bc93e9d8616afda8473f7a0dd22ec3592807e5e0283f3bff1d9`,
capture helper `8592d1a814b2856431a4e1ff255d9a1a4ab13d41bc3af03716e26db79adb34bd`.
No preference, model, vocabulary, IPC, microphone or framework behavior changed.

Current-source broad-suite note: a normal final run reached **1,345 passed and
11 expected skips** before the existing Windows OBS native child-pipe fixture
hit its eight-second self-expiry; the exact test failed again in isolation before
the product assertion path. A diagnostic remainder run completed **2,642 other
tests with 14 expected skips**, but its temporary-directory compatibility shim
intentionally changed directory creation and therefore made 20 additional OBS
pipe/private-ACL checks invalid; those failures are not counted as product
results. No OBS source changed in this slice. The last complete unmodified
desktop receipt remains the immediately preceding **2,648 passed, 14 skipped**
run above, while all source changed by this section-reset slice is covered by the
192-test focused regression and independent review. The managed-host native pipe,
private-DACL and physical release gates remain open rather than being weakened.

### Completed source slice: effective input-route revalidation

Goal: every explicit `Recorder.prepare()` re-resolves the effective input route
and invalidates a cached stream when that route changed, even if the human-readable
device name is unchanged. A disconnected named device remains fail-closed; an
exactly reconnected selection may succeed only on an explicit retry.

Area: `utterleaf/audio.py`, `tests/test_audio.py`, and only if owner-thread
sequencing requires it, `audio_owner.py` / `tests/test_audio_owner.py`. The audio
writer owns these files; Settings/config/app/docs remain integrator-owned.

Constraints: use a private within-process enumeration-route key, not a claim of
durable hardware identity. No schema/UI change, polling, passive monitoring,
automatic capture, fuzzy rename match or silent named-device fallback. Preserve
the current live take and the existing single bounded retry for documented
transient open failures. Duplicate same-name named endpoints must fail closed
unless a later stable native-identifier contract resolves them.

Acceptance: same-name default-route replacement closes and reopens on the next
prepare; a different default retains existing reopen behavior; missing named
selection refuses default fallback; reconnecting the exact saved name succeeds
on explicit retry; a preference change during a live take waits until that take
ends. Tests must not call this stable identity, hotplug monitoring or physical
device proof.

Verification: shared desktop Python with scoped `PYTHONPATH`; run
`tests/test_audio.py tests/test_audio_owner.py`, then
`tests/test_audio_interruption.py tests/test_continuous_capture.py`, using the
standard capture/no-cache flags, followed by independent review and
`git diff --check`.

Non-goals/stop: persistent identity across reboot, rename continuity, native
enumeration timeout, background hotplug/default notifications, Settings changes,
or physical USB/Bluetooth/sleep-wake certification. Stop after mocked route
change/reconnect coverage and the focused audio lifecycle regression pass.

Completion receipt (September 26): default selectors are resolved on each
explicit prepare to one current numeric enumeration index before stream reuse,
including supported `sounddevice` query strings and Windows WASAPI default
translation. Numeric `-1`, ambiguous query strings, duplicate saved names and
missing named inputs fail closed. The route key is private and cleared on close;
it is explicitly not durable hardware identity. Tests cover unchanged reuse,
same-name/different-name default replacement, start→stop→next-start reopening,
named reconnect, active-take preservation and owner/interruption/continuous
capture regressions. Root and independent review reruns each passed **145 tests**
(2.43 and 2.31 seconds); review found no blocking issue. Frozen hashes:
`audio.py` `d37283db4f20161d18bdb77375be65c20bd73541ff97ddacce6683db2af234a5`,
`test_audio.py` `a26ce68f5ab595a8019b4448670934382b58902c178e2ffadf93eebe60a43413`.
No UI, schema, polling or automatic capture was added. Actual unplug/reconnect,
rename, OS-default notification, sleep/wake and stable endpoint identity remain
physical/native follow-up gates.

### Completed source slice: unsupported microphone configuration recovery

Goal: structured audio format/channel/rate failures explain why capture could
not start and give a relevant recovery action instead of generic permission advice.

Area: `audio.py` error presentation, focused audio/runtime/Settings tests,
deterministic microphone-error captures and desktop documentation.

Constraints: classify only documented integer PortAudio codes, never arbitrary
exception text or coerced strings/floats. Preserve native HRESULT guidance,
named-device selection, single-owner audio, retry/fallback behavior, cancellation,
explicit Test/Start and local Details. No real capture, passive monitoring,
preference schema change, driver workaround or new dependency.

Acceptance: supported structured codes return fixed problem/impact/recovery copy;
unknown or malformed codes retain safe generic guidance. No private exception
text appears in primary feedback. Unsupported configurations cause no automatic
retry or device fallback. Settings failure/retry preserves drafts and clears old
Details; compact larger-text feedback/actions remain reachable.

Verification: pure audio tests, mocked runtime failure tests, affected real-Tk
Settings tests and guarded captures with `--capture=sys`; independent review and
`git diff --check`. No full-suite rerun is required for error-copy classification
alone; the immediately prior readiness integration receipt remains historical.

Non-goals: stable hardware identity, enumeration timeout, hotplug monitoring,
physical-driver certification, packaging or release. Stop after the bounded
source checks and capture review; all remaining A–R gates stay active.

### Completed source slice: truthful applied-model readiness

Goal: model warmup cannot replace microphone opening/listening, queued processing
or a newer failure. Ready requires a successful load matching the app's applied
model/device/language/compute preferences, never just files or Settings drafts.

Area: app warmup/status publication, transcription cache identity/readiness,
fixed status protocol and Settings presentation, focused tests and captures.

Constraints: keep existing capture, inference, download consent, fallback and
delivery architecture. No ambient audio, hardware enumeration, filesystem/model
probe or new worker/timer from status queries. Keep replies fixed and text-free.
Use frozen warmup configuration, a monotonically increasing generation and one
app-owned loading lane; recheck staleness after acquiring that lane. No capture,
app-state or presentation lock may surround native model loading/reset waits.
Recheck current download permission before native loading: a later opt-out can
revoke a queued request, but a later opt-in cannot broaden its frozen permission.
This does not promise cancellation of native model work already in progress.
Cache readiness must be immutable, nonblocking and invalidated before replacement
or reset; requested device/compute/language identity must govern cache reuse.
Existing CPU fallback remains associated with the original requested settings.

Acceptance: stale success/failure/queued warmup and callbacks after quit cannot
publish or supersede current loading. Non-model reload preserves active status.
Model loading/error survives recording/cancellation/completion until current
loading succeeds. Current Ready is a last-checked model-load claim; microphone
availability is checked only when explicitly starting/checking capture. The
Settings app status describes applied settings separately from selected drafts.
Brief result feedback expires back to the durable model state; it must not hide
loading or failure permanently. Quit clears cached presentation captions.
Tests hold fake loads/locks deterministically; no real model or microphone work.

Verification: focused app/readiness/cache/status/Settings tests, guarded captures,
independent review, then full desktop pytest with `--capture=sys` because model
cache and app status are shared integration points. Record exact skip prerequisites.

Non-goals: new tray capture controls, detailed device/model metadata in IPC,
passive device monitoring, a framework or inference rewrite, release packaging,
or certifying native devices/accessibility. Stop this slice after its tests,
capture and independent review; the rest of A–R stays active.

### Completed source slice: auxiliary recovery and state terminology

Goal: file transcription/export and decoder setup failures explain problem,
impact and next action, with bounded technical information disclosed explicitly.
Align visible capture/model-failure labels without changing runtime state keys.

Area: `file_ui.py`, `file_decoder_ui.py`, a reusable native feedback component,
`brand.py`/`indicator.py`, focused tests, guarded captures and desktop docs.

Constraints: preserve queues, cancellation/late-result handling, original-file
and overwrite protection, decoder identity/checksum/local-file validation and
explicit trust consent. Do not infer causes from arbitrary exception strings or
discard diagnostic context. No automatic retry, model/download/capture work,
new runtime polling, framework change, config schema or shared Android changes.
Ready must not be substituted for Idle. Loading/transcribing details stay useful;
the shared delivery-error key covers copy/delete/review as well as insertion.

Acceptance: safe primary copy plus next action; technical details are bounded,
control-character sanitized, shown only on request and cleared when the
underlying operation changes or the window closes. Export failure preserves
the preview and does not claim that no destination could have been written.
Decoder errors preserve explicit executable trust and do not silently select
anything. Details are keyboard-accessible and visible after focus at compact
1×/1.5×/2× text scale. Existing workflow/layout/security tests remain intact.

Verification: scoped `PYTHONPATH`, focused recovery/auxiliary/capture/brand/
indicator/failure tests using `--capture=sys`, separate guarded recovery images,
native indicator captures when the GUI slot is free, independent review and
`git diff --check`. The FD-capture/runtime issue has a bare-Tk reproducer; use
system-stream capture without treating it as an application fix or hiding tests.

Non-goals: actual readiness, new tray controls, decoder/security internals,
native-dialog/screen-reader certification, or release work. Stop this slice
after source checks, captures and independent review; retain the full A–R scope.

### Completed source slice: file and review auxiliary baseline

Goal: record file transcription, optional decoder setup, and automatic-dictation
review states before visual changes, and expose compact/large-text or keyboard
failures with repeatable synthetic fixtures.

Area: those three existing desktop surfaces, a guarded
`tests/capture_auxiliary.py`, capture-isolation tests and desktop baseline docs.

Constraints: preserve each workflow and protocol. No live microphone, recognition,
model loading/download, clipboard action, export, browser/process launch, or
personal configuration read/write. Use `Config()` and bounded sample text;
intercept workers without running their targets, native dialogs and external
entry points. Review rendering may use in-memory request/output streams but
must not start its production child process or control-reader thread. Never
weaken consent, cancellation, original-file protection or insertion verification.

Acceptance: capture initial, working, cancelled, result/empty/error file states;
decoder unselected/selected/failure; review Insert-enabled/disabled, compact and
large-text layouts. Preserve a manifest with requested/actual dimensions, scale,
source hashes and scenario inventory in a new ignored output directory; do not
erase or silently replace baseline evidence. Fixture tests prove side effects
are intercepted and production callbacks produce the staged states. Record any
new clipping or keyboard failures before fixing them in a bounded follow-up.

Verification: `python tests/capture_auxiliary.py`; focused
`python -m pytest tests/test_capture_auxiliary.py tests/test_file_ui.py
tests/test_file_decoder_ui.py tests/test_review_ui.py -o addopts=''
-p no:cacheprovider -q` with this checkout's `PYTHONPATH`, independent guard review,
visual inspection and `git diff --check`.

Non-goals: real file transcription, native picker certification, clipboard/editor
acceptance, physical DPI, framework changes, backup/OBS behavior or new features.
Stop after the guarded baseline and tests are complete; retain other auxiliary
surfaces and external acceptance as open work.

The final compact 2× Settings text-scale capture exposed a sidebar follow-up: the optional
privacy tagline was partially clipped below the five navigation controls. The
bounded correction must keep all navigation stable and fully visible, show that
redundant tagline only when it fits completely, and restore it on taller windows.
No privacy setting, disclosure page, focus, draft, or footer action may change.
Verify compact→tall→compact at 1×/1.5×/2×, existing shell tests, and final captures;
this is layout acceptance, not physical DPI or screen-reader certification.

Continue bounded implementation and independent review until the local source
work and acceptance checks are exhausted. A green mocked suite is not a waiver
of these remaining product/release gates:

- Remaining auxiliary windows and native dialogs need their own baseline and
  keyboard checks. File/decoder/review have source coverage; native dialogs are
  intercepted or explicitly post-dialog in current captures.
- Device identity/hotplug and model lifecycle need separate functional contracts;
  neither is a visual-only change. Keep download consent and named-input safety.
- Screen readers/UIA, physical scaling and mixed DPI, real microphones/editors,
  clean installed builds, and native macOS/Linux behavior need direct evidence.
- Startup, idle CPU/memory, tray overhead, and recognition latency need named
  hardware measurements; no-new-polling is not a performance measurement.
- Preserve historical release receipts. Local edits, captures, and source tests
  do not publish a new release or validate a signed binary.

### Completed source slice: auxiliary responsive layout and keyboard access

Goal: file transcription, decoder setup and automatic-dictation review retain
usable actions and readable content at their existing minimum window sizes.
The 19-image auxiliary before-state manifest reproduces clipped actions at 2×
Tk text scaling: file Close falls at y=702 in a 560-pixel window, decoder Done
at y=853 in a 500-pixel window, and review actions at y=323 in a 320-pixel window.

Area: these three renderers, a small native-Tk layout helper, focused layout
tests, guarded captures and desktop documentation. Preserve the before images.

Constraints: no framework migration, minimum-size inflation, new polling,
workers, global input hooks or workflow/protocol changes. Preserve cancellation,
discard, read-only previews, explicit export/decoder trust and review's fixed
action tokens. Tests must not record, recognize, download, export real files,
read/write the clipboard or change preferences.

Acceptance: fixed actions wrap at measured natural sizes; long content scrolls;
keyboard focus reveals controls and the active read-only preview line. Native
text/picker keys and Tab traversal survive. Compact→wide→compact at 1×/1.5×/2×
retains widget identity, selection and state. New guarded candidate captures
record actual dimensions and source hashes; independent review finds no blocker.

Verification: `python -m pytest tests/test_auxiliary_layout.py
tests/test_capture_auxiliary.py tests/test_file_ui.py tests/test_file_decoder_ui.py
tests/test_review_ui.py -o addopts='' -p no:cacheprovider -q -s`; then
`python tests/capture_auxiliary.py --output
artifacts/screenshots/desktop-auxiliary-final` and `git diff --check`.
The ordinary captured-output run has a separately recorded intermittent Tcl
initialization failure; disabling capture does not establish its cause or repair.

Non-goals: speech/decoder security internals, native picker certification,
screen-reader or physical-DPI clearance, error-language redesign and releases.
Stop this slice after focused checks, visual inspection and independent review;
retain the full modernization's other acceptance gates.

### Bounded Settings performance check

Goal: measure whether this Settings source change introduces an obvious local
construction, memory, or idle-CPU regression before broader hardware acceptance.
Area: ignored `.grok/measure_settings.py` and local JSON receipts only; no product
instrumentation or additional production timers.

Constraints: compare baseline `be4f117` Settings source to candidate using the
same current dependencies/assets in fresh child processes. Retain the existing
80 ms Settings queue poll, but disable background device/status work and fail
on audio, downloads, network, workers, writes, or external actions. Run serially
with runtime source, assets, and environment frozen and no user interaction;
no model or preferences change. Capture/test-only edits are not benchmark inputs.

Acceptance/verification: three alternating fresh-process pairs, each a mapped
960×780 real Tk window with 12 seconds of idle. Preserve every sample, source
hashes, non-unique hardware metadata, construction timings, idle CPU, private
commit and working set in an exclusive JSON receipt. Report medians and ranges,
not p95 or universal thresholds. Investigate reproducible regressions rather
than discarding unfavorable samples.

Non-goals: cold whole-app launch, tray, microphone/recognition latency, physical
hardware acceptance, or Milestone P completion. In-memory source compilation,
current shared dependencies and fixture-disabled background checks limit this
comparison. Stop after reviewed harness execution and a scoped evidence report.

## Verification receipts — September 26, 2026

### Unsupported microphone configuration recovery

- The shared microphone hint now recognizes only actual `PortAudioError`
  instances with the library's two-argument string/integer shape and the four
  documented channel/rate/sample-format/I/O-combination codes. Definitions and
  exception construction were checked against the installed local sounddevice
  bindings. Existing native WASAPI guidance and all capture/retry behavior remain
  unchanged; no exception-text matching or value coercion was added.
- Primary copy explains that the microphone cannot use the requested audio
  format and directs users to choose another input. Details remain explicit and
  local. Tests verify malformed/unknown codes, private-text exclusion, no
  automatic retry/fallback, stream and owner cleanup, runtime attention status,
  unchanged drafts and retry clearing. Large-text layout checks use both
  disconnected-device and unsupported-format copy.
- Shared Python with checkout-scoped `PYTHONPATH`:
  `python -m pytest tests/test_app.py tests/test_audio.py tests/test_settings_ui.py tests/test_capture_settings.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **275 passed in 106.87 seconds, no skips**.
- `python -m pytest tests/test_indicator.py tests/test_failures.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **29 passed in 2.23 seconds, no skips**. Independent audio/app validation passed
  **171 tests in 1.14 seconds**. Independent source and capture review is clear.
- `python tests/capture_settings.py --output artifacts/screenshots/desktop-audio-format-candidate`:
  **49 images completed**, adding ordinary and compact 2× format-error views.
  Full primary guidance and focused Details fit with the fixed footer visible.
- `python tests/capture_indicator.py --output artifacts/screenshots/desktop-indicator-audio-format`:
  **12 native Windows scenarios passed three lifecycles**. The new microphone
  format caption fits in two lines without losing its recovery action. Headline
  bounds, rounded regions and window-class cleanup remain checked.
- `git diff --check` passes. No real audio/model/network or personal-preference
  work occurred; no packaging or full-suite rerun was needed for this bounded
  classification/copy change. The earlier 1,958-test integration receipt keeps
  its original source stage. Physical drivers, stable device identity, native
  enumeration timeout and assistive-technology acceptance remain open.

### Applied-model readiness and status precedence

- Startup and model-preference reload now use one serialized, generation-checked
  warmup path with frozen configuration. Stale queued work is skipped after the
  lane is acquired; late completion cannot replace current loading, capture,
  queued processing, errors or shutdown. Native model waits hold neither the
  capture/state locks nor the presentation lock.
- Model cache identity now includes resolved model, requested device, compute
  type and language, with immutable successful-load metadata cleared before
  replacement/reset. CPU fallback remains associated with its requested
  preferences. The read-only `status-v1:ready` reply requires this matching
  proof; queries add no model/device/filesystem work or polling.
- Independent review caught two regressions before completion: temporary result
  expiry could permanently hide a newer model failure, and frozen queued warmups
  could retain download permission after a later opt-out. Both are corrected
  and covered. Opt-out is enforced before native loading, not retroactively
  after native work starts. Opt-in cannot broaden a queued request.
- Shutdown review also caught a newly retained result-caption copy. Quit now
  clears both presentation captions under their lock. Late timers/publishers
  cannot restore them. A cancelled worker may still unwind while Ready remains
  true for the loaded model; the cancelled delivery guard stays cancelled even
  after worker flags clear.
- Focused integration command, shared Python with checkout-scoped `PYTHONPATH`:
  `python -m pytest tests/test_app.py tests/test_app_readiness.py tests/test_app_status.py tests/test_transcribe.py tests/test_transcribe_readiness.py tests/test_failures.py tests/test_settings_ui.py tests/test_capture_settings.py tests/test_ipc_security.py tests/test_model_setup.py tests/test_config.py tests/test_privacy.py tests/test_repo_boundaries.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **332 passed in 96.92 seconds, no skips**. This preceded the small final Quit
  caption cleanup and its three additional regression cases.
- Final readiness-module check: **80 passed in 2.20 seconds**. Independent
  final edge verification: **7 passed, 73 deselected**. The separate cache
  readiness module has 19 focused cases; all loads/backends/devices are fakes.
  Independent bounded source review is clear.
- `python tests/capture_settings.py --output artifacts/screenshots/desktop-readiness-candidate`:
  **47 images completed**. Inspected Ready/applied versus draft-file status,
  compact Dictation and compact 2× model layout. No real model, microphone or
  personal settings are involved. A subsequent docstring-only correction does
  not change the captured layout or behavior.
- `python tests/capture_indicator.py --output artifacts/screenshots/desktop-indicator-readiness`:
  **11 native Windows scenarios passed three lifecycles**. Inspected the updated
  model-error caption directing users to Speech & privacy or Help. Headline fit,
  window regions and native class cleanup remain checked; earlier captures are
  preserved. These are not macOS/Linux or screen-reader acceptance.
- Final full desktop command:
  `python -m pytest --capture=sys -o addopts='' -p no:cacheprovider -ra -q`:
  **1,958 passed, 14 skipped in 189.38 seconds**. Skips require an explicitly
  verified local FFmpeg binary (11), the local public JFK audio fixture (1),
  Windows symlink privilege (1), or opt-in Windows clipboard-isolation acceptance
  (1). No prerequisite was downloaded, granted or waived to make this run green.
  This includes the final shutdown/privacy and applied-model cache changes.
- `git diff --check` passes. No Android, packaging or dependency change, real
  microphone/model download, personal-preference write, commit or publication
  occurred. The mixed recovery checkout retains only its pre-existing Android
  plan. This completes the bounded source slice, not the A–R release gate.

At this receipt's source stage, the next candidate was structured unsupported-
audio-configuration recovery. Its later receipt above records the implementation
and validation. Stable device identity and bounded enumeration still require
separate contracts.

### Auxiliary recovery and state terminology

- Added shared native recovery feedback for file transcription/export and decoder
  setup: problem, impact, retry guidance, explicit bounded Details. Ordinary
  status changes and destruction clear details; hiding a focused Details action
  hands focus to the next control. No automatic dialog, clipboard, export or log
  operation was added. Export errors preserve the preview and selection.
- Destination validation now reports errors before exporting. Its exception
  handler is deliberately separate from export overwrite confirmation: even a
  validation `FileExistsError` cannot authorize an overwrite. Tests cover both
  that exception and ordinary `OSError`, with no exporter or consent call.
- Shared brand `recording` presentation is Listening; stable runtime/asset keys
  remain unchanged. Model errors say Speech model unavailable; shared text-action
  errors say Needs attention because the key also covers copy/edit/review failures.
  Existing captions, timers, state transitions and readiness semantics remain.
- The first combined run had **135 passed, 1 failed in 32.88 seconds**. The new
  caption-free Tk model headline reached x=223 in a 220-pixel window. The renderer
  now uses the same root-owned font for measuring width and drawing the title.
  Four indicator cases check exact headings and every text bounding box.
- Visual review found file Details just below the viewport when only the label
  was revealed. Revealing the whole recovery group fixes this; six mapped-failure
  tests assert primary copy and Details fit at compact 1×/1.5×/2× text scale
  without moving footer focus. The capture harness maps before staging failure,
  exercising that production reveal path. A separate initial test-fixture failure
  came from destroying its Tk owner before restoring scaling; keeping a surviving
  owner fixes the fixture without changing product behavior or weakening checks.
- Final-source command, shared Python with checkout-scoped `PYTHONPATH`:
  `python -m pytest tests/test_ui_feedback.py tests/test_auxiliary_recovery.py tests/test_auxiliary_layout.py tests/test_capture_auxiliary.py tests/test_file_ui.py tests/test_file_decoder_ui.py tests/test_review_ui.py tests/test_brand_assets.py tests/test_indicator.py tests/test_failures.py --capture=sys -o addopts='' -p no:cacheprovider -q --tb=short`:
  **142 passed in 37.85 seconds, no skips**. No full-suite or packaging claim is
  made for this UI-only increment.
- `python tests/capture_auxiliary.py --output artifacts/screenshots/desktop-auxiliary-recovery-final`:
  **21 images completed**, including mapped compact 2× file/decoder errors.
  Inspected ordinary file/export/decoder failures and both new large-text views.
  Manifest hashes match all six owned surface/helper sources and the harness.
  Before-state, prior layout and first recovery candidates remain preserved.
- `python tests/capture_indicator.py --output artifacts/screenshots/desktop-indicator-recovery`:
  **11 native Windows scenarios passed three create/update/quit lifecycles**.
  The compact model headline measures 176 pixels in 190 available; title fit,
  rounded corners/edges and class cleanup pass. Eleven images were retained and
  model-error compact/expanded views inspected. Native Win32 rendering itself
  needed no change; the Tk fallback still needs native macOS/Linux acceptance.
- Independent review found no blockers, including the later destination guard,
  measured Tk headline and whole-panel reveal corrections. `git diff --check`
  passes. No real microphone, model download, personal preference, clipboard,
  package or release work occurred. The mixed recovery checkout is unchanged
  apart from its pre-existing Android plan.

At this receipt's source stage, model-load generation/readiness and
recording/processing/error precedence remained the next gate; the later
applied-model readiness receipt records that follow-up. Tray capture controls,
remaining auxiliary/recovery surfaces, device identity/enumeration, model
lifecycle, settings disclosure/search, whole-app performance and external
accessibility/platform gates remain in scope.

### Auxiliary baseline and responsive follow-up

- Guard-reviewed baseline capture completed **19 images** before these three
  renderers changed; manifest and images remain in
  `artifacts/screenshots/desktop-auxiliary-baseline`. Inspection and measured
  bounds exposed the three compact 2× clipping failures recorded above.
- Initial four-module check: **47 passed, 3 failed in 13.54 seconds**. One
  assertion wrongly expected the decoder's full path instead of its intended
  basename; corrected without exposing the path in production. Two failures
  occurred during `tk.Tk()` initialization, before auxiliary widgets existed:
  Tcl could not read `entry.tcl`/`init.tcl` even though both files exist.
- File-window layout change alone retained its workflow coverage:
  **13 passed in 3.12 seconds**. A geometry probe then found stale canvas height
  after labels wrapped (5,084 actual versus 599 requested pixels). Coalesced
  event-driven geometry settling corrects this without recurring polling.
- The next four-module run: **47 passed, 3 failed in 7.76 seconds**. Two
  additional initialization failures named `icons.tcl`/`ttk/scrollbar.tcl`;
  the third exposed an old decoder geometry test measuring a withdrawn 1×1
  transient window. That test now maps the parent/dialog and requires actual
  560×500 dimensions and fully mapped, naturally sized actions.
- The Tcl startup failures are retained, not skipped/retried away. Read-only
  inspection found no guard patch of filesystem/Tcl APIs, environment or working
  directory; shared Python points to the reported installation. Delayed Tk
  interpreter collection remains an unproven hypothesis under bounded diagnosis.
- Independent source review identified ancestor FocusIn scrolling, NumLock
  rejection and double scrolling over a nested preview scrollbar. Corrections
  are implemented and the reviewer confirmed all three resolved. No remaining
  source blocker was found in the integrations or strengthened assertions.
- The first 19-case layout run had **9 passed, 10 failed in 9.62 seconds**:
  nine tests unnecessarily deiconified already mapped windows during resize,
  which activates the Windows top-level instead of preserving child focus; one
  failed during Tcl initialization. Mapping only initially hidden windows fixes
  the test setup without restoring focus or weakening assertions. The next run
  had **17 passed, 2 failed in 10.40 seconds**, both before widget creation
  (`tk.tcl` read failure and missing `tcl_findLibrary`).
- Bounded lifecycle diagnosis: all **80 attempts passed**, comparing four fresh
  child groups with capture guards off/on and pre-creation collection off/on.
  Receipt: `.grok/tk-lifecycle-20260926T172140695312Z.json`. This narrow withdrawn
  native-widget probe did not reproduce the issue; it does not prove collection
  or guards are unrelated in a full pytest/application lifecycle.
- The combined five-module suite with `-s` (pytest output capture disabled)
  passed **69 tests in 29.04 seconds, no skips**. After visual review reduced the
  review heading to the same section-title style as file/decoder windows, the
  identical final-source command passed **69 tests in 24.57 seconds, no skips**.
  All assertions remain intact. Output-capture interaction is a hypothesis, not
  a demonstrated cause; the ordinary captured-output runtime gate remains open.
- All **19 final candidate images** completed under
  `artifacts/screenshots/desktop-auxiliary-final`, preserving the before-state
  and first candidate directories. Inspected standard and 2× compact file,
  decoder and review views. Fixed actions fit; offscreen file Model settings/
  More formats intentionally live in scrollable content and are focus-revealed
  by the real-key regressions. Native dialogs, screen readers and physical DPI
  are still not certified. No package, release or real workflow was run.

### Host Tcl/output-capture diagnosis

The later probes isolate the intermittent startup failure from Utterleaf source:

- `python -B -m pytest .grok/test_tk_bare_fd_probe.py --capture=fd -o addopts='' -p no:cacheprovider -q`:
  **18 passed, 2 failed in 3.31 seconds**. Failures occurred reading installed
  `tk.tcl` and `init.tcl` while constructing bare Tk roots. The probe imports no
  Utterleaf module and applies no capture guards. No previous roots were alive,
  and no collection ran during a failing constructor.
- The identical probe with `--capture=sys`: **20 passed in 3.41 seconds**.
  Receipts: `.grok/tk-bare-fd-probe-fd-20260926T173244283700Z.json` and
  `.grok/tk-bare-fd-probe-sys-20260926T173252686632Z.json`.
- A guarded native-widget probe independently reported **18 passed, 2 failed**
  under FD capture and **20 passed** under sys capture. Before the recovery
  changes, the 19-case auxiliary layout module passed with sys capture too.

This establishes a host test-runtime interaction (Python 3.14.6, Tk 8.6.15,
pytest 9.1.1), not its exact native-handle cause. The earlier lazy-loaded Tab
failure is not automatically explained by these startup results. Current UI
verification explicitly uses `--capture=sys`, preserving assertions and captured
Python output. No product GC/preload/retry workaround or global pytest setting
was added. Ordinary FD-capture compatibility and native platform acceptance
remain open; passing sys-capture runs do not claim those gates are fixed.

### Initial baseline and shell

- Branch base `be4f117` matches remote `main`, checked with `git ls-remote`.
- `python -m pytest tests/test_settings_ui.py tests/test_settings.py tests/test_settings_instance.py tests/test_config.py tests/test_theme.py tests/test_brand_assets.py tests/test_indicator.py tests/test_capture_settings.py -o addopts='' -p no:cacheprovider -q`:
  **103 passed in 47.40 seconds**.
- After final summary-heading wrapping and key-event assertions,
  `python -m pytest tests/test_settings_ui.py -k 'dictation_primary_controls or navigation_shortcuts or wide_page or landing or presence' -o addopts='' -p no:cacheprovider -q`:
  **12 passed, 35 deselected in 10.60 seconds**. These checks exercise native Tk
  event delivery and 1×/1.5×/2× text scale, not physical monitor DPI transitions.
- Corrected baseline: **39 Settings images** at standard, compact, and wide
  dimensions, plus **eight indicator images**. The native indicator passed three
  create/update/quit cycles, including region geometry and class cleanup.
- Candidate Settings images are generated separately under
  `artifacts/screenshots/desktop-candidate`. Reviewed standard/compact/wide
  Dictation, Help, microphone recovery, model state, and post-dialog save/reset
  examples. The full before-state description remains in the baseline document.
- Independent review found no blocking issues in the landing summary, guarded
  one-shot presence check, draft-preserving navigation, or scale-aware width cap.
  The final 39-image candidate capture completed after the wrapping adjustment.
  macOS shortcut delivery and physical mixed-DPI behavior remain unverified.
- No packaging, microphone capture, model download, or user-preference write was
  performed by the capture scripts. The next acceptance work stays listed above.

### Recovery follow-up

- `python tests/capture_settings.py --output artifacts/screenshots/desktop-candidate`:
  **40 images completed**, including the added device-refresh failure. Inspected
  microphone success/failure, device-refresh failure, and model-download failure;
  primary copy and Details controls fit the standard layout.
- `python -m pytest tests/test_settings_ui.py tests/test_capture_settings.py tests/test_model_setup.py tests/test_audio.py -o addopts='' -p no:cacheprovider -q`:
  **133 passed in 53.41 seconds, no skips** after review corrections. Tests cover worker overlap, selection
  invalidation, explicit/bounded Details, retry/cancel/close, named-device
  preservation, download consent, and Details focus/visibility at compact and
  1×/1.5×/2× Tk text scales. Audio/download operations are mocked.
- Independent review identified a late-cancel race in the download completion
  callback. Successful worker completion now takes precedence over a later
  Cancel click; a regression reproduces the queued-callback window. The reviewer
  confirmed the correction and found no remaining blocking issues.
- `git diff --check` passed. Original mixed checkout remains unchanged except
  for its pre-existing unrelated Android plan.
- Native Details dialogs, physical device recovery, macOS/Linux UI, and native
  enumeration timeout handling are not established by these source checks.

### Last-reported status follow-up

- `python tests/capture_settings.py --output artifacts/screenshots/desktop-candidate`:
  **43 images completed**, including the three new operational-state snapshots.
  Inspected Listening and Needs attention on Dictation; labels remain readable
  and explicitly last-checked. Capture uses synthetic replies and no live audio.
- With `PYTHONPATH` scoped to this checkout,
  `python -m pytest tests/test_app_status.py tests/test_app.py tests/test_ipc_security.py tests/test_settings_ui.py tests/test_capture_settings.py tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py -o addopts='' -p no:cacheprovider -q`:
  **174 passed in 69.66 seconds, no skips**. The status socket test uses a
  temporary authenticated loopback listener, not the user's running app.
- Independent product review found no blocking authentication, privacy,
  compatibility, or polling changes. Last-reported presentation remains a
  snapshot, not atomic readiness or physical-device acceptance.
- Full desktop regression with `PYTHONPATH` scoped to this checkout:
  `python -m pytest -o addopts='' -p no:cacheprovider -ra -q`:
  **1,690 passed, 14 skipped in 122.33 seconds**. Skips comprise 11 decoder
  checks requiring an explicitly verified FFmpeg binary, one unavailable local
  public speech fixture, one Windows symlink-privilege check, and one explicitly
  enabled Windows clipboard-isolation acceptance check. No Tk checks skipped.
- `git diff --check` passed. No package or release was created; physical input,
  actual engine readiness, assistive technology, mixed DPI, and measured idle
  performance remain separate gates.

### Keyboard page-scrolling follow-up

- `python tests/capture_settings.py --output artifacts/screenshots/desktop-candidate`:
  **43 images completed**. Inspected the updated Help keyboard reference; its
  instructions fit without clipping. No live microphone or preference writes.
- With `PYTHONPATH` scoped to this checkout,
  `python -m pytest tests/test_settings_ui.py -k 'reference_page_keyboard or page_scroll' -o addopts='' -p no:cacheprovider -q`:
  **12 passed, 62 deselected in 4.80 seconds**. Real Tk key events cover compact
  1×/1.5×/2× text scaling; native editing, modifiers, focus, drafts, bounds,
  closed/other windows, and a pending idle reset have regression coverage.
- The idle-reset regression first reproduced visible scroll loss in both
  Page Down and End cases (**2 failed, 2 passed**). Accepted page scrolling now
  cancels that pending reset; rejected native or modified keys leave it intact.
- Final focused regression, with `PYTHONPATH` scoped to this checkout:
  `python -m pytest tests/test_settings_ui.py tests/test_capture_settings.py tests/test_settings.py tests/test_settings_instance.py -o addopts='' -p no:cacheprovider -q`:
  **101 passed in 64.30 seconds, no skips**. The initial sandbox run could not
  access pytest's temporary directory; the approved rerun resolved the setup
  errors. No product failure was hidden by a skip.
- Independent review confirmed the idle-reset correction and found no remaining
  blockers. `git diff --check` passed. Native macOS/Linux key delivery, screen
  readers, oversized-editor caret reveal, and physical DPI remain open; the full
  desktop suite was not rerun for this Settings-only slice.

### Oversized-editor and model-presentation gauntlet

- Oversized-editor validation/focus first reproduced six failing scale cases.
  Following the insertion line fixed those; held Down-arrow testing then exposed
  three more failures when no KeyRelease arrived between repeats. A local
  post-class KeyPress handler now covers held-key movement as well as release
  and pointer input. No new timer or global input hook was added.
- The combined 29-keyboard-case run initially reported **26 passed, 3 failed**:
  the read-only report's native Tab command failed with `invalid command name
  "tk_focusNext"`. Its three cases passed alone; the identical combined run then
  passed **29 tests in 12.83 seconds**. This intermittent Tcl lazy-loading failure
  is unresolved, not erased by the repeat. No assertions or bindings were weakened;
  a recurrence requires Tcl command/index/error-state diagnostics before any repair.
- Pure model-presentation checks: **21 passed in 0.09 seconds**. Exact catalogue
  names and factual language support are shared; unknown identifiers remain
  editable but are not echoed into the primary summary.
- Initial compact model checks: **17 passed, 2 failed**. At 1.5×/2× Tk text scale,
  pickers were narrower than requested and Cancel download could shrink to one
  pixel. Responsive label/picker and action stacking fixed the issue. The extended
  compact→wide→compact regression now passes with the rest of that module:
  **19 passed in 17.30 seconds**, retaining drafts and actual keyboard focus.
- Independent reviewers found no blockers in the final caret, naming/details,
  consent/cancellation, or responsive-layout deltas.
- Consolidated desktop regression, scoped `PYTHONPATH`:
  `python -m pytest -o addopts='' -p no:cacheprovider -ra -q`:
  **1,760 passed, 14 skipped in 203.94 seconds**. No Tk failure or skip occurred.
  The 14 prerequisites remain the same: 11 verified-FFmpeg codec cases, one
  unavailable local JFK fixture, one Windows symlink privilege, and one opt-in
  clipboard-isolation acceptance. This run preceded the final sidebar fix below.
- The new sidebar regression reproduced clipped optional copy at 2× text scale:
  **1 failed, 2 passed** (61 pixels available for 70 requested). Showing the
  tagline only when its full natural height fits, without changing navigation,
  made all three compact→tall→compact cases pass. Independent review is clear.
- Final candidate capture: **46 images completed** after the sidebar fix.
  Inspected ordinary compact Dictation, model installed/error states, oversized
  validation, and 2× compact Engine overview/Cancel focus. Navigation and footer
  actions remain available; the optional tagline is no longer partially clipped.
- Final-source focused regression, scoped `PYTHONPATH`:
  `python -m pytest tests/test_settings_ui.py tests/test_capture_settings.py tests/test_settings.py tests/test_settings_instance.py tests/test_model_setup.py tests/test_model_presentation.py tests/test_model_presentation_ui.py tests/test_sidebar_layout.py -o addopts='' -p no:cacheprovider -q`:
  **173 passed in 98.85 seconds, no skips**. This covers keyboard/editing,
  model selection/details/consent, compact reflow, capture isolation, persistence,
  cancellation, and defaults reset. The earlier intermittent Tcl failure did not
  recur; its cause remains unresolved and recorded above.
- `git diff --check` passed. No package/release, microphone capture, model
  download, or personal-preference write was performed. The mixed recovery
  checkout remains untouched apart from its pre-existing unrelated Android plan.

### Bounded Settings performance receipt

- Reviewed local harness: `python -B .grok/measure_settings.py`. All six fresh
  children completed without guard violations. Raw receipt:
  `.grok/performance/settings-20260926T164020122906Z.json` (ignored, retained).
- Windows build 26200, AMD Ryzen 7 5800X3D (8 cores/16 logical CPUs), about
  32 GiB RAM, Python 3.14.6, Tk 8.6.15, Tk scaling 1.334; 960×780 windows.
  Three alternating baseline/candidate pairs each retained the real Settings
  poll during a 12-second idle interval. No audio/engine/network work occurred.

| Measure | Baseline `be4f117` | Candidate |
| --- | --- | --- |
| Source import + construction/layout, median (range) | 1,645 ms (1,061–6,325) | 1,284 ms (1,109–1,400) |
| Idle process CPU per 12 seconds, median (range) | 15.625 ms (0–31.25) | 15.625 ms (0–46.875) |
| Idle use of one logical CPU, median (range) | 0.130% (0–0.260%) | 0.130% (0–0.390%) |
| Private commit at ready and after idle, median | 35,713,024 bytes | 35,753,984 bytes |
| Working set after idle, median | 54,726,656 bytes | 54,808,576 bytes |

The short samples show low Settings idle CPU and a 40 KiB median private-commit
difference; private commit did not grow within any idle sample. Retain the
6.3-second baseline outlier: startup variance is too large for a speedup claim.
CPU timing is visibly quantized; three samples do not establish a tail budget
or sustained-growth behavior. The comparison uses in-memory source compilation,
current shared dependencies/assets, and disabled background checks. It does not
complete whole-app/tray/recognition performance or Milestone P. Source hashes
and all individual samples remain in the receipt; assets/transitive modules were
held fixed but are not exhaustively hashed by this local harness.
This measured candidate precedes the final sidebar-tagline fit correction; that
small later layout change has separate regression/capture evidence, not a fresh
timing claim. Do not present this receipt as exact-final-source performance QA.
