# Production readiness and stability

[Development guide](development.md) · [Platform testing](platform-testing.md) ·
[Android performance](android-performance.md) · [Roadmap](roadmap.md)

Research reviewed September 10, 2026. **This is a proposed acceptance standard,
with an initial evidence inventory, not a production certification or measured
performance claim.** Security first, privacy second, convenience third.

## Measure what the user experiences

A keyboard can avoid crashing while dropping letters or inserting into the wrong
field. Dictation can finish correctly but block the next take. Measure complete
user journeys and their failure paths, not only process uptime or test counts.
This applies the user-centered SLO approach described in
[Google's SRE workbook](https://sre.google/workbook/implementing-slos/).

| Dimension | Measurement | Proposed release decision |
| --- | --- | --- |
| Input correctness | Expected text, selection and modifier state after deterministic typing, gestures, editing and dictation sequences | Any reproducible lost/duplicated input, wrong-field insertion, or unintended destructive command blocks the affected release. A successful dispatch return is insufficient. |
| Stability | Crashes, native faults, ANRs/hangs, failures per completed test journey; separately, field rates if legitimately available | No unresolved reproducible crash/hang on supported critical paths. Report failures and total attempts, devices and build. Never infer field reliability from a green emulator suite. |
| Responsiveness | Touch-to-visible text, keyboard activation, mic opening, stop/cancel-to-mic-release, review and final insertion latency | Track median and tail latency separately. Reject unexplained repeatable regressions beyond established measurement noise. |
| Rendering | Frame deadline misses and P50/P90/P95/P99 frame overrun during typing and panel transitions | Investigate tail stalls. Refresh rate and device matter; averages hide intermittent freezes. |
| Speech quality and speed | Word/character error rate on fixed public fixtures, exact command/punctuation cases, model-load time, decode time and real-time factor (decode seconds/audio seconds) | Compare the same model, backend and fixture. Faster inference must not silently change text, commands or model selection. |
| Resource ownership | Peak process/native memory, retained memory after repeated work, microphone ownership, CPU while idle, energy per fixed workload | No unbounded growth, leaked recording ownership or continuing repeat/worker activity after cancellation. Test resource exhaustion and recovery. |
| Recovery and upgrades | Retry after denial/disconnect, import interruption, process death, upgrade and preference reset | The next supported operation works; failed import preserves the prior model; reset preserves models and user data. Verify retained settings, not just successful installation. |

Google Play defines user-perceived crash/ANR rates using daily active users who
experience at least one relevant failure, rather than failures divided by sessions.
Its overall bad-behavior thresholds are 1.09% for crashes and 0.47% for ANRs;
phone-model thresholds are 8%. These are warning limits, **not our quality goals**.
GitHub APK distribution does not provide a corresponding installed-population
metric. Do not invent a crash-free percentage without a valid denominator.
[Android vitals definitions](https://support.google.com/googleplay/android-developer/answer/9844486?hl=en)

## Establish physical-device baselines

Proposed starting budgets to evaluate on reference hardware are P95 touch-to-text
at 50 ms, warm keyboard activation at 250 ms, microphone opening at 300 ms and
stop/cancel-to-microphone-release at 250 ms. These are Utterleaf hypotheses, not
Android standards or achieved results. Slow hardware and OS scheduling need
explicit qualification; do not silently relax a budget after a failed run.

Record build SHA, device/OS, refresh rate, model hash/backend, power and thermal
state, sample count, fixture and measurement boundaries. Separate cold starts,
warm starts and sustained use. Preserve raw synthetic measurements so percentiles
can be reproduced; do not report a convincing-looking P99 from a handful of takes.
An initial regression-review trigger is a repeatable increase above 10%, once
normal variance is known. Absolute usability budgets still apply.

Android Macrobenchmark provides startup timing and frame distributions;
`frameOverrunMs` is available from API 31. Startup metrics describe activity
launch, so IME activation needs its own journey and timing boundary. Positive
frame overrun indicates a missed deadline; the goal is smooth interaction, not
a blanket claim that every frame on every device will meet it.
[Metric definitions](https://developer.android.com/topic/performance/benchmarking/macrobenchmark-metrics)

Use physical phones for timings; emulator performance is not representative.
Start with the Pixel 8 Pro and a lower-memory phone, then broaden vendor/OS
coverage. Desktop requires separate Windows, macOS and Linux measurements;
Wayland/X11 and CPU/GPU paths are distinct cases.
[Macrobenchmark testing guidance](https://developer.android.com/codelabs/android-macrobenchmark-inspect)

Keep inference, hashing, blocking I/O and long lock waits away from the UI thread.
Inspect traces when interaction stalls rather than adding arbitrary delays or
more worker threads. A timeout alone does not prove underlying work stopped.
[Android ANR diagnosis](https://developer.android.com/topic/performance/anrs/diagnose-and-fix-anrs)

## Clean code and security gates

Use explicit ownership and small, named state transitions: idle, opening,
recording, processing, review, delivery, cancellation and failure. Review callbacks
against session/editor identity. Bound untrusted input, buffers, subprocess waits
and retries; release resources on every exit. Verify framework/JNI entry points
before deleting apparently unused code. Aden helps navigation, not proof of safety.

Tests should establish behavior: real editor text/selection, failure recovery,
permission loss, rapid switching, Unicode, modifier release, interrupted imports
and stale callbacks. Add property/fuzz tests at parser/native boundaries and
sanitizer builds where applicable. Coverage is a gap-finding tool, not a substitute
for meaningful assertions. Do not hide flaky tests through repeated green reruns.

Use [NIST SSDF](https://csrc.nist.gov/projects/ssdf) to structure secure development:
protect source/builds, define review responsibilities, verify software and respond
to vulnerabilities. For mobile, map applicable storage, platform, code and privacy
requirements to evidence from [OWASP MASVS](https://mas.owasp.org/MASVS/).
Neither document makes this app certified. Avoid adding anti-user restrictions
or runtime dependencies merely to improve a checklist score.

Release hardening should include reviewed dependency updates, resolved dependency
inventories/SBOMs, vulnerability triage, secret scanning, least-privilege CI and
immutable action references. Test the exact revision that supplies the signed
artifact, preserve certificate continuity and verify artifact checksums.
[OpenSSF Scorecard checks](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
inform these controls; a score is not proof of secure code. Known exploitable
critical/high vulnerabilities block stable release; record reachability analysis
and remediation rather than treating every scanner result as equivalent.

## Evidence inventory and next work

This inventory is scoped source/workflow inspection, not an exhaustive audit.

| Area | Evidence already present | Still needed |
| --- | --- | --- |
| Android behavior | Instrumentation, JVM tests, lint and release contracts in [Android CI](../.github/workflows/android.yml); typed capture status and session guards | Physical-phone gestures, accessibility and real editor/terminal matrix; soak and latency baselines |
| Desktop behavior | Separate OS matrix in [desktop CI](../.github/workflows/build.yml) | Real mic contention, focus/paste, sleep/resume and compositor acceptance per supported environment |
| Android distribution | [Isolated signing workflow](../.github/workflows/android-release.yml), certificate checks and emulator upgrade/reinstall | Latest-predecessor upgrade with seeded settings/model retention; physical Obtainium acceptance |
| Build inputs | Pinned native source and model hashes; desktop dependencies declared in [pyproject.toml](../pyproject.toml) | Reproducible resolved desktop build inputs; reviewed SBOM/vulnerability gates; workflows currently contain mutable action version tags |
| Performance | [Android source findings and measurement plan](android-performance.md) | Actual reference-device results; no whole-app performance certification exists |

Ordered work, kept in the respective platform source/test roots:

1. **Correctness:** fill critical failure/state tests and document external editor
   limitations. Release gate: no unresolved reproducible security/data-loss defect.
2. **Measurement:** add local benchmark harnesses and record physical baselines.
   Release gate: reproducible reports with explicit units, denominators and devices.
3. **Supply chain:** pin reviewed CI inputs, record dependency inventories, add
   actionable security checks. Release gate: exact artifact provenance and triaged findings.
4. **Endurance:** repeated typing/voice/model switching, low storage/memory, denied
   permissions, device changes and upgrades. Release gate: recovery and retained
   data verified, with no unexplained sustained resource growth.
5. **Stable acceptance:** review accessibility, one-handed interaction and supported
   external apps on real devices; publish remaining limitations alongside evidence.

For each release, record the SHA/artifact hash, passed checks, device matrix,
benchmark comparisons, unresolved defects and support boundaries. Alpha availability
must remain clearly distinct from completion of these stable-release gates.

## Measurement without surveillance

Use synthetic typing and public audio on test devices. Keep traces local and review
them before sharing: traces can contain user paths and other app information.
Log only fixed phase identifiers and timings, never audio, transcript/clipboard
contents, editor text or window titles. Do not add an analytics SDK, passive
collection, uploads or Android network permission for this plan. User-submitted
diagnostics must be explicit and reviewable. Zero observed failures in a finite
test run is useful evidence; it is not a guarantee of perfect reliability.
