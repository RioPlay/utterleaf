# Adversarial review of the LatinIME migration plan

Status: proposal for Ernest's review, September 10, 2026. Implementation remains
paused. This document and related work stay local and uncommitted; no publication
or toolchain installation is authorized by this review.

Three independent lightweight reviewers using `gpt-5.6-luna` challenged security
and privacy, usability and accessibility, and engineering feasibility. Their
findings were reconciled against the [research](COMMUNITY-RESEARCH.md), current
Utterleaf documentation and selected pinned upstream source. This is an internal
planning review, not an independent security audit or device validation.

## Recommended path

Approve the product scope, interaction prototypes and security boundaries first.
Then prove an installable LatinIME vertical slice using its real Java, resources,
JNI and input/composition path. Add Utterleaf's features to that coherent base,
with security and lifecycle checks throughout. Only consider replacing the current
keyboard after everyday typing, voice, editing, advertised terminal behavior,
settings and physical accessibility pass their respective acceptance checks.

An internal experiment is not a minimum viable replacement. A compiling native
library is not a working IME. A polished screenshot is not comfort evidence.

## Challenges and resolutions

| Challenge | Resolution |
| --- | --- |
| A native-only spike could miss the actual porting difficulties | Accepted. It may diagnose a compiler issue, but the first meaningful feasibility gate is a full installable experimental IME. |
| Security stripping appears too late in the earlier sequence | Accepted. Capability, component, backup and text-logging restrictions precede installation. Full fuzzing and physical acceptance need not precede a controlled synthetic test. |
| Transient text handling is under-specified | Accepted. Define bounded context, its purpose and lifetime before extraction. No cross-field reuse, retained typing history or text-bearing diagnostics. |
| Correction undo appears before the correction engine | Accepted. The internal base can exercise literal input; a replacement needs tested correction and recovery together. Never expose an unavailable option as working. |
| Terminal could be removed to simplify the first candidate | Partially rejected. It may be absent from an internal first slice, but is an explicit Utterleaf workflow and remains a final migration gate. |
| Disable held deletion by default | Refined after challenge. Ordinary Backspace repeat is different from spatial drag-to-delete. Preserve familiar repetition subject to timing/cancellation validation; do not enable destructive drag behavior before safe preview and cancel are established. |
| Preference toggles solve disagreements automatically | Qualified. Provide user choices, but specify gesture ownership, option interactions, accessible alternatives and reset semantics. More combinations require deliberate testing. |
| Community research establishes the best defaults | Rejected. It supplies useful hypotheses and failure cases. The sample does not establish universal preference; physical trials must inform comfort defaults. |

## Stage 0: reviewable decisions before implementation

Produce a short scope checklist identifying retained current workflows, required
replacement capabilities, and separately gated enhancements. Terminal and offline
speech stay in scope. Swipe remains a major requirement for swipe-dependent users,
with a separate decoder/provenance gate rather than an unsupported promise.

Prepare Daily, Symbols/Accents, Edit, Terminal, Voice review and Setup/Settings
prototypes. Compare compact widths such as 320/360/412 dp and landscape without
claiming those mockups validate fingers or accessibility. Review microphone reach,
Space/B separation, stable control positions, long-press feedback, selection
preview and return-to-letters behavior. Provide a settings map with quick access,
independent preferences, proposed defaults and clear reset.

Define the initial supported language/device matrix and explicit exclusions.
English can be the first engineering fixture, not a hidden limit on the long-term
product. Layout, composition, dictionary, swipe and speech support are separate
claims. Identify native-speaker, motor-access and assistive-technology validation
gaps before promising broad compatibility.

**Exit:** Ernest approves scope, designs and the implementation sequence. Research
and review do not count as that approval.

## Stage 1: exact-source full-base feasibility

After approval, inventory LatinIME's transitive Java/resource/native dependencies,
licenses/notices and dictionary provenance. Use the pinned source from the
[foundation record](README.md), a separate application ID and ordinary debug
signing. Do not reuse upstream's shared key or Utterleaf's release key.

Modernize the standalone Gradle/CMake build around the real LatinIME service,
keyboard/input logic, resource graph and JNI library. Use a fixed reviewed test
dictionary or a suitable self-authored fixture. General dictionary/model import,
voice and terminal integration are unnecessary for this first proof.

The machine currently lacks the established Android toolchain. To preserve the
local-only instruction, a later approved build step should provision verified
official tools locally; remote CI requires separate publication authorization.
Do not silently substitute a push for local validation or claim compilation from
static inspection.

**Exit:** an experimental APK builds and its provenance is recorded. No installation
until the following pre-install restrictions are checked. A standalone native test
or Java shell does not satisfy this gate.

## Stage 2: restricted synthetic test environment

