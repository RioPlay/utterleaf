# Desktop modernization

Status: active. This is the owning contract for the post-RC2 desktop experience
work. It supersedes chat-only planning, but not the desktop roadmap or the
bounded contracts linked below.

## Current stabilization slice, November 15, 2026

Goal: consolidate the existing visual upgrade into a quiet, consistent desktop
candidate and prevent ordinary test commands from opening display windows.
Source baseline: `feat/desktop-modernization` at `9b28250`, including visual
commit `d78fdd1` through merge `df8648c`. The mixed root checkout is reference
only. Android remains on its separate branch and is not changed by this slice.

Constraints: retain speech, privacy, staged settings, cancellation and reset
behavior. No framework migration, native-shell activation, release publication,
model operations or application launch. No screenshot or emulator runs. The user
authorized one bounded headless check of selection and theme logic after fixes.

Acceptance: an explicit display-test opt-in is required even when a caller
passes a marker expression; the PR gate stays headless; main retains deliberate
display coverage. Review the merged visual controls for actionable regressions
and align the interface guide with the actual desktop tokens. Existing captured
images may inform visual review, but do not establish current interaction or
installed-build acceptance.

Ready queue:

| Work | Owner | Scope | Status / evidence |
| --- | --- | --- | --- |
| Quiet test selection and CI | Luna runner | pytest configuration, workflow, selection checks, development guide | Complete; AST/TOML/YAML parsing and diff whitespace checks passed |
| Independent visual review | Sol reviewer | merged visual controls, theme and Settings usage | Complete: no demonstrated material defect; source matches saved visual captures; no GUI execution |
| Independent selection review | Sol reviewer | collection hook, workflow and focused checks | Complete; no demonstrated material finding; no test execution |
| Integration and documentation | Sol coordinator | demonstrated fixes, interface guide, roadmap and this plan | Complete for this slice; one focused invocation passed 10 selected checks |

Verification: cheap source/configuration parsing, independent review, then the
single authorized focused headless invocation. No broad suite or packaging.
Stop this slice after demonstrated defects are repaired, the bounded check is
reported accurately, and remaining usability/accessibility gates are explicit.
This slice alone does not certify stable release readiness.

The visual review covered the implementation with SHA-256 identities:

- `ui_layout.py`: `e35179884057d03151f15477a85942d0de0a854dad27332bea245a5867c2a0fb`
- `theme.py`: `fd49edaeda315dea8b96228f661173aef7ef29665219ec20d82682aa1c4b0649`
- `settings_ui.py`: `fbfdd0d5160ecb6489434fc6fea556efa815f062771c21c2bd811eb9571379b5`

One interaction question remains unverified: rounded controls forward pointer
crossing events without copying the button-state mask. Native ancestor events
may preserve drag cancellation, so this is not a demonstrated product failure.
The next permitted interaction check should cover press, drag outside and
release, plus drag back before release. No speculative control rewrite was made.

Delivered locally, November 15, 2026:

- A collection hook now excludes `ui` items unless `--run-ui` is supplied,
  independently of marker expressions. PR invocations remain headless and all
  three main-suite platform invocations explicitly opt in to UI coverage.
- The independent selection review found no material defect. The coordinator
  then added a harmless inherited UI-marker sentinel to the same workflow test
  module to exercise real collection without a window. The sentinel asserts that
  explicit opt-in exists if it is ever selected; it passes on opted-in CI runs.
