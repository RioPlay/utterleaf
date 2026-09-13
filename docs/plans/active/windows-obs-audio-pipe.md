# Windows OBS audio pipe

Status: client implemented and independently reviewed; native synthetic Windows
checks pass. Final integrated regression is recorded below. September 12, 2026.
Follows the reviewed
[TCP peer identity gate](windows-obs-peer-identity.md) and
[OBS audio design](obs-audio-design.md).

## Goal and area

Implement the local client side of the original OBS audio bridge: bind one named
pipe to the already verified OBS process before exchanging session credentials,
then receive bounded binary audio for the existing protocol/session receiver.
The audio connection must retain its own process identity so a degraded control
connection cannot silently replace or invalidate an otherwise healthy active
audio session. This component does not itself arm or record.

The source is `windows_pipe.py`, `obs_audio_pipe.py` and the process-lease additions
to `windows_peer_identity.py`, `obs_websocket.py` and `obs_control.py`, all under
`utterleaf/`. Corresponding desktop tests include the shared native fixture
`tests/windows_pipe_server.py`. Root owns the integrated files after delegated
handoff. An independent reviewer checks native API usage, identity/handshake
ordering, cancellation, handle lifetime and evidence. Keep desktop source and
dependencies separate from Android.

## Constraints and implementation contract

- Open only an exact local per-session pipe name in a fixed Utterleaf namespace.
  Reject remote servers, arbitrary namespaces, traversal and alternate names
  before native I/O. No pipe discovery, automatic retries against another server,
  OBS launch/configuration changes or user credentials from saved files.
- Use overlapped Windows pipe I/O, bounded buffers and explicit ctypes ABI.
  Disable server impersonation privileges with an explicit identification-level
  security quality of service. No inherited native handles.
- Verify the pipe's server PID against a retained handle for the live process
  originally attributed to the authenticated WebSocket connection. Transfer an
  independently owned process lease; a PID supplied only by vendor JSON is not
  sufficient. The server must separately validate the expected client process,
  same user/session and a restrictive pipe DACL in the future native plugin.
- Exchange any fresh single-use session secret only inside that verified pipe;
  vendor JSON carries only nonsecret metadata. A session ID alone is not peer
  authentication. The fixed handshake layout and checks are recorded below.
  Reject unexpected bytes before audio delivery.
- Read/write at most 65,536 bytes per operation. Poll cancellation and deadlines
  without a detached worker touching freed buffers. Cancel pending I/O and observe
  completion before releasing OVERLAPPED storage, buffers, events or handles.
  Windows cancellation and metadata operations do not provide hard kernel-time
  guarantees; document that limit rather than freeing pending native memory.
- No logging or persistence of pipe secrets, PCM, transcripts, process paths or
  native error payloads. Exceptions and repr remain generic. Importing modules
  opens no handle/socket and captures no audio.

## Identity handoff and handshake

Authenticated control exposes `retain_peer_process()` after both Identify and
GetVersion have succeeded. While holding the existing peer lock, it revalidates
the exact TCP peer and duplicates the retained process handle with the same
rights and inheritance disabled. The independent lease verifies an exact pipe
server PID, live original process object and same user/session; it never looks up
the old TCP tuple after handoff. Closing the control and expected-file leases
does not close this separate process lease. Multiple leases may be retained;
the future plugin arm/session state supplies the one-use policy.

`obs_audio_pipe.connect` consumes that independent lease on every exit. Its only
locator input is the exact 16-byte nonsecret session ID; it constructs
`\\.\pipe\Utterleaf.OBS.<32 lowercase hexadecimal digits>` internally. It verifies
the process before opening, queries the actual pipe server PID after opening,
and repeats PID/process checks immediately before sending any secret bytes.

Both handshake records are exactly 56 bytes, little-endian `<4sBBH16s32s>`:

| Field | Client Hello | Server ACK |
| --- | --- | --- |
| Magic/version/kind/reserved | `ULAH`, 1, 1, 0 | `ULAH`, 1, 2, 0 |
| Session ID | Explicit 16-byte vendor session ID | Exact same ID |
| Payload | Fresh cryptographic 32-byte client secret | HMAC-SHA-256 result |

The HMAC key is the fresh secret; its message is the ASCII domain
`Utterleaf OBS audio server ack v1` followed by one zero byte and the complete
24-byte canonical Client Hello header, including its role and session ID. Compare
the ACK MAC in constant time. This confirms receipt of the fresh secret after
OS peer binding; it does not independently attest code inside OBS. The future
server validates the connecting expected client PID/user/logon session before
its first read and consumes a session once. The client never reconnects a failed
session. Mutable secret/Hello construction buffers are cleared best-effort;
Python/HMAC copies cannot be guaranteed erased.

After ACK, each bounded read rechecks server PID and the independent process
before and after I/O. Bytes feed the existing ULAP decoder; every frame must carry
the same session ID. End must be the last frame, with no trailing partial frame.
Consent, post-arm start ordering, bus selection and temporary stores remain the
receiver/controller's responsibility. A pipe timeout or malformed/failed read is
terminal, leaving the future controller to preserve an explicitly incomplete
prefix. An idle armed session needs its own heartbeat/start coordination before
using the active-audio read timeout; this component does not supply that policy.

