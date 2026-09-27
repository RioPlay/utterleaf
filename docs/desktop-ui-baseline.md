# Desktop UI baseline

[Desktop roadmap](desktop-roadmap.md) ·
[Modernization plan](plans/active/desktop-modernization.md) ·
[Interface guide](interface.md)

Recorded September 26, 2026 before product UI changes on
`feat/desktop-modernization`, using desktop source from `main` at `be4f117`.
This record describes that starting UI; it is not a claim about every packaged
build or physical device. Later landing/shell changes are recorded in the
desktop roadmap and have separate candidate captures.

## Evidence boundary

The Settings baseline uses the real Tk widgets, theme, packaged artwork, labels,
focus behavior, and layout. Dynamic device/model/save states are staged by the
capture harness so it never opens a microphone, downloads a model, contacts a
service, or writes personal configuration.

Those captures answer “what does this source state look like?” They do not prove
that a device transition, model operation, save failure, installed build,
screen reader, physical scaling configuration, or multi-monitor transition works.
Unit, integration, and native acceptance evidence remain separate.

## Current application shape

Utterleaf is tray-first. There is no separate Home or dashboard window. Opening
the visible application opens one Settings window with five stable destinations:

| Destination | Primary user goal | Current important states |
| --- | --- | --- |
| Dictation | Learn the shortcut, choose/test a microphone, control speech stopping and feedback | device list empty, named device missing, opening, listening, low input, audio detected, capture error, unsaved preference |
| Vocabulary | Control cleanup and local replacements, preview results | empty/sample vocabulary, invalid line, unsaved text |
| Voice commands | Learn deterministic local punctuation, list, and correction commands | reference content only |
| Speech & privacy | Select/download a speech model, choose processing, review local/clipboard behavior | missing, incomplete, downloading, cancelled, installed-files, error, unsupported |
| Help | Recover defaults, back up settings, inspect app/device state, find logs/artwork | tray app running/unavailable, diagnostics success/error, staged reset |

The footer keeps Save changes and Close visible while page content scrolls.
Edits are staged in the single existing window. Close asks before discarding;
Save validates, applies asynchronously, reports partial saves, and returns to the
invalid field. Defaults are staged for review and do not delete models or
vocabulary.

## Navigation and shell

- The sidebar is fixed and does not change with the task or runtime state.
- Page headings are task-led. Utterling is decorative; instructions remain text.
- The ordinary landing destination is Dictation, not an operational overview.
- Local/no-account language remains visible in the sidebar.
- The content canvas expands with the window and has no explicit readable maximum
  width. Wide-window behavior is now captured for review rather than assumed.
- Minimum size is 760 × 560. Source tests also exercise 770 × 655 and enlarged Tk
  text scaling, but physical display scaling and mixed-monitor DPI remain open.

## Operational state language

The product currently has several related vocabularies. Modernization must map
them at presentation boundaries instead of renaming stable engine state.

| Concept | Tray/brand | Floating indicator/detail | Baseline interpretation |
| --- | --- | --- | --- |
| Ready | Ready / `idle` | pill hidden | Available; no audio capture. A future landing surface must make readiness visible without inventing an idle overlay. |
| Listening | Recording / `recording` | Listening | Microphone capture is active. “Listening” is the preferred visible label; Recording remains an internal/asset term where required. |
| Processing | Processing / `busy` | Loading or Transcribing | Opening a device, loading a model, or recognizing speech; show the specific detail. |
| Error | Needs attention / error override | concrete failure such as Microphone unavailable | Lead with the problem and next action rather than the generic state. |

Utterling expressions do not define operational state. The leaf/status treatment
and visible text do.

## Device baseline

Current source:

- Shows human-readable input names and a System default choice.
- Preserves a missing named selection and explains reconnect/choose/Save; it does
  not silently switch to the system default.
- Provides Refresh and a five-second Test with opening, listening, meter, low
  input, success, stop, and error text.
