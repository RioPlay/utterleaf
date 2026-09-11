# Performance and acceptance contract

All numeric budgets below are **provisional engineering targets**, not measurements
or promises. First reference class: ARM64, 4 GB RAM, 60 Hz display, Android 35;
select and record the exact phone before judging results. Add a low-memory Android
26 device and a recent high-refresh phone to the supported matrix. Emulator tests
validate ordering and regression logic; they do not establish touch comfort,
real-time latency, thermals, battery or assistive-technology usability.

## Optimize the architecture before tuning implementation

1. Dedicated Kotlin View-based key renderer with immutable layout geometry shared
   by hit testing and accessibility. Optional calibrated probability regions do
   not move keycaps; accessibility exploration uses static semantic geometry.
   Precompute glyph/label placement on layout or
   preference changes; no per-frame full keyboard reconstruction. Settings can use
   normal Android views; no WebView/JavaScript runtime in the Android keyboard.
2. Immediate literal typing and feedback require no dictionary, speech model, JNI
   call, file I/O or worker response. Editor mutation has one owner. Slow hosts are
   measured separately from core CPU time; Android host calls cannot be guaranteed
   nonblocking by changing our scheduling alone.
3. One coalesced update per linguistic worker; bounded ordered gesture completion.
   Do not increase queues to hide latency. Reject admission visibly before accepting
   more deferred input when capacity is exhausted. Never silently drop an accepted
   word, replay into another field, or block the main thread waiting for native code.
4. Layouts and active language resources load on demand with an explicit cache cap.
   Memory pressure retires idle resources. Optional speech stays unloaded until use;
   warm retention is bounded and only follows explicit use. There are no idle
   polling loops, periodic typing collection, wake locks or continuously animated UI.
5. Existing capture creates a 1,920,000-element float array (7,680,000 bytes) and
   `copyOf(count)` before JNI: up to 15,360,000 bytes for those two arrays alone.
   New voice transport should use one bounded owned buffer and a validated sample
   count, avoiding a second full Java array. This arithmetic excludes JNI/model
   allocations; it is not a measured whole-app memory saving. Native buffer lifetime
   must outlive admitted inference, including cancellation and worker failure.
6. Start with CPU speech and a bounded worker count. GPU/NPU paths need independent
   quality, energy, startup and device compatibility evidence. Do not initialize
   accelerators or load an alternative engine as an invisible convenience fallback.

## Initial budgets

| Metric | Provisional target | Measurement boundary |
| --- | --- | --- |
| Core handling of a literal key | p95 <= 2 ms, p99 <= 4 ms CPU | Touch classification through command creation; separate Android host IPC |
| Visible key feedback | p95 <= 33 ms at 60 Hz | Timestamped input to presented frame, measured on phone |
| Warm keyboard show | p95 <= 150 ms | Served-field show request to visible interactive keyboard |
| Cold keyboard show | p95 <= 350 ms | Process start request to first interactive keyboard; separately record OS scheduling |
| Frame misses during normal typing | < 1% frames over refresh deadline | Sustained synthetic typing, no speech; repeat with inference running |
| Typing-only PSS | <= 100 MiB | One layout and one approved compact dictionary; speech unloaded; include child processes |
| No-speech APK | <= 15 MiB compressed ARM64 | Resource/native breakdown; voice-inclusive APK reported separately, no asset-size hiding |
| Speech buffer memory | <= 12 MiB excluding model/engine workspaces | Peak capture and transport buffers across all processes at 120-second cap |
| Cancel responsiveness | UI acknowledgement <= 50 ms; resource retirement separately measured | Cancel event to UI; additionally mic release, worker cancel/kill and buffer disposal |
| Idle behavior | No app-owned periodic polling after settling | 10-minute visible-idle and hidden-keyboard traces; report OS-driven callbacks separately |

These are initial gates for tuning, not an assertion that every device can meet
them. Report misses and the reason; change budgets only with named evidence and a
recorded product tradeoff. Word quality and reliability cannot be traded away to
meet a latency number. Speech inference latency/RTF and memory are reported per
model/device/clip, not as a universal target that silently selects a smaller model.

## Matched baseline procedure