Primary API references:

- [DuplicateHandle](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-duplicatehandle)
  describes independent handle ownership, equal rights and noninheritance.
- [Pipe names](https://learn.microsoft.com/en-us/windows/win32/ipc/pipe-names) and
  [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
  define the local namespace, overlapped access and identification-level SQOS.
- [Server PID](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeserverprocessid)
  documentation describes server attribution but ambiguously names a
  CreateNamedPipe handle; actual client CreateFile-handle behavior is a required
  native fixture, not a claim inferred solely from that wording.
- [CancelIoEx](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex)
  does not await completion; retain buffers until
  [GetOverlappedResult](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-getoverlappedresult)
  observes completion, including cancel/normal-completion races.
- The future server's [CreateNamedPipeW](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew)
  must use an explicit restrictive DACL, one instance and
  `PIPE_REJECT_REMOTE_CLIENTS`; the default DACL is insufficient. Validate the
  [client PID](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid)
  and same logon session before reading a secret. Synthetic server fixtures are
  not a substitute for this original plugin implementation and review.

## Acceptance and verification

Use unit fixtures for strict naming, ABI/flags, partial and zero-byte I/O,
fragmentation, server PID mismatch/exit, independent process lease ownership,
deadline/cancellation races, malformed or replayed session handshakes, and exact
cleanup. Use harmless native Windows child peers with ephemeral local pipe/TCP
names to prove the actual I/O and identity boundary. No OBS instance or audio
device is needed for this component's native checks.

Run each affected module's focused pytest first, then integrated OBS/privacy/
configuration/boundary checks and full desktop regression for the new native
authentication boundary. Obtain independent source and evidence review. Actual
OBS/plugin compilation, restrictive server DACL/client validation, atomic arming,
cross-channel event ordering, visible UI, live recognition, streaming-load and
release tests remain required before claiming the live workflow complete.

The native integration fixture uses one self-expiring child process that owns an
ephemeral loopback TCP socket and the corresponding named pipe. The client first
attributes that child using the actual Windows TCP/process APIs, retains an
independent handle, authenticates the actual pipe and closes TCP. The original
TCP check then fails while the pipe continues returning the expected ULAP
Start/Audio/End sequence into `ObsCaptureSession` and a real temporary store.
Another native fixture owns a different process's pipe and reports only its byte
count: wrong-process refusal leaves that count at zero. These checks ran without
OBS or a microphone; synthetic-server security is not production-plugin evidence.

The fixed HMAC vector was independently computed with .NET
`System.Security.Cryptography.HMACSHA256`: ASCII `s` repeated 32 times as key,
session bytes `00` through `0f`, and the canonical domain/Hello header above
produce `f1893739588fa57f393e5b7ca8ffcc3319a3d0f332c4533994b8581c37e8b636`.
The client accepts this fixed ACK and rejects a replay made with an old key.

### Review result

Independent review cleared the process handoff, mandatory authenticated-control
gate, handshake/framing and native overlapped transport. Fault-injection findings
fixed before acceptance included handle leaks during pipe/OVERLAPPED/event-field
construction and cancellation failures that could bypass completion observation.
The final drain waits for an actual completed result even if cancellation fails,
distinguishes `ERROR_IO_INCOMPLETE`, and paces incomplete/exceptional retries by
50 ms. A backoff interruption is deferred until native completion; persistent
native failure may therefore prevent cleanup from returning. No hard kernel
deadline, detached cleanup worker or safe early buffer release is claimed.

Focused suites pass **47 process identity**, **142 control/transport** (93/49),
**23 native pipe**, and **27 audio handshake/receiver** tests. The final separate
reviewer reran all 23 pipe tests in 3.51 seconds and cleared the final pacing
delta. Native receipts use Windows 11 build 26200, Python 3.14.6 and x64 pointers;
they do not establish other desktops, installed OBS behavior or streaming-load
performance. No additional dependency or packaged binary was created.

Root verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_windows_pipe.py tests/test_obs_audio_pipe.py tests/test_windows_peer_identity.py tests/test_obs_control.py tests/test_obs_websocket.py tests/test_obs_protocol.py tests/test_obs_session.py tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py tests/test_packaging_media.py
.\.venv\Scripts\python.exe -m pytest
```

The integrated focused run passed **385 tests in 6.29 seconds**. Full desktop
regression passed **1,432 tests, 13 skipped in 39.47 seconds**. This closes the
client component's implementation/review increment; it does not complete live OBS.
Continue with the [original plugin build](obs-plugin-build.md), production server
authentication, controller and the end-to-end gates above.

## Non-goals and stop

No remote transport, ambient recording, app startup connection, OBS setup,
automatic plugin/model/toolchain installation, copied keyboard/plugin code,
manual artifact deletion or consumer streaming changes. Stop editing this
component after named native, integration and review checks pass; continue with
the original server plugin, controller and end-to-end audio acceptance.
