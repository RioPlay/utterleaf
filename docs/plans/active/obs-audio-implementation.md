# OBS audio implementation

## Goal and scope

Implement the live workflow in the [OBS design](obs-audio-design.md): a visibly
armed desktop session receives the actual OBS streaming mix, optionally separate
OBS buses, and transcribes locally without changing stream or recording settings.
This plan records implementation progress; protocol tests alone do not establish
live OBS support. Desktop speech-end stopping is already implemented and reviewed
in source; its physical microphone and release gates remain separate.

## Current increment

The bounded audio protocol, consent/session receiver and read-only loopback
WebSocket control client are reviewed. The Windows TCP peer identity gate is now
implemented and integrated, as recorded below. Continue with the original native
plugin/server and its authenticated audio endpoint. Root owns the integrated source,
tests and this plan after delegated handoff; assign each next component one writer
and a separate reviewer under the repository's ownership rules.
No runtime/UI entry is exposed until the authenticated transport can satisfy the
complete capture contract.

The control increment uses the maintained `websockets` library, pinned to 16.1.1
to preserve Python 3.10 support. Its BSD-3-Clause notice must enter the desktop
notice inventory. The library has no runtime dependencies. Verification uses a
harmless synthetic server bound to an ephemeral loopback port, never the user's
OBS configuration, password or audio. The client rejects nonlocal addresses,
proxies, redirects, unauthenticated Hello messages, unsupported RPC versions,
malformed/oversized messages and mismatched responses. It subscribes to General
and Outputs for shutdown and stream lifecycle events, discards unrelated events
without retaining their data, and sends only read-only status/version requests.
Connecting or observing an event does not arm the audio receiver. Native bridge
vendor requests and recording readiness remain a later integration step.

Control acceptance includes a real challenge-response handshake, wrong-password
failure, status and event ordering, cancellation during blocked network operations,
bounded deadlines/queues, safe close, no reconnect and no credential/payload logs.
Run the focused control/transport checks, affected dependency/privacy/boundary
checks and full desktop regression after independent review. Stop this component
when those checks pass; the native audio bridge and complete live workflow remain
required by the full goal.

The [control dependency record](../../desktop-obs-control-resource.md) records the
exact verified development wheel and full-license copy receipt. The existing OBS
debug logger can record vendor JSON; the revised design reserves that channel
for nonsecret metadata and exchanges future pipe secrets only inside the verified
pipe. WebSocket challenge-response alone does not prove server process identity.

The protocol uses little-endian framing, a version and bounded payload length.
It carries an opaque session ID, actual mixer-bus identity, monotonically ordered
sequence numbers, OBS nanosecond timestamps and finite stereo float32 samples.
An explicit start describes the sample rate, primary bus, selected buses and
timeline origin. Gaps and terminal reasons remain visible; no duplicated audio,
invented speaker labels, silently concatenated gaps or guessed complete results.

The receiver is idle by default. A confirmed idle OBS state and explicit arming
precede a subsequent streaming start. Connecting to an already active stream,
stale sessions, replayed messages and reconnects cannot start capture. Session
identity comes from the authenticated transport; a binary session ID alone is
not authentication. Audio storage is local and bounded by the existing queue
and free-space policy. Native callbacks must never wait for storage or inference.

## Acceptance and verification

- Protocol tests exercise fragmentation, coalescing, fixed bounds before payload
  allocation, malformed headers and PCM, non-finite samples, sequence metadata,
  zero/oversized blocks, truncation and terminal failure without resynchronizing.
- Receiver tests exercise explicit arm/start, already-active refusal, stale and
  replayed sessions, per-bus order and timestamp continuity, gaps, stop/cancel,
  startup/storage failure, and cleanup without automatic paste or export.
- Connect the native plugin and same-user authenticated Windows pipe, then verify
  the actual primary encoder's bus with synthetic OBS audio. No real microphone
  or consumer stream configuration is needed for deterministic tests.
- Follow the full design's live non-interference, multibus/timeline, security,
  distribution and platform acceptance gates before claiming the workflow done.

Initial commands: `.\.venv\Scripts\python.exe -m pytest tests/test_obs_protocol.py
tests/test_obs_session.py`, then affected storage/privacy/boundary tests and
independent implementation review. Use native build and OBS receipts for transport
acceptance; pure Python tests cannot replace them.