- Has recovery copy for permission denial, a busy device, invalidation,
  unsupported formats, disconnects, and interrupted capture.
- Structured PortAudio channel/rate/sample-format/I/O failures now use specific
  format guidance in both Settings checks and runtime capture. The four core
  codes supplement native WASAPI handling; unknown/malformed errors are not
  classified by matching raw exception text. Retry and fallback behavior are
  unchanged.

Open gaps:

- A renamed device is currently indistinguishable from a removed device because
  the saved identity is its display name.
- Technical identifiers/details and explicit default-device change notices are
  absent.
- Hotplug, Bluetooth, permission, exclusive-use, sleep/resume, and default-switch
  behavior need physical-device acceptance.
- A tray/indicator error does not yet provide a direct Choose microphone action.

## Speech-model baseline

Current source distinguishes Missing, Incomplete, Installed files, and Unsupported
guided setup; a requested download can be cancelled and retried. Download consent
is one-time and does not silently alter the persistent network preference.

“Installed” explicitly means required files were found locally; model loading was
not tested. The surface exposes raw model/backend terminology and does not yet
provide a catalogue with friendly names, measured recommendations, exact size,
Remove, or Details. Download failure remains inline copy rather than the reusable
Problem / Impact / Recovery / Details pattern.

## Error, empty, and recovery baseline

Useful empty states already exist for no microphones and missing/incomplete
models. Help contains defaults, backup/import, diagnostics, logs, GPU guidance,
and artwork. The tray retains two-minute copy/forget recovery.

Important errors are not yet one reusable component. Some operations place an
exception's string directly into a dialog or status line. A later recovery slice
must provide:

1. Problem — what happened.
2. Impact — which capability is unavailable.
3. Recovery — the safest next action.
4. Details — optional technical context.

## Tray, notifications, and shortcuts

- The tray is the operational surface and shows current status plus Settings,
  recent-dictation recovery, optional indicator, file/vocabulary/log tools, and
  Quit.
- It does not currently expose tested start/stop control or a microphone picker.
- There is no routine notification subsystem, which is consistent with quiet
  operation. Model completion or a critical action may justify a later,
  separately accepted notification.
- Settings supports platform Save, Escape/Close, normal focus movement, and
  explicit Text-widget Tab handling. There is no settings search or complete
  discoverable shortcut reference.

## Accessibility and performance baseline

Source evidence covers visible focus, logical focus movement, hidden-page
exclusion, non-color tray marks, textual state, and palette contrast. Windows UI
Automation has previously exposed many visually labelled controls as unnamed
panes; screen-reader acceptance is open.

The original baseline had no measurement establishing startup latency, idle CPU/memory, tray
overhead, or recognition p50/p95. Model warmup is background work, but that alone
does not establish quiet idle behavior. Performance measurements must precede a
completed Milestone P claim.

## Deterministic capture inventory

Activate the shared desktop Python environment and run from the owning checkout:

```powershell
$py = (Get-Command python).Source
$env:PYTHONPATH = (Get-Location).Path
& $py tests/capture_settings.py
& $py tests/capture_indicator.py --output artifacts/screenshots/desktop-indicator-recovery
```

Settings output is ignored under `artifacts/screenshots/desktop-baseline/`.
The indicator requires a new directory and refuses to overwrite earlier captures.
After changing product UI, use `--output artifacts/screenshots/desktop-candidate` to preserve
the local before images. The command always captures the currently checked-out
source; the inventory below names generated files, not every file that might
already exist in the directory from an older run.

