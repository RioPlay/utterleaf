# Design review record

September 11, 2026. Scope: next-system architecture, experience, adaptive touch,
Incognito, performance acceptance and interaction concept. This is design review,
not implementation, penetration testing, native verification or device acceptance.

Terra handled architecture/source contracts; Luna handled experience and the
interaction concept. A separate Terra reviewer challenged the contracts without
editing them. One owner per file prevented overlapping edits. Source claims used
scoped Aden navigation followed by direct source inspection; a missing framework
or JNI graph edge was not treated as proof.

Material findings reconciled:

- Delayed gesture results require bounded ordered dependent input with visible
  pending/error/cancellation outcomes. Ordinary taps only bypass that ordering
  while no gesture run is unresolved. No UI wait for native decode.
- Editor support is eligibility plus observed host outcome, not an inference from
  a Boolean API return. Synchronous host IPC can still block independently of core
  scheduling. Modifiers start with complete per-key chords and local arm state.
- Voice entry points retain separate editor/take ownership and share one exclusive
  microphone/inference lease; a second owner gets Busy instead of cross-canceling.
- Asset trust derives from a fixed reviewed catalog, never an imported manifest.
- Calibration is geometric only, default Off. Incognito overrides it; compound
  generations prevent stale training or Clear resurrection. Already accepted OS
  writes and failed-save durability are described without impossible guarantees.
- Footprint comparisons require matched feature profiles and candidate/baseline
  ratios. No imported-source-size or incomplete-prototype comparison can establish
  that the complete new system is smaller.
- Milestones now use one N0–N5 map. Calibration inspection has no persisted date or
  individual input history; stable keycaps are separate from touch probability.

The fresh independent markdown review found no remaining concrete blocker. That
does not select a decoder, prove adaptation quality, resolve licensing for future
dependencies or establish a replacement release. Those remain explicit gates in
[the roadmap](README.md) and [acceptance contract](PERFORMANCE-AND-ACCEPTANCE.md).

Local documentation links were checked. The concept's script passed syntax checking;
static interaction review covered draft cancellation, stale voice insertion,
Incognito/zone inspection and Terminal/Fn navigation. No browser/device execution
is claimed for that mockup. No Android source, dependency, manifest or
build input changed, so Android native/emulator suites were not rerun for this
design increment. Existing 121-emulator/12-JVM evidence belongs to LatinIME only.
