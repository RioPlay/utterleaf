# Utterleaf Android keyboard implementation plan

**Product:** LatinIME's foundation, FUTO-inspired comfort and refinements,
Hacker's Keyboard-style power controls, and Utterleaf's own offline voice engine.
All four belong to the intended replacement. Utterleaf retains its own identity
and prioritizes security, privacy, then convenience.

**Status:** implementation, testing and shipment authorized. The isolated foundation
now builds and runs; comfort preferences and restricted input handling are under
test. This is not a completed replacement keyboard. See the
[execution evidence](EXECUTION-EVIDENCE.md) for current results and open gates.
The packages below remain the canonical execution sequence; research and the
baseline checklist define the intended scope.

## Starting point

- Utterleaf integration worktree: branch `feat/android-latinime-foundation`, based
  on `e76a055`, with isolated implementation changes.
- AOSP reference fork: `utterleaf/android-base`, pinned to
  `127336e9f29d69607eab55982324b210279ae8c5` in the separate upstream checkout.
- Existing Android alpha13 remains the behavioral regression reference. Its tests
  do not establish correctness of the new port.
- The standalone experiment builds with the installed toolchain. The shipping
  application remains separate until migration and acceptance gates pass.
- Desktop worktrees, dependencies, source and releases are outside this plan.

## Architecture and ownership

LatinIME remains the sole keyboard renderer, touch/composition system and normal
text input path. Extend its layouts, resources and input handling rather than
replacing them with Utterleaf's earlier custom button surface.

Put editor policy at the active LatinIME input boundary. Normal text/composition,
explicit Edit actions, terminal key events and Utterleaf voice insertion must all
respect current editor identity, sensitivity, capabilities and cancellation. The
terminal adapter deliberately uses key semantics; ordinary editing uses suitable
editor operations. No parallel component independently commits into a cached field.

Reuse Utterleaf's voice capture/inference, verified model store and cancellation
contracts. Adapt their UI/session connection to LatinIME; do not adopt another
keyboard's voice stack or maintain two speech engines merely for appearance parity.

| Workstream | Exclusive ownership during implementation | Dependencies |
| --- | --- | --- |
| Foundation/security integration | Experimental build, manifest, native packaging, dependency inventory and shared session boundary under `mobile/latinime/` | Scope approval |
| Keyboard experience | LatinIME-derived layout/resources, touch refinements, themes, suggestions presentation and accessibility tests | Stable build and boundary contract |
| Edit/Terminal | Editor/key dispatch adapter, power layouts, modifier lifecycle and editor/terminal tests | Shared boundary; reviewed layouts |
| Voice/models | Utterleaf voice adapter, voice UI, verified asset integration and related tests | Shared boundary; existing engine contract |
| Lead integration/QA | Cross-workstream contracts, build routing, migration, evidence ledger and docs | Reviews from each owner |

Exact files will be assigned after the extraction map exists. Only one owner edits
a shared manifest, build file, session contract or settings schema at a time.
Reviewers can work read-only in parallel. Every source change uses scoped Aden
navigation and actual source/test validation; framework/JNI entry points are not
dead code merely because a graph lacks callers.

Keep the existing `mobile/android` application as the stable reference until a
reviewed migration step. Preserve AOSP provenance and notices in the derived
source. The port belongs under the isolated Android experiment, with no desktop
dependency changes and no permanent competing keyboard engine.

## Proposed experience

| Surface | Design proposal |
| --- | --- |
| Daily | Familiar staggered keys, broad Space, direct comma/period, host-aware Enter, optional secondary hints. A compact strip offers suggestions with microphone/actions access; expanded actions use the same strip area where feasible. Avoid stacking permanent tool rows. |
| Symbols/Accents | Familiar symbol pages, hold-slide-release alternates and quick punctuation; visible current choice, safe cancellation and tap-accessible alternatives. |
| Edit | In-place panel for selection, navigation, undo/redo, cut/copy/paste and forward Delete, with a stable return to letters. Unsupported editor actions have an honest unavailable state. |
| Terminal | Explicit power layout retaining access to letters and directly reachable common modifiers/Esc/Tab/navigation. Fn exposes less frequent keys. Held/one-shot/locked state is visible, with Clear modifiers and an obvious exit. |
| Voice | Reachable Utterleaf microphone. Tap starts explicit capture; Stop/Cancel remain clear. Transcript review expands for reading/editing. Hold-to-speak with release-to-insert is a separate choice, not a forced review flow. |
| Setup/Settings | Enable/select keyboard, choose language/layout, verify resource readiness and try a practice field. Ordinary typing works independently of optional speech assets. Settings explain missing resources and recovery steps. |