| Group | Files |
| --- | --- |
| Primary pages | `page-*-standard.png` and `page-*-lower.png` for all five destinations |
| Layout | `layout-dictation-compact.png`, `layout-dictation-wide.png` |
| Devices | `device-none.png`, `device-selected-missing.png`, `device-refresh-error.png`, `microphone-opening.png`, `microphone-listening.png`, `microphone-low-input.png`, `microphone-ready.png`, `microphone-error.png` |
| Audio configuration recovery | `microphone-unsupported-format.png`, `microphone-unsupported-compact-text-scale-2x-focused.png` |
| Models | `model-missing.png`, `model-incomplete.png`, `model-downloading.png`, `model-cancelled.png`, `model-installed.png`, `model-error.png` |
| Synthetic large-text layout | `engine-compact-text-scale-2x-synthetic-overview.png`, `engine-compact-text-scale-2x-synthetic-cancel-focused.png` |
| Save/apply | `save-clean.png`, `save-unsaved.png`, `save-in-progress.png`, `save-partial-failure-post-dialog.png`, `save-invalid-vocabulary-post-dialog.png`, `reset-staged.png` |
| Empty vocabulary | `vocabulary-empty.png` |
| Oversized editor | `vocabulary-oversized-validation-synthetic-post-dialog.png` |
| Help | `help-app-running.png`, `help-app-not-running.png` |
| Last-reported app status | `app-status-ready.png`, `app-status-listening.png`, `app-status-processing.png`, `app-status-attention.png` |
| Native Windows indicator | `indicator-app-opening-microphone.png`, `indicator-app-listening-hold.png`, `indicator-app-transcribing.png`, `indicator-app-microphone-error.png` |
| Renderer stress | `indicator-renderer-stress-compact-listening.png`, `indicator-renderer-stress-expanded-listening.png`, `indicator-renderer-stress-long-listening.png`, `indicator-renderer-stress-compact-again.png` |
| Brand reference | `guide-*.png` for tray states, badges, cutouts, Utterling, and wordmark |

The original before-state set contains 39 Settings images. The recovery slice
adds `device-refresh-error.png` for a 40-image candidate set; its raw synthetic
error stays behind the user-requested Details action. `microphone-ready.png`
retains its historical filename but now says only that audio was detected and
the microphone check passed, not that dictation or the speech model is ready.
The operational-status slice adds three last-reported-state images for a
43-image candidate set. Those use synthetic fixed protocol replies, not live
capture, transcription, or device acceptance.
The editor/model follow-up reaches **46 candidate images**: one synthetic
40-line editor with validation on line 75 and two compact Engine views at 2× Tk
text scaling, including focus-revealed Cancel download. These are not physical
DPI tests. Model names/purpose are human-readable; explicit model information and
download-error details remain separate. The large-text captures exposed and now
verify the correction for a partially clipped sidebar tagline: navigation stays
stable, and the optional tagline is shown only when it fits completely.

The applied-model readiness follow-up adds `app-status-ready.png` for a
**47-image candidate set**, captured in `desktop-readiness-candidate`. Its synthetic
reply exercises “Ready · applied
speech model loaded” and the distinction between applied app settings and the
selected draft's local-file status. It does not load a real model or test a
microphone. The active plan records exact checks and capture evidence for each
source stage. Earlier 39/40/43/46-image
receipts retain their original scope.

The format-recovery follow-up adds ordinary and compact 2× microphone format
errors, reaching **49 images** in `desktop-audio-format-candidate`. Both use a
synthetic structured driver exception through the production completion callback;
no microphone is opened. Primary copy, focused Details and the fixed footer were
inspected. `desktop-indicator-audio-format` contains **12 native indicator
scenarios**, each checked through three lifecycles; the new two-line recovery
caption fits completely. These checks do not prove physical-driver recovery.

The save-error captures show the form after the native error dialog is dismissed;
the modal dialogs themselves remain a separate visual acceptance item. Production
callbacks supply the captured state and text, with side effects replaced throughout
the capture run. Each dynamic scenario starts from an isolated Settings window.

The indicator command is Windows-only and repeats create/update/quit three times
to retain its lifecycle and rounded-region checks. Ready is intentionally absent
from the overlay inventory because the production pill is hidden at rest; the
Tray states guide records the Ready artwork. Renderer-stress images use synthetic
captions to check long text, dwell, and expanded-to-compact transitions; they are
identified separately from real app scenarios.