Compare alpha13, foundation `b75526a`, and the new candidate on the same phone,
orientation, layout, refresh rate, thermal state and synthetic input tasks. Record
commit, APK hash/signer, Android build, model/dictionary hash, settings and device.
Use 30 cold/warm openings and at least 1,000 deterministic taps per condition;
report medians/p95/p99, failures and distributions, not only fastest samples.
Instrument timestamps without text. Use Perfetto/frame timing, allocation traces
and process-tree PSS; report release builds without synthetic debug hooks.

Voice comparison uses consented/public-domain fixtures: short commands, 10/30/120
second speech, silence, interruption and failed microphone route. Record word error
rate and correction effort with runtime, total process-tree peak memory, energy
and thermal behavior. Run simultaneous typing to expose worker starvation.

Real two-thumb/one-handed sessions measure corrected and uncorrected errors and
effort, not just words per minute. Include accents, emoji sequences, RTL, composing
scripts, literal terminal commands and field changes. Obtain explicit consent for
any recording or typed-text collection in testing; production adds none.

## Correctness and utility gates

The footprint scorecard reports **candidate / baseline ratios** as well as absolute
sizes. Compare the same ARM64 release feature profile: (1) literal typing and
layouts, (2) typing plus the same-scope approved language assets, and (3) typing plus
voice using the same verified model. Where a build cannot provide a profile, mark
it unavailable rather than subtracting estimated bytes. Report compressed APK,
installed code/resources, peak and settled process-tree PSS, owned runtime source
size and dependency inventory separately. Include optional engines/assets and
shared runtime overhead. Never compare an uncompiled upstream checkout against a
tiny prototype to claim a fraction of the shipped footprint. A smaller candidate
with missing correction/swipe/voice is not a completed comparison.

Measure static, Learn, Frozen and Incognito touch paths on identical geometry.
The proposed calibration storage cap is 32 KiB across eight profiles; verify total
allocations as well as serialized size. No per-touch disk I/O or history buffer.
Geometry processing remains inside the literal-key CPU budget. Calibration quality
must improve correction effort without worsening uncorrected errors; all numbers
and confidence thresholds remain unmeasured until named-device trials.

| Scenario | Required result |
| --- | --- |
| Old suggestion/voice result after field or caret change | No text/UI mutation into an invalid target; no silent rebase |
| Gesture A ends, B starts before A decodes | A and B preserve order; A cannot change B's preview/composer; pending failure has visible recovery |
| Gesture then tap/delete/selection/voice | Defined ordered barrier, cancellation or explicit recovery; no action silently disappears |
| Two-thumb taps / slide / long press / cancel | Each pointer has one owner; no duplicate characters or stuck modifiers; canceled alternate inserts nothing |
| Unicode deletion | Whole user-perceived character where safely bounded; no surrogate/emoji corruption, no unlimited editor scan |
| Unsupported editor action or raw terminal | Unavailable feedback, no speculative Ctrl fallback or implicit Enter/Send |
| Voice cancel, permission/audio loss, worker death | Mic stops, old completion rejects, typing still works, bounded buffers retire |
| Preference draft, restart and Reset | Draft semantics hold; saved options persist; models/dictionaries unchanged |
| Failed import / low storage / process death | Previous verified asset remains usable; no unverified partial asset activated |
| Accessibility | TalkBack and Switch Access complete all core actions; stable semantic key geometry, static touch exploration, no gesture-only essential action |
| Calibration and Incognito | Off by default; no samples or updates during manual/forced Incognito; stale work cannot publish or resurrect cleared data; restart and reset preserve privacy choice |
| Release upgrade | Correct signer/version ordering, asset/preferences preservation and IME re-enable guidance; Obtainium and old voice entry points verified |

Frontend mockups and passing unit tests satisfy none of the physical acceptance
rows by themselves. Do not claim all languages because layout resources exist.

## Decision gate

After N1, compare implementation complexity, failures and measurements against
LatinIME rather than continuing either approach by inertia. Proceed with the new
core only with a real asynchronous decoder adapter, a viable reviewed linguistic
backend/asset path and evidence that basic touch/composition is sound. If the new
core fails those gates, retain the existing builds and revise the scope/architecture
explicitly. There is no automatic fallback renderer hidden inside the new service.