Action placement is configurable; the proposed default favors one-handed voice
access. All configurations retain an accessible route to actions, Settings and
Reset. A hidden optional toolbar must not trap people without recovery controls.

Use Utterleaf colors/icons and restrained Utterlings in setup/help. Do not consume
active key space with mascot animation. FUTO is the comfort reference, not a
pixel-identical skin. Mockups require review before visual implementation; physical
comfort requires separate tests.

## Preferences and initial defaults for review

Group settings into **Typing and languages**, **Layout and comfort**,
**Gestures and feedback**, **Voice and models**, and **Editing/Terminal**. Quick
settings expose common adjustments and link to the full section.

| Choice | Proposed default | Alternatives |
| --- | --- | --- |
| Theme/geometry | Dark, centered, comfortable standard size | Light/high contrast/system theme; sizing, bottom spacing, one-handed alignment |
| Optional rows | Number and arrow rows off in Daily | Independently enabled; dedicated power layout |
| Correction | Conservative with suggestions once implemented and verified | Correction off/stronger; suggestions independently controlled |
| Space gesture | Cursor movement | Language switching or disabled, with one clear gesture owner |
| Deletion | Ordinary repeat retained after timing/cancel tests | Repeat off; separate drag-to-delete option after preview/cancel validation |
| Voice | Tap, then editable review | Hold/release-to-insert; review remains available |
| Silence stopping | Off | Optional stop; no implicit Send/terminal execution |
| Feedback | Sound off; other feedback finalized in the comfort review | Independent haptics/previews/intensity/timing choices within sensitive-field policy |

No unavailable engine or gesture is presented as a working preference. Avoid
automatically changing an unrelated option without explanation. Preview screens
with Apply/Cancel must honor cancellation; immediately applied quick toggles must
be easy to reverse. Reset preferences preserves models and explicit dictionary
entries. Data deletion is a separate deliberate operation.

## Security and privacy contract

No keyboard network/cloud inference, telemetry, contact/account integration,
background dictionary updates, ambient recording, passive typing collection or
clipboard monitoring/history. No executable add-ons or unverified assets. User
preferences cannot disable these invariants.

Bound transient editor context by purpose and active session. The earlier
256-code-point prediction-context proposal is a starting candidate, not a universal
limit for every explicit edit/voice operation. Define separate bounds where those
operations require them; never scan or retain the entire editor as a convenience.
Invalidate cached context and pending results at session transitions. Do not claim
cryptographic erasure of managed-runtime strings.

Password and unknown-sensitive contexts use conservative behavior, including no
voice or predictive context reads. `IME_FLAG_NO_PERSONALIZED_LEARNING` specifically
forbids updating personalized data; it is not itself a platform ban on all voice
or local suggestion features. Since learning is excluded globally, any additional
suppression for that flag must be an explicit documented product decision.

Every voice insertion requires an explicit user-chosen flow and a still-valid
editor session; hold-release mode may insert without mandatory review. Never
interpret insertion as Send or terminal execution. Stop/cancel, permission loss,
focus changes and late results must be handled at the mutation boundary.

Retain secure-window protection and accessible controls. Validate private storage,
backup exclusion, component boundaries, native parsing, import rollback and update
identity. Hashes establish asset identity, not parser safety; signatures establish
update identity, not blanket application safety.

## Work packages and completion gates

### W0 — Approved specification and reference tasks

Deliver the baseline checklist, the six surface prototypes above, settings map,
gesture-conflict matrix and proposed defaults. Record an exact FUTO reference
version/configuration for later comparisons; keep source research distinct from
observed behavior. Name initial language pairs, device/OS tiers and terminal/editor
targets. English can be the first engineering fixture without limiting the roadmap.