The state-language follow-up records **11 indicator images** in the separate
`desktop-indicator-recovery` directory. It adds a real model-failure caption,
shared text-action recovery caption, and caption-free model-error stress case.
All 11 scenarios passed three native lifecycles, with measured headline bounds,
rounded regions and class cleanup. The longer model heading also exposed a
caption-free Tk clipping bug; Tk now measures the actual heading font before
choosing width. Source tests cover exact headings and all text bounds. Windows
testing of the fallback renderer does not certify native macOS/Linux behavior.

## Auxiliary before-state — September 26

`python tests/capture_auxiliary.py` recorded **19 synthetic images** in the new
`artifacts/screenshots/desktop-auxiliary-baseline` directory before changing
file transcription, decoder setup or automatic-dictation review. Its completed
manifest records actual/requested window dimensions, Tk scaling/version, source
hashes, and action bounds. The directory is exclusive; reruns cannot overwrite it.

- File transcription: empty, selected, opening, recognizing, cancelling,
  cancelled, result, no speech, decoding error and export error; also compact 2×.
- Decoder setup: no selection, selected executable, selection error and compact 2×.
- Review: Insert available, Copy only, compact and compact 2×.

The actual production transitions/renderers are used, with worker starts held,
synthetic input/output streams, and external actions intercepted. No recognition,
model loading, network, export, clipboard mutation or user preference access runs.
Native file/confirmation dialogs are intercepted, not visually certified.

The before-state establishes three reproducible layout failures at 2× Tk text
scaling. File actions start at y=702 in the 760×560 window; decoder Done starts at
y=853 in the 560×500 window; review actions start at y=323 in the 480×320 window
and Insert shrinks to six pixels. These are source layout failures, not evidence
about physical DPI. The responsive auxiliary follow-up must keep the existing
minimum sizes, preserve workflows and make actions/content keyboard-reachable.

The follow-up preserves those sizes and has a separate **19-image final set**
under `artifacts/screenshots/desktop-auxiliary-final`. Its fixed action rows wrap
without shrinking buttons, and long content scrolls. Model settings and More
formats can be below the initial file viewport at 2×; regression tests reveal
them on keyboard focus. The review heading now uses the same section-title role
as the other auxiliary windows. Final source checks passed 69 cases with pytest
output capture disabled; ordinary captured-output Tcl startup failures remain
an explicitly unresolved runtime gate in the active plan.

The recovery follow-up adds two mapped-window, compact 2× failure captures for
**21 images** in `artifacts/screenshots/desktop-auxiliary-recovery-final`, with
the first recovery candidate preserved separately. File failures now reveal the
whole explanation and Details action, not just the headline; the export preview
stays available. Decoder setup keeps explicit trust consent and offers bounded
technical details. The completed manifest matches all six surface/helper source
hashes and the capture harness. **142 final-source focused tests passed using
`--capture=sys`, with no skips**, including real keyboard access and automatic
reveal at three scales. Dialog internals, physical devices and screen readers
remain separate acceptance gates.

## Backup preview follow-up — September 26

Eight synthetic before images and a source-hashed manifest are preserved in
`artifacts/screenshots/desktop-backup-before-20260926`. The compact 2× baseline
reproduces a 364-pixel Apply action squeezed to 229 pixels, choice labels outside
the viewport, and a clipped vocabulary disclosure. Actual key tests also
reproduce trapped Shift+Tab; an independent mouse check later catches ancestor
focus scrolling an already-visible checkbox during its press.

The reviewed source uses existing native wrapping/traversal helpers, keeps the
full vocabulary disclosure inside its checkbox and ignores container focus
events. Eight final captures in `desktop-backup-reviewed-20260926` have complete
action/choice bounds and matching source/harness hashes; the earlier candidate
is retained separately. **41 focused tests passed without skips**, including
compact→wide→compact at three text scales, real Tab/Shift+Tab, first-click
stability, cancellation, capture guards and existing backup behavior. Import
review/storage/consent rules are unchanged. Capture reads only synthetic bytes
and blocks writes; native picker/confirmation interiors remain unverified.

