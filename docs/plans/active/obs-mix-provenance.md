# OBS mix provenance and routing boundaries

## Goal and area

Continue the full [OBS audio design](obs-audio-design.md) on
`feat/obs-mix-provenance`, from reviewed controller source `a0ad377` in draft
PR #40. All five desktop CI jobs passed for that source in run `34774733389`.

Describe each selected OBS bus using its explicit label and observed input
assignments. Disclose buses with the same assigned inputs as the primary mix.
Preserve historical attribution and a timestamped boundary when routing changes;
keep normal capture continuous when the capture identity and format remain valid.

Area: bounded immutable desktop metadata, versioned native/Python framing,
native source/routing observation and worker transport, receiver/transcript
ownership, visible mix descriptions and focused cross-language/race tests.

## Constraints

- Resolve the primary bus from the live output's actual slot-zero audio encoder.
  Additional tracks are selected OBS buses, never stereo channels or inferred
  speakers. Equal assignment sets describe configuration, not identical PCM.
- No OBS routing, stream, recording, monitoring, profile or encoder mutation.
  Preserve explicit Arm, session identity, cancellation and bounded audio queues.
- Enumerate and copy metadata outside the audio callback. Retain only selected
  buses, with fixed source counts and UTF-8 byte limits. Labels/source identifiers
  must not leak through logs, exception text, dataclass representations or backups.
- Distinguish observation time from a proven sample boundary. OBS signal timing
  and buffered audio require an explicit uncertainty contract; do not invent
  precise attribution from a callback timestamp. Preserve uncertainty visibly
  when exact effective timing cannot be established.
- Metadata history and pending updates must remain bounded in memory for an
  unlimited session, using the existing private transcript ownership model.
  Missing, malformed, oversized, stale or inconsistent updates fail visibly.
- Source/capture identity or format changes that cannot preserve the authorized
  primary mix terminate safely. Ordinary assignment changes must not silently
  rewrite earlier labels or be presented as a new inferred speaker.

## Acceptance

1. Immutable models enforce six buses, at most 128 selected input records,
   unique source identities and exact selected-bus labels. Tests distinguish
   identical names from identical identities and empty from duplicate mixes.
2. Independent native wire vectors decode with Python under strict version and
   size checks. Identity, revision, selected buses and monotonic observation/
   boundary rules are validated before receiver state or audio ownership changes.
3. Initial metadata describes the actual selected primary and optional buses.
   Native signal/enumeration/teardown fixtures cover changes during snapshot,
   attachment, callback publication, stop, cancellation and source destruction.
4. Routing changes preserve earlier transcript attribution and refresh later
   descriptions. Bounded update bursts, slow recognition and cancellation do not
   create an unbounded metadata list, block audio callbacks or lose cleanup.
5. UI and eventual exports distinguish input assignments, same-input mixes and
   uncertain transition intervals. Synthetic evidence does not claim real OBS
   stream compatibility or physical-device usability.

## Verification

Start with focused model/protocol/receiver/transcription tests and native
metadata/wire/stream fixtures. Then run the affected OBS regression and canonical
native build/test driver when integration changes its linked inputs. Record
exact commands, final source hashes and independent review results here.

Commands for the current integration, from the owning worktree. The earlier
codec checkpoint retains separate receipts in the parent output directory.

```powershell
$py = "C:/Users/unknown/Projects/Mindict/.venv/Scripts/python.exe"
$toolchain = "C:/Users/unknown/.local/llvm-mingw-20260616-ucrt-x86_64"
$obsBin = "C:/Program Files/obs-studio/bin/64bit"
$headers = "C:/Users/unknown/Projects/Mindict/.grok/obs-native-build/headers"
$output = "C:/Users/unknown/Projects/Mindict/.grok/obs-mix-provenance/integration"
& $py -m pytest tests/test_obs_mix.py tests/test_obs_routing_protocol.py tests/test_obs_protocol.py -o addopts= -q
& $py native/obs-plugin/tools/build.py --toolchain $toolchain --obs-bin $obsBin --headers $headers --output "$output/build"
& $py native/obs-plugin/tools/smoke.py --build "$output/build" *> "$output/build/smoke-run.log"
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --build "$output/build" --headers $headers --output "$output/verification"
& $py -m pytest tests/test_obs_session_ui.py -o addopts= -q
```