## Wire version 1

All integers use little-endian order. The 12-byte header is `<4sBBHI`: magic
`ULAP`, version `1`, kind, zero reserved bits and body length. Kinds are Start=1,
Audio=2, Gap=3 and End=4. Reads are capped at 65,536 bytes, a body at 65,573 bytes,
and an audio block at 8,192 stereo frames (65,536 bytes of interleaved float32).
Kind-specific lengths are checked as soon as a full header arrives. A malformed
or truncated stream is terminal; the parser never searches for another magic
sequence inside rejected audio. It does not authenticate a peer.

| Body | Fields and layout |
| --- | --- |
| Start, 30 bytes | `<16sIBBQ`: session ID, sample rate, primary bus, selected-bus bitmask, origin nanoseconds |
| Audio, 37 bytes plus PCM | `<16sBQQI`: session ID, bus, sequence, timestamp nanoseconds, frames; then exactly frames × 2 × 4 bytes |
| Gap, 41 bytes | `<16sBQQQ`: session ID, bus, first missing sequence, missing-block count, timestamp nanoseconds |
| End, 18 bytes plus entries | `<16sBB`: session ID, reason, entry count; one sorted `<BQ>` bus/last-sequence entry per selected bus |

Bus numbers are zero-based 0–5. Supported rates are 16,000, 32,000, 44,100, 48,000,
88,200 and 96,000 Hz. A Start mask must include its primary bus. PCM must be finite;
it is not amplitude-clamped by the wire protocol. Audio sequences begin at zero
per bus. The largest uint64 value is reserved for End's no-frame sentinel; real
sequences and Gap ranges must stay below it. End reasons are Stream stopped=1,
Disarmed=2, OBS exit=3, Source changed=4 and Transport error=5.

The native bridge must convert copied native OBS planes to the negotiated wire
format on its worker, with any rate/layout conversion explicitly verified. It
must not request extra format conversion on OBS's audio callback thread merely
to satisfy this wire layout. Surround-layout support is not established by the
stereo protocol and remains a native adapter acceptance case.

## Receiver implementation

`ObsCaptureSession` is a single-use receiver created by an explicit arm after an
authenticated idle snapshot. It requires a subsequent stream-start notification
and a matching Start descriptor before creating any store. The default selection
means the actual primary stream mix, whose bus is resolved by the authenticated
plugin after streaming starts. Explicitly requested additional buses must all be
present, and no unsolicited extra bus is accepted. A requested additional bus
that is also primary is deduplicated. No idle-profile or Track 1 guess is needed.
Each selected bus has
its own bounded `CaptureStore`, sequence count and first OBS timestamp. Downmixing
uses bounded float64 accumulation to avoid overflow of finite float32 inputs.

Timestamps are checked against cumulative source-frame counts with at most one
nanosecond of integer-clock tolerance. The first timestamp of each bus remains
relative to the declared common origin, so a late bus is not silently shifted to
zero. Actual export must carry those offsets; the existing independent file-import
route does not yet preserve a container's cross-track timeline.

The first missing/repeated sequence, explicit Gap, timestamp discontinuity,
unselected bus or storage failure seals every store and labels the result
incomplete. This initial receiver keeps the contiguous prefix and stops; it does
not concatenate audio on opposite sides of a gap. Only a matching End with every
selected bus's last sequence can finish cleanly. A track with no samples or a
late writer error cannot become a complete result. The owner must drain writers
with cancellation, inspect completeness, and close all stores on every exit.
Taking a result transfers that ownership exactly once. Cancel discards the
receiver's stores and never rearms it.