## Icons & artwork follow-up — September 26

Nine before images in `artifacts/screenshots/desktop-artwork-before-20260926`
record all five reference tabs and compact 2× states. At the existing 720×540
minimum, Export/Close were unmapped and tab labels truncated. Page-key tests
also reproduced missing scrolling. Two before-source 1.5× layout runs stalled
in Tk update; their exact cause remains unproven, and no completed red-suite
count is claimed.

Nine reviewed captures in `desktop-artwork-reviewed-20260926` retain those
states after fixed actions, concise stable tabs, wrapped text and local page
keys. Export failure is inline with optional bounded Details. All mapped-action,
row-width and tab-label bounds pass, with matching source/helper/harness hashes.
Compact 2× error content retains a 103-pixel viewport after review-driven copy
and padding corrections. **21 focused cases passed without skips**, including
three-scale roundtrips, keyboard keys, cancellation/retry and late-close safety.
The capture harness blocks real exports, native dialogs, preferences, microphone,
network and clipboard work. Export consent/asset generation are unchanged;
native dialog interiors, assistive technology and physical DPI remain unverified.

## Diagnostic report follow-up — September 26

Nine synthetic before images in
`artifacts/screenshots/desktop-diagnostics-before-20260926` record empty/success,
failed device/GPU checks, retained-report expectations and report-save failures.
The original callbacks erase the last successful report on failure; picker errors
escape handling, and write failures use an intercepted raw-error modal.

Nine reviewed images in `desktop-diagnostics-reviewed-20260926` show inline
problem/impact/retry copy with optional Details. Previous report content survives
check and save failures. Both compact 2× error states keep the entire explanation
and Details inside the actual scroll viewport, with footer actions visible.
All source/helper/harness hashes match; no raw synthetic error appears in primary
copy, and no native dialog or uncaught error occurs in the reviewed set.

Captures explicitly align a synthetic viewport; they are not proof of automatic
reveal. **48 focused tests passed without skips**, separately covering actual
three-scale reveal/focus, first mouse-click stability, saved-configuration use,
operation overlap, late callbacks, preview/draft preservation, export snapshots,
cancellation and guard behavior. No real device probe, report write or personal
preference access occurs. Hardware-report source is unchanged; 23 existing
hardware tests also pass. Native dialogs, screen readers and physical-device
acceptance remain open.

The final integration refresh is **55 images** in
`artifacts/screenshots/desktop-diagnostics-settings-20260926`. Post-capture hashes
and scale restoration match; **195 final-source Settings/recovery regressions
passed without skips**. Earlier screenshot directories remain historical evidence.

## Settings-save recovery follow-up — September 26

Ten guarded before images in `artifacts/screenshots/desktop-save-before-20260926`
record all three persistence failure stages, unknown progress, worker-start
failure, full/partial save followed by notification failure, validation and two
compact 2× states. Intercepted alerts record the original raw technical messages.
The start failure escapes and leaves Save disabled; notification failures lose
confirmed full/partial progress. No real settings, vocabulary, startup or IPC
operations occur.

Ten reviewed images in `desktop-save-reviewed-20260926` retain those scenarios.
Safe native alerts explain progress and recovery, with an error-only **Save
details…** action for bounded technical text. All drafts survive. Full local
success advances the captured baseline even when notification fails; partial
failure retains the previous baseline. All callbacks unlock and no uncaught
errors occur. Six source, four helper and harness hashes match, and scales are
restored. Compact 2× status/actions fit at natural dimensions and all five
destinations fit inside the actual sidebar, not merely the root window.