## Current work and open decisions

The preceding controller checkpoint remains frozen. Bounded immutable models,
Python framing and the independent C encoder are implemented and independently
reviewed. The following codec evidence belongs to checkpoint `5183cc2`;
it does not verify the in-progress integration described below.

The focused model/routing/legacy codec bundle passes **224 tests**. The canonical
driver passes **796 affected desktop tests** and all **51 native commands**;
the **24-command linked build** and headless refusal smoke pass. The audit matches
all **446** recorded source, SDK, tool, generated-file, runtime, artifact and log
hashes. The existing native v1 wire vectors remain unchanged. Independent C and
Python review is clear, including the corrected blank/invisible-label policy.

Local evidence lives under `.grok/obs-mix-provenance/`: build/smoke receipts in
`build/`, canonical `verification/test-receipt.json`, focused `codec/` evidence
and `hash-audit.json`. No OBS application, audio device, consumer profile or
model was used. This proves the component checks, not the remaining package
acceptance or live OBS behavior.

### Current integration

The receiver, private routing history, transcript ownership and explicit v2
pipe/controller path are implemented. Routing is validated against accepted
per-bus sequence positions before publication. Initial metadata must follow Start
and precede PCM; a pre-Start Disarm creates neither audio nor metadata stores.
Each later accepted observation has exactly the next wire revision. Equal
observation timestamps are allowed; these timestamps are not sample boundaries.

The private journal queues at most eight bounded records and performs file I/O
on its own worker. Disk-backed history remains with the transcript owner after
audio is released. Cancellation clears visible metadata immediately, then waits
off the UI thread for owned files and active readers to close. Cleanup failure
remains visible even after a formerly complete or cancelled result. Review found
and fixed an internal recognition-cancellation path that had omitted history
closure after ownership transfer.

The view places latest mix details beside the transcript in a tab, preserving
the window dimensions and minimum preview heights. It distinguishes complete,
same-input, different-input and unassigned mixes and states timing uncertainty.
It shows configuration observations without identifying speakers or asserting
audibility. Private names are absent from representations and cleared on discard;
selecting text does not publish it to the platform selection clipboard.

Final integration verification passes **873 affected desktop tests**, **48 Tk
checks**, all **55 native verification commands**, the **25-command linked
build** and headless refusal smoke. Eleven synthetic captures include normal
and compact mix-detail tabs. All **488** recorded source, SDK, tool, runtime,
generated-file, artifact, log and UI source/render hash comparisons match.
Evidence lives in `.grok/obs-mix-provenance/integration/`, with the separate
`ui-integration-verification.json` also checked by its `hash-audit.json`.
Earlier 120-check integration evidence describes its original source stage only.

Independent receiver/controller/pipe, private-history, view, native integration
and build-driver reviews are clear. Review corrected cached private metadata
retention on explicit close and external destruction. Keyboard traversal and the
full six-bus, 128-source display bounds are covered. These checks used no OBS
application, audio device, consumer profile or model. Source CI remains pending.

Native observation uses fixed watcher/snapshot limits and an OBS monotonic clock
declared by the newly pinned public `util/platform.h`; its ISC notice is retained.
Independent review found and fixed an old-worker/new-session snapshot race by
serializing lifecycle mutation and snapshot access. Synthetic close/reopen checks
pass. OBS's own signal-disconnect calls can wait for foreign signal callbacks
before the local quiescence timeout begins; this is a public-API teardown limit,
not a proven globally bounded close. Scheduler callbacks use a nonblocking
frontend post and fail visibly if its state lock is contended.