The current protocol/receiver tests pass **125 cases**. They include independent
wire construction, fragmented/coalesced messages, real two-bus temporary storage,
distinct sample levels, automatic primary-mix selection, late-bus offsets,
single-frame 48 kHz and cumulative 44.1 kHz clock rounding, replay/gap/early
audio refusal, startup and late-write failure, result ownership and cancellation.
Independent review identified and resolved a tolerance that accepted a whole-sample
overlap or gap. The revised check admits only integer-nanosecond rounding; both
whole-sample and fractional-clock discontinuities have regression tests. Re-review
cleared the timing, actual-primary and writer-drain changes with no remaining
component blocker. Full desktop `.\.venv\Scripts\python.exe -m pytest` passes
**1,193 tests, 13 skipped in 48.40 seconds**; the earlier focused protocol/receiver/
storage/privacy/config/boundary bundle passed **164 tests** before the final ten
receiver regressions were added. No native transport, OBS plugin, visible
controller, live recognition, automatic stream following or release is implemented
by these modules alone.

## Native environment and evidence

### Control connection implementation and review

`obs_websocket.py` now opens a real, direct numeric socket to exactly `127.0.0.1`
or `::1`, with an explicit port. The maintained threaded WebSocket client receives
that preconnected socket; proxy use, compression, automatic reconnect and payload
logging are disabled. The negotiated subprotocol must be `obswebsocket.json`.
Messages are limited to 65,536 bytes and the library frame queue high-water mark
is four. Connect/upgrade takes at most five seconds, sends two seconds and close
one second, with owned socket shutdown used to interrupt blocked operations.
Receive uses short timed waits. The supplied cancellation callback must be prompt
and nonblocking, such as `threading.Event.is_set`; an arbitrary blocking callback
would invalidate that timing contract. These are application operation budgets,
not a hard real-time scheduling guarantee.

`obs_control.py` requires a password-protected Hello, computes OBS's documented
challenge response and waits for RPC 1 identification before requesting version
information. The response must advertise the required read-only requests and a
5.x WebSocket version. Only `GetVersion` and `GetStreamStatus` are allowed; there
is no arbitrary request passthrough. The General/Outputs subscription mask is 65.
Only stream lifecycle events are retained, with a 32-event limit; shutdown closes
the control connection. Unrelated event payloads, including recording paths, are
discarded. Events arriving after Identify but before Identified stay quarantined
until login/version checks succeed. Pending stream events explicitly flag a
status snapshot as stale; snapshots do not establish permission to arm.

JSON rejects duplicate keys, oversized UTF-8, non-finite numbers (including
exponent overflow), invalid envelopes and mistyped fields. Responses must match
the pending request's type and connection-specific ID. Relevant event types must
match their subscribed category. Timeout, malformed data, cancellation and
connection loss close the single-use client without reconnecting. Credentials
are not stored on the client or in preferences; Python strings cannot be securely
erased, and callers must not log exception locals or dump credential memory.

Independent review cleared the initial internal component after tightening cancellation
cleanup, event category validation and login/shutdown coverage. The control and
transport suites initially passed **122 tests** (83 control, 39 transport). Real ephemeral
loopback peers exercise challenge response, rejected credentials with close 4009,
ordered events, negotiated JSON, fragmented messages, binary/oversized rejection
and actual send backpressure. The backpressure check observes the library receiver
thread terminated and no remaining watchdog. The Unicode authentication vector
was independently verified with .NET SHA-256, and a DEBUG-level logging test sees
no client payload/credential records. These are synthetic local peers, not the
user's OBS instance; native OBS interoperability was not established. Subsequent
Windows peer-identity fixtures below add local IPv6 evidence.

That increment's combined OBS protocol/receiver/control/transport and privacy/configuration/
boundary/packaging checks passed **268 tests in 1.32 seconds**. Full desktop
`.\.venv\Scripts\python.exe -m pytest` passed **1,315 tests, 13 skipped in 38.74
seconds**. The verified dependency's complete BSD license also passed the notice
collector's byte-for-byte temporary-output check. No packaged release was built.

The [Windows TCP peer identity check](windows-obs-peer-identity.md) now requires
`expected_executable` on both connection APIs with no verification bypass. It
retains the selected file and exact TCP-owning process, checks user/session and
full path/current file identity before HTTP upgrade, revalidates before the
authentication proof and subsequent I/O, and closes both leases on every exit.
It never opens or resolves the untrusted reported image path. There is no new
third-party dependency; native Windows API calls remain synchronous between
deadline/cancellation checks. This proves process attribution under the documented
constraints, not historical loaded-image bytes or actual OBS compatibility.