**34 UI tests** and **13 capture-harness tests** pass without skips. These cover
real held worker/queue and `apply_form` paths with synthetic sinks, persistence
order, partial/full notification errors, validation, staged reset, drafts,
stale/closed callbacks and pointer/keyboard behavior. Twelve layout roundtrips
cover four failure states at 1×/1.5×/2×. Independent review found a retry-focus
defect; Ctrl+S from Details now moves focus to enabled Close while saving and
after success. The initial run retained **31 passes and two failures**: that
defect and one stale expected status string, both corrected before final checks.
Native alert interiors and screen-reader/physical-platform behavior are not
certified by intercepted dialogs or screenshots.

The final combined Settings/search/model/report/save regression passed **290
tests in 192.20 seconds without skips**. Separate configuration/privacy/boundary/
startup/presentation checks passed 81; one existing Linux startup symlink test
was skipped for unavailable Windows symlink privilege. This is not native
platform clearance or real storage-failure evidence.
The latest integration refresh is **55 images** in
`artifacts/screenshots/desktop-save-settings-20260926`. Clean and partial-save
views were inspected; the ordinary footer stays unchanged. All six reviewed
save-source hashes still match after that capture.

## Settings check-dispatch follow-up — September 26

Six before states in
`artifacts/screenshots/desktop-mic-dispatch-before-framed-20260926` record the
real microphone Refresh/Test and app-status handlers when thread startup fails,
at standard and compact 2× sizes. All three previously leave busy flags/controls
stuck and let the error escape. The original label-only framing remains in
`desktop-mic-dispatch-before-20260926`; corrected framing includes retry actions.

Six reviewed states in `desktop-mic-dispatch-reviewed-20260926` show safe,
operation-specific retry copy and restored controls. Drafts/baselines survive;
all busy flags clear, the picker remains readonly, and no uncaught error or
native dialog appears. Mic recovery/Details/retry groups use 248 pixels within
the compact 414-pixel viewport; the app-status group uses 189. Footer/navigation
fit. Five source/four helper/harness hashes match, and all text scales restore.
No real microphone, enumeration, IPC, configuration or clipboard action runs.

These screenshots deliberately frame feedback and are not automatic-reveal
proof. **26 UI tests** separately exercise actual worker dispatch, full startup
with both background checks failing, retry, Stop/input cancellation, closed
callbacks and three-scale keyboard/pointer reachability. Tab-away/return reveals
the full microphone message and Details after reflow. Home/Page Down expose the
whole status paragraph with at least one rendered-line overlap; focus remains
on its control and traversal returns to an enabled visible retry action.
**11 harness checks** pass. The initial seven targeted failures reproduced the
dispatch defect. A later three-failure layout run retained overstrong
automatic-reflow/Home-only assumptions; the revised tests prove real keyboard
access without weakening privacy, natural bounds, draft or action assertions.
Automatic resize reveal and full native/accessibility acceptance are not claimed.
The final combined Settings/search/save/dispatch regression passed **208 tests
in 171.53 seconds without skips** on the reviewed source. No unrelated historical
capture set or package was rebuilt for this local completion-path change.

## Model-management follow-up — September 26

The authoritative before set is
`artifacts/screenshots/desktop-model-management-before-worker-20260926`:
ten standard/compact 2× states at Settings hash `ce9fd4a1…`. It reproduces the
worker-start exception and stuck download controls. An earlier closure-mocking
capture is retained but superseded by this corrected receipt.

`desktop-model-management-reviewed-20260926` contains **20 reviewed images**,
including local inventory installed/incomplete/empty/read-error/start-failure
states. Eight source, five helper and harness hashes match; all 20 scales restore,
drafts/baselines stay unchanged, and no unexpected work or escaped errors occur.
Settings hash is `2226b8827e62dc60a787ce1c19040cca981eedd831fa5358e2149c90059af4b5`.
The independent final evidence/source review found no blocking issue. All **55
existing Settings images** were also refreshed in
`desktop-model-inventory-settings-20260926` on the unchanged source; that older
harness emits no manifest.