**Gate:** Ernest approves this plan's scope/design direction and implementation
sequence. Prototype review then resolves the detailed design within that scope;
routine implementation does not require repeated permission. Changes to security
policy, omitted baseline capabilities or publication return for explicit review.
This document does not approve itself.

### W1 — Full restricted LatinIME experiment

Inventory public-SDK build dependencies, Java/resources/JNI, dictionaries and
licenses. Provision verified official build tools locally after implementation
approval; no push to CI as a workaround for the local-only constraint. Pin the
toolchain and replace the obsolete Gradle/native build setup.

Build an experimental APK around the real LatinIME service and input path, using
an independent application ID/debug signing and a reviewed static dictionary or
synthetic fixture. Remove or isolate contacts/accounts/history/download paths,
unnecessary receivers/providers, sensitive backup and text-bearing debug/statistics
hooks before installation. Preserve required legal notices.

**Gate:** full Java/resource/JNI APK build, reviewed merged manifest/component and
dependency inventory, then installation only in a controlled synthetic emulator.
A native-only library or Java-only shell is not a passed milestone.

### W2 — Input/session policy and baseline correctness

Establish the shared active-editor boundary and contracts for composition, edit
actions, terminal events and later voice insertion. Exercise literal characters,
Space/Delete, composition, selection, sensitive fields, restart/hide/focus changes,
process death, cancellation and stale callbacks. Check synthetic canaries in logs,
caches, preferences and backup. Validate explicit IPC rather than equating absent
Internet permission with a complete data-flow audit.

**Local progress, September 10:** suggestion requests now snapshot composer/context
inputs on the owner thread, deep-copy coordinates and reject stale owner/worker/UI
queue work. Recorrection indicator changes remain on the owner thread. Specialist
and independent adversarial review plus 12 JVM/102 emulator tests are recorded in
[execution evidence](EXECUTION-EVIDENCE.md). Dictionary loads now reject retired
generations, dispose obsolete results, release waiters and notify on main. Native
dictionary/proximity admission now defers disposal until active operations finish;
composer reset and service teardown release local data. An external emulator probe
verified applied height and one synthetic asset across abrupt process death. Subtype
cache/identity, UI-cache and bounded JNI-input follow-ups passed review and regression
checks. Missing native gesture policy now returns unavailable; swipe remains required
and unimplemented. Traversal-cache retirement now passes safe-admission, race and
data-preservation tests. Deferred superclass finish targeting and bounded native word
copies passed. Native property outputs reject malformed buffers and preserve callback
exceptions; unsafe legacy bulk personalization is explicitly unavailable. Packaged
notices now have a local viewer and current-source APK checks;
component attribution remains incomplete. Bounded Unicode headers, numeric parsing
and reentrant header-output snapshots passed. Actual IME process recovery passed in
a separate synthetic host after a same-field user re-show; automatic reappearance
and wider editor/device coverage remain unverified. Unicode file paths and checked
native mapping ranges passed. Cursor-session retirement, bounded scoring/statistics
and automatic dictionary-file preservation passed. Production format migration is
temporarily unavailable pending a reviewed format-conversion replacement workflow.
Ordinary dictionary write transactions passed fault tests and six external emulator
process-death cases. Decoder suggestion requests now capture immutable
`ProximityInfo` on the owner thread and pass that through native suggest admission
instead of a mutable `Keyboard`. This removes that worker-side keyboard lookup;
it does not establish complete cross-thread isolation of the decoder. Further
JNI/lifecycle coverage, including newly identified
static editor-metadata retention, remains. Owner-checked service/view teardown and
silent pointer-state cleanup are implemented in a bounded follow-up; independent
review also corrected surviving timers and stale shared-preview cleanup. See
execution evidence for verification. The [editor metadata review](EDITOR-METADATA-REVIEW.md)
records an implemented immutable snapshot for cached keyboard layout/ID metadata;
the follow-up also snapshots deferred callback metadata, removes InputAttributes'
full editor reference, and clears strong cache slots on existing theme/locale
invalidation. These bounded fixes do not establish complete editor-data retirement
or decoder isolation. W2 is open.

**Gate:** no unresolved wrong-field mutation, implicit submission, sensitive
persistence or cancellation defect in these tested paths. Do not use real private
messages or credentials while those boundaries remain unproven.

### W3 — Comfortable typing, correction and customization