That identity increment passed **37 tests**, and control/transport passed **130 tests**
(86 control, 44 transport). On Windows 11 build 26200, Python 3.14.6, x64, actual
IPv4 and IPv6 child-process fixtures identify the server rather than the client.
Native transport fixtures complete a synthetic authenticated control session and
reject a wrong expected executable before sending any HTTP bytes. Fake native
fixtures cover SID/token/TCP returned-buffer bounds, the 16 MiB allocation cap,
three growth retries, reserved PIDs, path rejection before filesystem access,
cancellation between query stages and exact handle cleanup. No OBS instance,
consumer credential or audio device is used.

Independent review cleared the identity implementation and integration after the
documented native-buffer, path and cancellation fixes. The combined identity/
control/transport/protocol/receiver/privacy/configuration/boundary/packaging run
passed **313 tests in 2.23 seconds**. That full desktop run passed **1,360
tests, 13 skipped in 38.68 seconds**. Native OBS enrollment
and interoperability remain open. The client-side
[Windows audio pipe](windows-obs-audio-pipe.md) now has an independent retained
process lease, native overlapped transport and a fixed session handshake before
ULAP decoding. Native synthetic child tests cover continuity after TCP loss and
wrong-process refusal with zero secret bytes received. Independent review cleared
the client after native ownership, cancellation-drain and retry-pacing fixes.
Current suites include 47 identity, 142 control/transport, 23 pipe and 27 audio
handshake/receiver checks. The combined OBS/identity/pipe/privacy/configuration/
boundary/packaging run passes **385 tests in 6.29 seconds**; full desktop regression
passes **1,432 tests, 13 skipped in 39.47 seconds**. The original native server
bridge, restrictive server DACL/client identity, atomic idle-to-arm gate,
cross-channel start ordering, visible controller and live recognition remain open. OBS debug
JSON must never carry the audio pipe secret. No app entry point currently imports
these control modules, and they do not connect, capture or change OBS on import.

### Installed native runtime

Read-only inventory found OBS **32.2.2** installed, with runtime DLLs but no OBS
headers/import libraries or Visual Studio/Microsoft Windows SDK. A subsequent
targeted inventory found an existing Windows-targeting LLVM-MinGW toolchain and
undecorated C exports in the installed OBS DLLs. The
[original plugin build plan](obs-plugin-build.md) records a viable C-only header/
import-library route, its upstream-support distinction and remaining compile/load
proof. No OBS process, profile, credentials, audio device, stream or recording was
opened or changed by inventory. Native compilation still needs pinned public
resources and actual build/load validation; a new large toolchain installation
is not yet established as necessary.

The exact 32.2.2 [public encoder API](https://github.com/obsproject/obs-studio/blob/32.2.2/libobs/obs.h#L2126-L2132)
and [implementation](https://github.com/obsproject/obs-studio/blob/32.2.2/libobs/obs-encoder.c#L1084-L1098)
confirm `obs_encoder_get_mixer_index`. Use the active streaming output's slot-zero
audio encoder after pointer/type/range validation. Do not replace the actual
encoder check with guessed Track 1 or a read of the user's profile configuration.

The [audio callback implementation](https://github.com/obsproject/obs-studio/blob/32.2.2/libobs/media-io/audio-io.c)
uses borrowed buffers and calls consumers on its audio thread. Native-format copy
must stay bounded; conversion and pipe I/O belong on the plugin worker. Disconnect
off the callback thread before freeing callback state. OBS timestamps use a
monotonic media clock with cumulative-frame integer conversion, not wall-clock
timestamps or independently rounded block durations. These are source-derived
design constraints, not measurements of an installed integration.

## Constraints, non-goals and stop

Preserve existing uncommitted work, original code and desktop/Android separation.
No microphone, process-presence trigger, startup capture, remote address, plugin
installation, credentials in ordinary configuration/backup, cloud fallback or
automatic export. Do not copy OBS/FUTO/LatinIME implementation code. Do not
change ordinary dictation or file-import behavior merely to scaffold OBS.

This increment is not the final feature. Stop editing each reviewed component
when its named checks pass, then continue the native plugin/server transport, controller/UI,
live recognition and full OBS acceptance gates. The app remains incomplete until
the full user workflow and release requirements are verified.