The normal-size groups fit. Compact 2× panels require scrolling: installed
inventory is 779 px and its error group 1,000 px in a 414 px viewport.
Inventory recovery plus Details fits locally (252/215 px); download start/error
groups are 445/477 px, placing Details below the initial frame. No full-group-fit
or automatic-reveal claim is made. Actual Tab/Shift-Tab/Space and pointer checks
cover the compact/wide round trip, including Settings' own focus reveal and
opening download-error Details at three scales. Native dialogs are intercepted,
not visually or accessibility certified.

The grouped model/settings/privacy/boundary and UI regression covers **398
distinct passing tests without skips**. The strengthened final integration
module rerun passed **25 in 19.06 seconds**. The inventory remains explicitly
refreshed and read-only; no real store scan, download, model load or preference
write occurs in these guarded captures. The active plan retains exact commands,
timings and hashes. Runtime model identity, safe removal/update, physical-device,
screen-reader and whole-application performance gates remain open.

## Loaded model for applied settings follow-up

Dictation and Help now pair their last-checked operational status with a fixed
human-readable loaded-model name. This requires matching successful runtime
load metadata for the captured applied preferences. It is not file inventory,
an unsaved draft or an already-running take's engine identity. Custom identifiers
and paths become “Custom model”; missing proof says “not confirmed.” One
authenticated versioned reply carries both claims; the legacy status command
is unchanged. An explicit older-server response alone allows fallback.

The two pre-change images in `desktop-loaded-model-before-20260926` retain
Settings hash `2226b882…`. The first 12-image candidate in
`desktop-loaded-model-reviewed-20260926` and its 55-image companion
`desktop-loaded-model-settings-20260926` are intermediate evidence at Settings
hash `8d3b371b…`, not the final layout. Visual review found an unnecessarily
narrow status text column at 2×. The follow-up stacks both summary actions below
their text at compact/larger-text widths and restores side-by-side layout on
wide windows. The dedicated capture framing now includes the last-check heading
when the group fits; it does not establish automatic reveal.

Final-source focused UI/capture-fixture tests passed **43 in 39.02 seconds**
without skips or Tcl timer noise. Native key tests cover full status text in
Dictation and Help, compact/wide/compact layouts at 1×/1.5×/2×, restored focus,
stable drafts, both summary rows and controls. Full-suite and final-capture
receipts are in the active plan. The first dedicated final set and its companion
predate the later section-reset source change and remain intermediate evidence.
The current source-hashed set has 12 images in
`desktop-loaded-model-source-final-20260926`; the companion refresh has 56 images
in `desktop-section-reset-settings-final-20260926`, including the inspected
staged Recording feedback reset. Its manifest records the current Settings hash
`6bb4ec8e…` and capture helper `8592d1a8…`. Physical-DPI and screen-reader
acceptance remain separate.

## Baseline conclusion

The later Settings-search slice has **55 images** in
`artifacts/screenshots/desktop-search-final`, retaining the prior baseline and
candidate directories. Six added states cover empty/results/no-match search,
disabled-setting prerequisite guidance and compact 2× results/prerequisites.
The static index, shortcut/caret/focus behavior and all 26 destinations at three
text scales have source tests. The combined regression passed 181 cases and the
final search/capture follow-up passed 37, without skips. Screenshots remain
synthetic presentation evidence, not screen-reader or native-platform clearance.

The starting UI was not a raw technical shell: it already had coherent native
styling, stable navigation, local-first language, grouped controls, explicit
save/reset, device preservation, and recovery guidance. The initial product gap
was operational clarity at rest: app presence, microphone checks and model-file
status did not form a clear readiness surface.

Subsequent Dictation changes now separate last-checked applied model readiness
from unsaved model choices and microphone checks, while retaining five
destinations and Tk. The follow-ups above record keyboard, layout and recovery
progress; the desktop roadmap remains the authority for remaining work. New
start/stop actions still require a tested IPC control contract rather than an
assumption that a read-only status snapshot authorizes capture.
