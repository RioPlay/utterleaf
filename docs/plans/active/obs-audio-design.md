# OBS audio integration design

Status: live OBS integration is not implemented or device-verified. Internal
protocol, receiver, control, identity and audio-pipe client components are recorded
in the [implementation plan](obs-audio-implementation.md).
Updated September 12, 2026.

## Decision

Use a small, original native OBS plugin as the audio boundary and the built-in
OBS WebSocket 5.x service as the authenticated control and lifecycle boundary.
On Windows, the plugin sends raw PCM over a per-session named pipe restricted to
the interactive user's security token. Utterleaf must first connect to the
password-protected WebSocket service on an explicit loopback address and call a
plugin vendor request to create the pipe. Bind the pipe to the expected process
and user before exchanging its single-use secret inside that pipe. Refuse
hostnames and non-loopback addresses in the first implementation. This is the
recommended design, based on the official APIs below; native OBS acceptance is
still required.

The plugin remains idle after OBS loads. Utterleaf's OBS feature is disabled by
default, and enabling it does not capture audio. The user must arm it visibly for
the current Utterleaf session. Only a subsequent successful streaming-start event
may begin audio delivery. Disarm, OBS stream stop, Utterleaf cancel/quit, pipe
failure, authentication failure, or OBS exit ends the session. Starting OBS,
connecting WebSocket, reconnecting after a lost session, or finding a stream
already active must never create a new capture by itself.

OBS WebSocket is control only. Its documented protocol has stream and record
state, input-to-track assignment, meter, and caption operations, but no PCM audio
operation. `StreamStateChanged` contains only `outputActive` and `outputState`.
`GetInputAudioTracks` returns enable flags, not samples; `GetRecordStatus` returns
recording state, duration and byte count. A WebSocket-only implementation cannot
meet the audio acceptance requirement. OBS recommends password protection for
the built-in service.

Sources:

- [OBS remote-control guide](https://obsproject.com/kb/remote-control-guide)
- [OBS WebSocket 5.x protocol](https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md)
- [OBS WebSocket plugin vendor API](https://github.com/obsproject/obs-websocket/blob/master/lib/obs-websocket-api.h)

## Exact live transport

At `OBS_FRONTEND_EVENT_STREAMING_STARTED`, the plugin obtains the current output
with `obs_frontend_get_streaming_output()`, obtains audio encoder slot zero with
`obs_output_get_audio_encoder()`, and reads its OBS mixer index with
`obs_encoder_get_mixer_index()`. This identifies the bus actually feeding the
primary stream audio instead of assuming Track 1. If any step is unavailable or
ambiguous, fail visibly rather than substitute a microphone, desktop device, or
configured recording track.

The plugin connects a read-only callback to that index on `obs_get_audio()` using
`audio_output_connect()`. That API supplies a chosen mix, conversion request, raw
frames, and an OBS timestamp; OBS exposes at most six audio mixes. Use native
format/rate/layout in the callback and copy the borrowed planes into bounded
preallocated storage. Convert to the negotiated wire format on the plugin worker:
requesting conversion in `audio_output_connect` can run that work on OBS's audio
thread. The initial receiver wire accepts stereo float32; native surround-layout
conversion remains an explicit adapter acceptance case. These source-derived
constraints must be confirmed with an actual supported stream.

Optional separate transcripts select additional OBS mixer indices, never stereo
channels. A plugin snapshot records each selected bus number and the inputs whose
`obs_source_get_audio_mixers()` mask includes it. OBS WebSocket's
`GetInputAudioTracks` may present the same assignment for setup diagnostics. A bus
is labelled with its user-provided name, such as "guest" or "mic"; Utterleaf does
not infer a speaker. If a bus contains several inputs, it is another mix. If it
duplicates the complete mix, it must be flagged or omitted rather than presented
as an isolated speaker.

The named-pipe protocol is versioned and length-prefixed. Its handshake carries
the nonsecret vendor-request session ID and a single-use random secret exchanged
inside the verified pipe, never in WebSocket vendor JSON. Start describes the
sample rate, actual primary bus, selected buses and timeline origin. Each audio
message carries session ID, bus index, sequence number, OBS timestamp in
nanoseconds, frame count and stereo float32 little-endian payload. A
terminal message carries the reason and last complete sequence. The pipe DACL
permits only the same Windows user, the server validates the connecting process
token, and the secret is accepted once and never logged. WebSocket credentials,
pipe secrets and PCM never enter ordinary configuration backup.

The pinned OBS WebSocket server logs decoded incoming and outgoing JSON when its
debug option is enabled. Vendor requests/responses therefore carry only nonsecret
session metadata: protocol version, session ID, selected buses, expected process
ID and pipe locator. Validate the expected server/client process and Windows user
before sending any pipe secret. OBS's password challenge authenticates a client
to the server; it does not independently prove the identity of a local server
process. Do not present it as mutual audio authentication. See the
[pinned server implementation](https://github.com/obsproject/obs-websocket/blob/1ef34bf48110c2a18184e50e41cd0b1a855e2147/src/websocketserver/WebSocketServer.cpp).

The internal Windows control component now requires an explicitly selected local
executable and verifies the connected TCP peer before HTTP upgrade and before
sending the authentication response. It checks the exact established server tuple,
retained live process, same user/session, expected full image path and current file
identity; subsequent control I/O revalidates the peer. See the
[identity implementation and limits](windows-obs-peer-identity.md). This is process
attribution, not proof of historical loaded bytes or protection against injected
same-user code. A malicious local listener can solicit a challenge response;
checking the audio pipe later cannot retroactively protect it. Native synthetic
Windows tests cover this boundary. The [audio pipe client](windows-obs-audio-pipe.md)
now retains an independent process handle, verifies the pipe server before its
fixed secret/ACK handshake and returns bounded ULAP frames. Native synthetic
tests prove continuity after TCP loss and zero secret bytes sent to a different
process. OBS executable selection, the original server's restrictive DACL and
client validation, atomic arming, actual PCM callbacks and OBS acceptance remain
separate open gates; the test server is not production server security evidence.

The real-time callback only validates and copies a complete OBS block into a
preallocated bounded single-producer queue, then returns. A separate plugin thread
writes the pipe. A full queue drops whole blocks, advances the sequence and emits
an explicit gap; it must never block OBS's audio thread. Utterleaf marks that
track/session incomplete and keeps recovery/export available. Initial targets are
at most two seconds queued per bus and no unbounded retry, subject to native load
measurement. The plugin does not start, stop, pause, split, reconfigure, or inspect
recording files and does not change audio routing, filters, monitoring, encoders,
stream service, delay, or container format.

Sources:

- [OBS frontend events and streaming output](https://docs.obsproject.com/reference-frontend-api)
- [OBS output and audio-encoder APIs](https://docs.obsproject.com/reference-outputs)
- [OBS encoder mixer-index API](https://docs.obsproject.com/reference-encoders)
- [libobs audio-output callback API](https://raw.githubusercontent.com/obsproject/obs-studio/master/libobs/media-io/audio-io.h)
- [libobs source mixer masks and source capture callback](https://docs.obsproject.com/reference-sources)

The [implementation record](obs-audio-implementation.md) pins current API evidence
to installed OBS 32.2.2 and documents bounded Python framing/receiver progress.
Slot zero is the primary live mix in that release's built-in outputs; validate the
encoder pointer, audio type and mixer range. Additional encoder slots can repeat
the same mixer or represent archive audio, so they must not be presented as
independent speakers or automatically labelled guests. No user profile read or
track-routing change is needed to inspect the actual encoder. Native compilation,
server authentication and live non-interference measurements remain open.

## Session behavior

The Utterleaf state machine is `disabled -> ready -> armed -> active -> finalizing`
with separate `error` and `incomplete` results. "Ready" means authenticated
WebSocket and compatible vendor API; it is not capture. Arming opens the mutually
authenticated audio session while idle. `OBS_WEBSOCKET_OUTPUT_STARTED` begins one
transcript only after the plugin confirms the streaming mix and first ordered PCM
block. `RECONNECTING` and `RECONNECTED` remain within that same session; they do
not reset time or create another transcript. `STOPPED` finalizes it.

If WebSocket disconnects while the authenticated pipe and original session remain
healthy, continue that already-visible session while showing control degraded;
manual disarm remains available through the pipe. If either channel loses session
identity, stop and mark incomplete. A later reconnect may report current status
but requires a new manual arm before any future capture. Source or track assignment
changes during a session create a timestamped boundary and refresh labels; they do
not rewrite prior attribution.

The primary bus is the complete stream mix, including desktop and remote guests
only when OBS actually routes them to the streaming encoder's bus. Utterleaf cannot
manufacture audio that OBS does not receive. A single mixed waveform supports one
mixed transcript and no reliable speaker labels.

## Recorded-file transcription

After-the-fact transcription remains a separate, simpler workflow: the user picks
an OBS recording explicitly, Utterleaf enumerates audio streams, previews stable
metadata and lets the user select the complete mix and optional other tracks. OBS
documents up to six recording tracks and recommends keeping all sources on Track
1 as a playable mix while assigning other buses separately. MKV is resilient and
supports all OBS codec combinations, while FLV supports one audio track. Utterleaf
must accept the user's existing recording choices and never enable recording,
change the selected tracks, or force MKV/remuxing.

For every selected audio stream, preserve decoded frame presentation time:
`seconds = frame.pts * frame.time_base`. Do not concatenate streams at zero or
derive time solely from decoded sample count. Normalize all tracks against the
container timeline origin when it is valid; otherwise use the earliest valid
selected A/V presentation timestamp and disclose the fallback. Preserve each
track's leading offset as silence/timeline offset and preserve internal gaps.
`Stream.start_time` and `Stream.time_base` are per-stream, while FFmpeg defines the
container start as the first component frame. Missing PTS, negative starts,
timestamp discontinuities, codec priming, pause/resume gaps and a track that begins
late are fixtures, not cases to silently zero. After resampling, calculate segment
timestamps from the source PTS plus exact consumed sample counts and add the common
file origin once when exporting TXT/SRT/VTT.

PyAV's documentation says decoded packet/frame timestamps use the stream time
base. FFmpeg also warns that normal timestamp processing may remove an initial
offset and that even `-copyts` can be affected by muxer processing. Any FFmpeg
subprocess fallback therefore needs `ffprobe` evidence and synthetic offset tests;
command order such as `-map 0:a:N`, `-copyts`, and `-start_at_zero` cannot substitute
for an explicit timeline model.

Sources:

- [OBS multiple audio-track guide](https://obsproject.com/kb/multiple-audio-track-recording-guide)
- [OBS audio/video format guide](https://obsproject.com/kb/audio-video-formats-guide)
- [PyAV stream timing](https://pyav.org/docs/stable/api/stream.html)
- [PyAV time bases](https://pyav.org/docs/stable/api/time.html)
- [FFmpeg timestamp options](https://www.ffmpeg.org/ffmpeg.html)
- [FFmpeg `AVFormatContext.start_time`](https://ffmpeg.org/doxygen/7.0/structAVFormatContext.html)

## Alternatives considered

| Approach | Result |
| --- | --- |
| WebSocket events/meters | Keep for authenticated lifecycle and diagnostics. It has no PCM and meter values cannot be transcribed. |
| Native plugin plus named pipe | Recommended. It reaches the actual libobs mix, preserves OBS timestamps and can remain read-only to stream/record settings. It adds a versioned native build and OBS ABI/device acceptance burden. |
| Lua/Python OBS script | Reject for shipping audio. OBS warns scripts can leak or crash like C, Windows Python needs a matching external installation, and callback/byte-buffer behavior across bindings would still need proof. A script adds no advantage over a narrow native boundary. |
| Watch a growing MKV/MP4 | Reject for live use. Recording may be off, paused, finalized late or use another track layout. Starting or changing recording would violate the non-interference requirement. Retain completed files for explicit after-the-fact import. |
| Chunk or split OBS recording | Reject. It mutates the user's recording workflow and introduces boundary/overlap and disk-pressure failure into streaming. |
| Virtual audio device/monitor capture | Reject as the integration contract. It changes system/OBS routing, can create feedback, may omit remote/application sources and does not expose OBS mixer buses reliably. |
| Local RTMP/SRT restream | Reject. It adds a listening network service and encode/decode path, commonly exposes only the transmitted track, and can affect streaming resources. |

OBS documents native modules as the extension mechanism for sources and outputs.
Its scripting documentation requires a matching Python installation on Windows
and warns that improper scripts can crash OBS or leak memory.

Sources:

- [OBS plugin modules](https://docs.obsproject.com/plugins)
- [OBS scripting](https://docs.obsproject.com/scripting)
- [OBS raw multi-track output callbacks](https://docs.obsproject.com/reference-outputs)

## Licensing and distribution gate

Utterleaf is Apache-2.0. OBS Studio and its public plugin template are GPL-2.0;
OBS Studio describes itself as GPL-2.0-or-later. A plugin that links libobs should
be treated as a separate GPL-covered deliverable, with complete corresponding
source, build instructions, license text, copyright notices and dependency
notices shipped beside its binaries. Keep the IPC protocol independently written
and the Apache Utterleaf process separate from the plugin. Do not copy OBS, FUTO,
or third-party plugin implementation code; implement only against documented
interfaces. Do not copy the OBS template boilerplate into the repository merely
for convenience.

This is an engineering compliance recommendation, not a final compatibility
ruling. Before distributing a combined installer, record the exact chosen GPL
version, OBS/libobs headers and binaries, plugin dependencies, source-offer path,
installer separation and notice inventory, then obtain project legal approval.
Pin and test a declared OBS version range; the official plugin template currently
uses Visual Studio 2022 and CMake on Windows, so this is a new native release lane,
not part of the existing Python package by implication.

Sources:

- [OBS Studio repository and license statement](https://github.com/obsproject/obs-studio)
- [OBS plugin template build environments and GPL license](https://github.com/obsproject/obs-plugintemplate)

## Next implementation contract

**Goal:** on Windows, an explicitly armed Utterleaf session begins local
transcription when OBS successfully starts streaming, receives the exact primary
stream mix, optionally receives user-selected OBS mixer buses, and stops safely
without changing the stream or recording configuration.

**Area:** a separately built GPL OBS plugin; an Apache-licensed versioned IPC
client; desktop OBS settings/status; the existing bounded temporary-audio and
recognition pipeline; recorded-file stream selection and timestamp handling.

**Constraints:** local processing remains default; no microphone opens from this
mode; no capture at OBS or Utterleaf startup; no ambient/process-presence trigger;
no credential/audio logging or backup; no automatic recording, routing, model,
codec, plugin or dependency changes; bounded memory and writer queues; no claim of
speaker identity from a mix.

**Acceptance:**

1. A native Windows OBS test proves the captured primary PCM contains a test mic,
   desktop tone and remote-guest tone routed to the live encoder bus, with sample
   alignment and level compared to a reference OBS recording.
2. Separate buses containing distinct synthetic tones produce distinct outputs;
   stereo channels are never listed as tracks, duplicate/combined buses are
   disclosed, and routing changes produce an explicit boundary.
3. Disabled, ready and armed states capture no audio before a post-arm stream
   start. Already-streaming connection, OBS-only startup and WebSocket reconnect
   do not silently create a transcript. Stop, disarm, cancel and quit cleanly end
   callbacks and delete temporary audio according to the existing lifecycle.
4. Wrong WebSocket password, non-local address, wrong pipe user/token, replayed
   secret, plugin/version mismatch, OBS exit, pipe loss and queue overflow fail
   closed and visibly. Secrets are absent from logs, crash reports and backups.
5. Under CPU, encoder and pipe backpressure, the callback does not block the OBS
   audio thread; sequence gaps mark output incomplete. Compare OBS skipped frames,
   audio continuity and stream status with integration disabled and enabled.
6. Imported MKV/MP4 fixtures with two to six audio streams, unequal/negative start
   PTS, late tracks, gaps, pause-like discontinuity and codec priming preserve one
   global timeline through TXT/SRT/VTT export. Unsupported/missing timestamps fail
   visibly without guessed alignment.
7. GPL source, reproducible build instructions, notices and binary provenance are
   reviewed before any plugin binary or combined installer is published.

**Verification:** add deterministic protocol/parser/state tests without OBS;
synthetic multi-bus plugin tests; long bounded-storage/cancellation tests; recorded
file offset/export tests; then native OBS streaming acceptance on a named OBS and
plugin version. Record exact commands, logs with secrets redacted, fixture hashes,
OBS audio/sample settings, stream encoder mixer index and observed results. These
tests do not establish macOS/Linux behavior.

**Non-goals:** live caption injection, diarization, source inference, automatic
OBS setup, recording control, remote OBS hosts, macOS/Linux transport, copied
third-party plugin code, or a plugin/model download flow.

**Stop:** stop the first increment after authenticated Windows primary-mix PCM,
state/cancellation/privacy tests, native non-interference measurements and an
independent implementation/compliance review pass. Add optional buses and file
timeline work as separately reviewed increments.