- Exactly one headless invocation ran from the owning worktree, using the shared
  repository Python environment with `PYTHONPATH` set to that worktree and
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`:
  `python -m pytest tests/test_ci_workflow.py tests/test_theme.py -m "not slow" -q -ra`.
  All **10 selected checks passed**, exit 0. The inherited UI sentinel was
  deselected even with the explicit marker expression. Fake-item checks also
  verified rejection without opt-in, retention with opt-in, ordinary-item
  preservation and deselection reporting. Theme checks covered readable contrast
  and style application through a fake root. No real Tk root was created.
- Interface guidance and roadmap now match the current layered desktop design.
  No application, screenshot harness, emulator, microphone, model operation or
  package build ran. No CI job, public push, installation or release was made.

Remaining broader-goal acceptance: current whole-app/runtime and packaged-build
verification, real pointer drag cancellation, supported-platform interaction and
the existing Windows accessibility-shell release gates. The 15-minute hosted
full-suite budget remains unmeasured on this revision. The broader goal remains
open; do not infer production readiness from this bounded result.

### Release compatibility follow-up

Goal: preserve the existing full-test release gate after CI job consolidation
and the explicit display-test opt-in. Baseline: `c37207a`.

Source inspection found two integration defects: the Windows preview's full-test
subprocess omits `--run-ui`, and stable publication still requires the removed
`windows`, `macos-build`, `linux-build`, `macos-tests` and `linux-tests` jobs.
The current build produces three `full-suite` and three `installers` matrix jobs.

Area: preview and publication workflows, their focused source-contract checks,
and development guidance. Luna owns these edits; the coordinator owns this
contract and independent review. No runtime/product-source changes.

Acceptance: preview full tests explicitly include UI; stable publication requires
all current native test/build jobs to succeed for the exact tagged source, while
retaining archive verification. A tag-only build that skipped full tests must
not qualify. Removed job names must not remain as publish requirements.

Verification boundary: source/configuration parsing and independent static
review only. The prior one-check authorization has been consumed. No local test,
CI dispatch, tag, release, upload or install is authorized by this follow-up.
Stop when the source matches these requirements and unexecuted checks remain
explicit. This repairs release preparation; it does not authorize publication.

Implemented and statically reviewed: preview tests now pass `--run-ui`. Build
jobs have explicit OS-based names, and publication requires the six matching
successful test/installer jobs from a completed successful `build.yml` main push
at the exact tag SHA. Existing archive checks are unchanged. The development
guide no longer claims PR screenshot generation.

Independent review traced a valid main-run case and rejection of tag-only,
missing-test, failed-job and revision-mismatch cases through the gate. It also
found a deterministic source-contract assertion mismatch in the preview argument
list; the missing `sys.executable` prefix was corrected and read back. No
outstanding material static finding remains. AST/YAML parsing and whitespace
checks passed.

Approved focused verification on November 15, 2026, at source revision `5c2ee71`:
`python -m pytest tests/test_ci_workflow.py -q -ra
--junitxml=.grok/verification/ci-contract.xml` passed **7 checks**, with zero
failures, errors or skips. The UI sentinel remained deselected. The shared Python
environment used this worktree as `PYTHONPATH`, with plugin autoload disabled.
The local text/XML receipts are under `.grok/verification/`. No app window,
screenshot harness, emulator, microphone or model operation ran. The hosted API
gate remains unexecuted; source assertions do not prove runtime positive/negative
publisher behavior or installed-build acceptance.

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
| G | Model management | Canonical names and factual language support appear in summaries/download feedback. Fresh profiles stay offline until an explicit model installation; malformed persisted consent fails closed. An explicitly refreshed inventory lists guided installations, measured setup-file sizes and compatible draft-only selection; download dispatch/confirmation/stale callbacks recover safely. Cached Model details keeps identifiers/paths optional. Runtime load proof is separate from inventory; neither identifies an active take. No download-size or reclaimable-space claim. Removal/Update is gated on trusted immutable revisions/hashes, managed-path defenses, shared leases, active-take unload acknowledgement and quarantine/rollback; it must not be improvised from file presence. |
| H | Settings | The Recording feedback section now has one explicitly scoped reset for indicator, live preview and sounds; real isolated-storage tests preserve unrelated drafts, global reset semantics and saved data. Broader regrouping still requires a persistence/reset migration contract. |
| I | Keyboard shortcuts | Window-local page navigation, F1 Help, Page Up/Down/Home/End and Ctrl+F/Command+F Settings search accompany Save/Close/focus movement. Static search covers all 21 preferences and five destinations without indexing private values. Native editing keys remain untouched; broader platform shortcut validation remains. |
| J | Tray | Current tray keeps status, Settings, two-minute recovery, indicator, secondary Tools and Quit. Tray start/stop and microphone switching remain gated: clicking the tray changes focus, so paste-target ownership and per-platform menu/keyboard behavior need an explicit contract before those controls are safe. |
| K | Notifications | Routine states remain in-app. No notification was added without measured need; user-requested model completion, critical device failure and required action still need per-platform permission/lifetime and duplicate-suppression acceptance before becoming first-class notifications. |
| L | Errors/recovery | Device-list, model-download, file transcription/export, decoder setup, artwork export and diagnostics/report export failures lead with impact/retry guidance and expose bounded local technical text only via Details. Settings-save now preserves confirmed progress separately from app notification, with safe alerts and explicit Save details; scoped verification is recorded below. Remaining failures still need convergence. |
| M | Empty states | Explain why dictation is unavailable and offer one next action for missing microphones/models. Avoid decorative art that adds no comprehension. |
| N | Window/layout | Readable widths, responsive model/sidebar layout and fixed wrapping auxiliary actions are implemented. File/decoder/review content scrolls; compact/wide round trips cover 1×/1.5×/2× Tk text scales. Physical scaling, maximized/mixed-monitor DPI and other native platforms remain open. |
| O | Accessibility | Reference-page scrolling, oversized-editor insertion/validation-line reveal, held-key repeats, and read-only report Tab traversal have source coverage. An intermittent Tcl Tab-command failure is recorded, not waived by later green runs. Names, dialogs, screen readers, physical scaling and Windows UI Automation acceptance remain open. |
| P | Performance | A bounded real-Tk Settings comparison records construction, 12-second idle CPU and memory on named Windows hardware. Three fresh packaged starts record authenticated readiness and ten-second parent-process tray-idle CPU/memory; polling saw no established external TCP socket owned by the parent app process, and no model write occurred. The harness left the separately launched first-run Settings processes alive, so it is not whole-process shutdown evidence. Source tests separately deny both downloader entry points. Sustained use, recognition latency, cross-platform behavior and a packaged baseline comparison remain open; no full performance clearance is claimed. |
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
- **Whole-product performance:** the bounded Windows package receipt now measures
  three sequential fresh-profile starts plus tray-idle CPU/memory. OS/file cache
  state was not controlled. Sustained use,
  recognition latency, other release hardware/platforms and a packaged baseline
  comparison remain open; neither the Settings nor three-start sample clears them.
- **Tray/notifications:** start/stop from a tray must not paste into a target lost
  when the menu took focus. Notification permission, lifetime, suppression and
  recovery behavior need platform contracts and user-value evidence.
- **Release:** a local unsigned Windows onedir build, unforced doctor, fresh-profile
  startup and full desktop suite now pass. Exact-final hosted multi-OS CI, signing,
  public tag/publication authorization and manual device/accessibility acceptance
  remain release activities. Security checks are not weakened to manufacture a pass.

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

## Historical verification journal

The following completed slices and receipts are archived as historical evidence. Open gates remain in this active contract and the [desktop roadmap](../../desktop-roadmap.md).

### Completed source slice: landing information and shell

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-landing-information-and-shell).

### Completed source slice: microphone and model recovery

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-microphone-and-model-recovery).

### Completed source slice: last-reported operational status

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-last-reported-operational-status).

### Completed source slice: keyboard page scrolling

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-keyboard-page-scrolling).

### Completed source slice: oversized-editor keyboard access

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-oversized-editor-keyboard-access).

### Completed source slice: consistent model presentation

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-consistent-model-presentation).

### Completed source slice: Settings search

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-settings-search).

### Completed source slice: backup preview keyboard and layout

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-backup-preview-keyboard-and-layout).

### Completed source slice: artwork reference keyboard and recovery

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-artwork-reference-keyboard-and-recovery).

### Completed source slice: diagnostic report recovery

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-diagnostic-report-recovery).

### Completed source slice: Settings-save recovery

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-settings-save-recovery).

### Completed source slice: Settings check dispatch recovery

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-settings-check-dispatch-recovery).

### Completed source slice: guided installation inventory and download lifecycle

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-guided-installation-inventory-and-download-lifecycle).

### Completed source slice: loaded model for applied settings

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-loaded-model-for-applied-settings).

### Completed source slice: Recording feedback section reset

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-recording-feedback-section-reset).

### Completed source slice: effective input-route revalidation

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-effective-input-route-revalidation).

### Completed source slice: unsupported microphone configuration recovery

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-unsupported-microphone-configuration-recovery).

### Completed source slice: truthful applied-model readiness

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-truthful-applied-model-readiness).

### Completed source slice: auxiliary recovery and state terminology

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-auxiliary-recovery-and-state-terminology).

### Completed source slice: file and review auxiliary baseline

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-file-and-review-auxiliary-baseline).

### Completed source slice: auxiliary responsive layout and keyboard access

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#completed-source-slice-auxiliary-responsive-layout-and-keyboard-access).

### Bounded Settings performance check

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#bounded-settings-performance-check).

### Unsupported microphone configuration recovery

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#unsupported-microphone-configuration-recovery).

### Applied-model readiness and status precedence

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#applied-model-readiness-and-status-precedence).

### Auxiliary recovery and state terminology

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#auxiliary-recovery-and-state-terminology).

### Auxiliary baseline and responsive follow-up

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#auxiliary-baseline-and-responsive-follow-up).

### Host Tcl/output-capture diagnosis

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#host-tcloutput-capture-diagnosis).

### Initial baseline and shell

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#initial-baseline-and-shell).

### Recovery follow-up

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#recovery-follow-up).

### Last-reported status follow-up

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#last-reported-status-follow-up).

### Keyboard page-scrolling follow-up

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#keyboard-page-scrolling-follow-up).

### Oversized-editor and model-presentation gauntlet

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#oversized-editor-and-model-presentation-gauntlet).

### Bounded Settings performance receipt

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#bounded-settings-performance-receipt).

### Explicit model-consent and packaged first-run follow-up

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#explicit-model-consent-and-packaged-first-run-follow-up).

### Explicit multilingual model-pack follow-up

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#explicit-multilingual-model-pack-follow-up).

### Closeout recovery, lifecycle and accessibility audit

Historical evidence: [archived receipt](../completed/desktop-modernization-history.md#closeout-recovery-lifecycle-and-accessibility-audit).