Implement the approved Daily/Symbols surfaces within LatinIME. Complete alternates,
punctuation, cursor/selection/deletion behavior, gesture options and visible
alternatives. Add local suggestions and correction with undo as one coherent
feature, plus explicit dictionary management, language/resource readiness and emoji.
Implement settings/practice/reset alongside the behavior they control.

**Gate:** K01–K08, L01–L06, L10, A01–A05, A07 and X01–X03 have implementation and
appropriate automated/physical evidence. Test one/two hands, small screens, slow
gestures and supported assistive technology early, not only at the final gate.

### W4 — Editing and full power-key workflow

Integrate the Edit/Terminal surfaces through W2's boundary. Cover Ctrl/Alt/Shift/Meta
where supported, Esc/Tab, forward Delete, navigation, Home/End, Page Up/Down,
Fn/F1–F12, selection and word-editing combinations. Keep modifier state explicit
and clear it on relevant transitions. Preserve Copy versus terminal Ctrl+C semantics.

**Gate:** A06, T01–T05 and U01 pass actual editor/terminal task checks. Name supported
applications and limitations; successful event dispatch is insufficient evidence.

### W5 — Utterleaf voice and model workflows

Reuse the existing local speech engine and verified asset handling. Integrate tap
and hold capture, readable editable review, expansion, explicit insertion, cancel,
model switching between takes and import recovery. Validate audio route/focus,
mic conflicts, resource/time limits, optional silence stop and symbol preferences.

**Gate:** V01–V05, E01, U02–U04 pass current-session, resource ownership and
one-handed usability tests. No silent engine substitution or network fallback.

W4 and W5 may proceed in parallel once W2's contracts are stable, with exclusive
file ownership. Shared toolbar/settings integration remains centrally coordinated.

### W6 — Separately gated parity capabilities

Investigate dictionary/decoder licensing and supported language assets during W1,
so blockers are discovered early. Integrate after W2/W3: inline autofill (K09),
mixed-language quality (L07), offline swipe (L08), local next-word prediction (L09),
split/floating modes (A08) and bounded custom layouts (A09). Each needs its own
compatibility, data-flow, quality and accessibility evidence.

**Gate:** each row is either verified for a named scope or explicitly incomplete.
There is no unqualified parity claim while material capabilities are missing.
Changing the promised scope requires review; a smaller experiment is not a new
definition of the finished product.

### W7 — Integrated acceptance, refinement and migration

Validate the complete product against the reference tasks and current Utterleaf
regressions. Include native malformed-input/sanitizer/fuzz testing, dependency and
artifact review, real-phone accessibility, battery/memory/latency and correction
effort. U05 performance work follows measurements; GPU/NPU integration requires its
own feasibility/provenance evidence. U06 branding is implemented with W3 surfaces
and assessed here for consistency and distraction.

Plan migration of existing settings, models, package/signing identity and public
IME/voice entry points. An experimental application ID is not a drop-in upgrade.
Preserve compatibility or clearly document any required re-enabling of the IME;
never silently discard the existing voice-only/recognition workflows. Keep a
working prior installation during experiments and avoid promising unsupported
Android downgrade behavior.

**Gate:** no unresolved critical security, data-loss, wrong-field, unintended-command
or required-accessibility blockers in supported workflows. Publish named-device
evidence and limitations, not universal superiority. Release, commit and GitHub
publication remain separately authorized steps.

## Evidence and maintenance

Keep one per-ID evidence ledger with implementation state, exact build, settings,
test commands/results, device/OS, remaining limitations and a regression scenario.
The [production-readiness standard](../../docs/production-readiness.md) supplies
measurement categories; emulator counts do not establish physical reliability.
Never collect routine user typing for metrics. Use synthetic fixtures and explicit
consenting test sessions; outreach is not authorized by this plan.

Run focused JVM/instrumentation/native/build checks with each applicable change.
Every implemented preference gets persistence, cancellation/reset and interaction
tests. Use targeted adversarial review at the session, import, permissions and
release boundaries. Keep changes small and reviewable without maintaining a
permanent second keyboard stack.

**First work after approval:** W0's concrete surface prototypes/reference tasks and
W1's dependency/source inventory, followed by the restricted full-IME build. No
further broad feature research is needed; investigate only the named blockers.