Before installation, replace incompatible manifest entries and remove or isolate
their source paths: contacts/accounts/cloud integration, background downloads and
updates, user-history learning and unnecessary providers/receivers. Disable backup
of sensitive data. Enforce a merged-manifest/component allowlist and review dynamic
registrations, logging, assets and dependencies. Merely hiding settings is inadequate.

Define the editor-context contract here, not as a later prediction feature. A
bounded current-session context can support composition without becoming passive
collection. The existing capability document's 256-code-point proposal is a
candidate to evaluate, not a verified universal bound. Clear session references
and invalidate work at field transitions; distinguish this from a guarantee that
managed-runtime memory has been cryptographically erased.

Exercise literal input, Space, Backspace, composition, selection, sensitive fields,
hide/restart, cancellation and editor switching in a controlled emulator using
synthetic data only. Inspect logs/storage with canaries. Test component restrictions
and intentional inter-app communication. No real accounts or private messages.

**Exit:** observed behavior matches the restricted design. Unresolved wrong-field
actions, unintended submission, sensitive persistence or unsafe components block
progress to personal-device use. Passing finite tests is not proof of perfection.

## Stage 3: Utterleaf behavior on one keyboard engine

Retain LatinIME's coherent composition/touch path. Introduce a clear session and
editor-action policy at that path; do not create a second competing commit engine
by bolting the old custom keyboard alongside it. Review asynchronous suggestion,
gesture and voice results for freshness at the actual mutation boundary. Not every
synchronous JNI method needs a new token parameter; the design must enforce the
invariant without unnecessary signature churn.

Integrate in small complete workflows: Daily typing with correction/recovery;
accessible gestures and Edit actions; local voice with explicit capture, review,
cancel and insert; verified model selection/import; then the full advertised
Terminal layer. Test each slice as it lands. Do not silently drop an existing
workflow because it was absent from the initial experiment.

Test preference persistence, conflicting gesture modes, quick-toggle reversal,
preview cancellation and reset. Reset preferences preserves models and explicit
dictionary entries. No preference weakens privacy/security guarantees. Keep
unimplemented choices out of the working controls.

**Exit:** integrated workflows have source, automated and targeted physical evidence;
remaining limitations are explicit. The earlier custom implementation remains a
reference/fallback during development, not a permanent second production engine.

## Stage 4: migration acceptance

Run matched everyday/editor/terminal tasks on named devices and Android versions,
including one-handed use, small screens, large text, contrast choices, TalkBack,
Switch Access where supported, and navigation to host-app controls. Test actual
terminal applications for advertised modifiers, interruption keys, Tab/Escape,
navigation, focus changes and the distinction between Copy and terminal Ctrl+C.

Assess reviewed native parsers with malformed/oversized fixtures, allocation bounds,
sanitizers and fuzzing appropriate to the exposed surface. Review artifacts and
dependencies independently. Verify settings/model retention through upgrades and
failed imports. Do not promise downgrade rollback where Android version/signing
rules or data migrations make it unavailable.

Measure accuracy, correction effort, activation/touch latency, tail stalls, memory,
and voice responsiveness against a named baseline. Use the existing
[production-readiness standard](../../docs/production-readiness.md); test counts
alone cannot establish stability or physical accessibility.

**Exit:** no unresolved critical security, data-loss, wrong-field or required-access
blocker in supported workflows. Any release or GitHub publication still needs the
explicit authorization currently withheld.

## Source evidence and review limits

The engineering and security reviewers inspected pinned AOSP source. Selected
observations were rechecked during synthesis:

- `build.gradle` uses AGP 3.2.0-beta03 and references absent
  `native/jni/Android.mk`; `java/Android.bp` and `native/jni/Android.bp` describe
  the actual platform build and native graph.
- `java/src/com/android/inputmethod/latin/LatinIME.java` eagerly loads JNI in its
  static initializer and contains lifecycle/dynamic receiver registration paths.
- `java/src/com/android/inputmethod/latin/inputlogic/InputLogic.java` passes typed
  words into statistics hooks during input restart; its debug branch in
  `commitChosenWord` logs chosen text.
- `java/src/com/android/inputmethod/latin/utils/StatsUtils.java` has empty hook
  bodies at this revision. That is not evidence of active telemetry; it is a
  text-bearing interface and future-merge risk to eliminate or constrain.
- Reviewers flagged editor caching in `RichInputConnection.java` and contacts and
  user-history paths in `DictionaryFacilitatorImpl.java` for the extraction audit.
- [Current design history](../../docs/android-keyboard-design.md#released-in-alpha10)
  documents ordinary held deletion as enabled by default. It must not be confused
  with the separate proposed drag-deletion behavior.

No implementation files changed, no Android build/device tests ran, and no claims
of current upstream exploitation or complete parser safety are made by this review.
The precise upstream source is [LatinIME at
127336e9f29d69607eab55982324b210279ae8c5](https://android.googlesource.com/platform/packages/inputmethods/LatinIME/+/127336e9f29d69607eab55982324b210279ae8c5/).