Final native review corrected three lifecycle races. Normal stop or Disarm can
close observation before initial Routing reaches the pipe, so the exact-generation
immutable snapshot remains readable through the bounded audio drain; worker
retirement wipes it. Stale queued refresh commands cannot stop a newer capture.
Snapshot comparison and publication revalidate lifecycle state under the same
lock as worker retirement, preventing a paused refresh from republishing after
retirement. Deterministic fixtures cover each race and callback scheduling
contention. Independent reruns pass on the same frozen native inputs.

Production source advertises and requires audio version 2. Protocol/command
versions remain 1. Older audio-version-1 plugins and unknown future versions are
refused before Arm. Actual live OBS/audio/load acceptance, application entry,
export integration and native distribution remain open.

Copy source names and UUIDs entirely inside the enumeration callback. The pinned
[core implementation](https://github.com/obsproject/obs-studio/blob/ba2f32bdf791005443988a4955e963663e16b1ed/libobs/obs.c)
holds the source mutex across that callback; source renaming and UUID reset use
the same mutex. A retained reference also prevents destruction. This is a
pinned-implementation constraint: the public getter API does not separately
promise borrowed-string lifetime or thread safety outside enumeration.

### Observation semantics

The public [source API](https://docs.obsproject.com/reference-sources) describes
assignment and rename signals but supplies no audio timestamp or documented
sample-effective ordering. The [core API](https://docs.obsproject.com/reference-core)
provides input enumeration and source lifecycle signals. These support observed
configuration snapshots, not proof of which input was audible in each sample.

Keep PCM continuous on ordinary assignment changes. Do not pause/drop capture to
make labels appear more precise. Record the OBS monotonic observation timestamp
and exact per-bus next-sequence positions when the worker publishes an update.
Those positions serialize metadata with the transport; they are not the instant
the routing took effect. Describe historical entries as observed assignments,
with uncertainty explicit. A later observation never rewrites earlier entries.

### Version 2 routing component

The 12-byte ULAP header retains its existing layout. Version 2 adds kind 5;
existing Start/Audio/Gap/End body layouts are unchanged. Python encoding/decoding
requires explicit version selection and rejects version mixing. The native
runtime and compatibility reply now select version 2, and the desktop status
check requires it before Arm. Explicit legacy codec wrappers and the legacy
stream fixture retain version 1; the new runtime fixture verifies Start,
initial Routing, continuous Audio, later Routing and End under version 2.

Routing body, little-endian:

| Part | Fields |
| --- | --- |
| Prefix, 36 bytes | session ID (16 bytes), revision (u64), observed-at ns (u64), primary bus (u8), selected mask (u8), source count (u16) |
| Each selected bus | bus (u8), next sequence (u64), label UTF-8 length (u16), label bytes |
| Each source | source ID (16 bytes), selected assignment mask (u8), name UTF-8 length (u16), name bytes |

Buses appear once in ascending selected order; sources appear once in ascending
raw-ID order. All source masks are nonempty subsets of the selected mask.
There are at most six bus labels of 64 UTF-8 bytes and 128 source names of 128
bytes. The maximum body is 19,302 bytes. Revisions range from 1 to u64-max minus
one; next-sequence positions may include u64-max after sequence exhaustion.

Whitespace-only and joiner-only text, controls and directional overrides are rejected.
Normal RTL text, meaningful Persian non-joiners and emoji joiners are preserved;
names are not silently trimmed or normalized. Invalid input produces generic
errors and cannot leave partially encoded native output. Source IDs/names and
bus labels are absent from model/frame representations.

The codec does not validate session authority or update order. Integration must
require initial revision 1, exact next revisions, monotonic observation time,
unchanged selected/primary buses, and positions equal to the receiver's accepted
sequences before committing a record. Its private history must be bounded in
memory and survive slow recognition without silently losing observations.

## Non-goals and stop

Recorded-file stream selection and global PTS handling follow as a separate
reviewed increment. Do not add diarization, automatic source selection, microphone
capture, model downloads, plugin installation or publication here.

Stop editing this package after the complete metadata/boundary contract,
integration checks and independent review pass, with the roadmap accurately
describing remaining live OBS/audio/load and native distribution gates. Keep the
full desktop and original Android completion goal active.
