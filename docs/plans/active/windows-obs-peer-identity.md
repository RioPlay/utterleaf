# Windows OBS peer identity

Status: implemented and independently reviewed; native synthetic Windows and
integrated desktop checks pass. Actual OBS and audio-bridge acceptance remain open.
September 12, 2026. Follows the reviewed internal
[OBS control component](obs-audio-implementation.md).

## Goal and area

Before sending an OBS WebSocket authentication response, bind the connected
loopback TCP peer to the expected OBS executable, user and interactive session.
Keep an owned process handle through authentication and the control session.
Neither an executable basename nor a password challenge establishes server
identity. This is a prerequisite for a user-facing OBS connection flow.

Implement a Windows-only, import-inert `utterleaf/windows_peer_identity.py` and
focused tests. Integrate it into `obs_websocket.py` after the numeric TCP connect
and before HTTP upgrade; revalidate immediately before `obs_control.py` sends
Identify. Root owns integration. A delegated writer may own the new module/tests
under the repository's one-writer and Aden navigation rules.

The integration requires `expected_executable` on both public connection
functions, with no default that skips verification. The transport owns separate
expected-file and verified-peer leases. The native peer lease borrows the socket
and does not close the expected lease. Transport cleanup serializes with active
native verification, closes the peer and then the expected file, and remains
idempotent after cancellation/socket failure. Identity is checked before HTTP
upgrade, again after Hello before Identify, and before subsequent control I/O.
Native metadata calls are synchronous: deadlines bound retry loops and checks
between calls, not a stalled in-flight Windows operation.

## Implemented native contract

1. Open the explicitly selected, absolute local expected executable with
   `CreateFileW`, read-attributes access, read sharing and `OPEN_EXISTING`. Keep
   its handle. Obtain its normalized final path and `FILE_ID_INFO` identity
   (volume serial plus 128-bit file ID). Unsupported identity or sharing failure
   fails visibly; never accept a basename or remote path as a substitute.
2. Anchor verification to the connected socket's actual local and peer tuples.
   Require exact IPv4 `127.0.0.1` or IPv6 `::1` loopback endpoints. Query
   `GetExtendedTcpTable` using the matching family and owner-PID connections class.
   Find exactly one established **reversed** tuple: table local is socket peer,
   table remote is socket local. A listener row or Utterleaf's client row is not
   the server process. Include IPv6 address bytes and scope fields.
3. Reject reserved PIDs 0 and 4, then open the matched PID with limited query and synchronize rights, without debug
   privilege. Require a nonsignaled live process handle, record its creation
   time, query its full executable path and inspect its token. Require the same
   user SID and session ID as Utterleaf. Compare the reported image path lexically
   against the trusted final DOS path first; never resolve or open the reported
   path. Reject remote, device, alternate-stream and different paths. Only after
   that comparison, reopen the retained known-local expected path and require
   both final path and file identity to match the retained expected executable.
4. Re-query the exact TCP tuple and require the same sole PID and a still-live
   retained process handle. Revalidate before Identify. Retaining and checking
   the original process handle distinguishes an exited process from reuse of its
   numeric PID. A later loss of identity invalidates the connection and never
   reconnects or rearms automatically.
5. Close candidate file/token handles promptly. Retain the expected-file and
   process leases through authentication/session, and close every owned handle
   exactly once on success, cancellation and failure. Python sockets keep their
   own socket cleanup; do not pass sockets to `CloseHandle`.

Native bindings need explicit ctypes argument/result types and last-error use.
Define native row/table structures rather than assuming packed offsets. Microsoft
documents possible table alignment padding; use the table field offset and row
size. Decode network-order port/address fields correctly. Bound two-call buffer
growth to three attempts and 16 MiB, validate row count against returned bytes,
and bound missing-row polling with cancellation and a shared short deadline.
Do not log other connections, token buffers, paths, PIDs or native error payloads.

Primary references:

- [GetExtendedTcpTable](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable),
  [IPv4 owner row](https://learn.microsoft.com/en-us/windows/win32/api/tcpmib/ns-tcpmib-mib_tcprow_owner_pid),
  [IPv6 owner row](https://learn.microsoft.com/en-us/windows/win32/api/tcpmib/ns-tcpmib-mib_tcp6row_owner_pid).
- [OpenProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess),
  [QueryFullProcessImageNameW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-queryfullprocessimagenamew),
  [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes).
- [GetTokenInformation](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation),
  [FILE_ID_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info),
  [final file path](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew).

## Acceptance and verification

Unit fixtures must cover alignment, byte order, buffer growth/count bounds,
missing/ambiguous/client-only/listener-only rows, process exit and PID changes,
wrong user/session/file/path, unsupported file identity, access failure,
cancellation and exact handle ownership. Results are recorded below separately
from the wider native OBS acceptance gate.

A harmless native Python child can bind an ephemeral loopback socket, accept one
connection, wait within its own deadline and exit naturally. Use the current
base Python executable (`sys._base_executable`, since a Windows virtual-environment
launcher can redirect to another image) as the expected file for this fixture. Verification must return
the child's PID, not the parent's, with matching file identity/SID and a nonzero
creation time. A different existing executable as the expected identity must
fail without launching that executable. Exercise IPv6 only where binding is
available and record the result separately. No OBS instance, consumer credential,
microphone, streaming service or recording configuration is needed.

Run focused identity and OBS control/transport tests, then privacy/boundary checks
and full desktop regression for the integrated authentication boundary. Obtain
independent review of native bindings, races, failure cleanup and claims before
exposing the connection in the app. Native OBS and the authenticated audio bridge
remain separate gates.

### September 12 acceptance result

The final identity suite passes **37 tests**. Native fixtures ran on Windows 11
build 26200 with Python 3.14.6 and 64-bit pointers. Both IPv4 and IPv6 child-server
attribution passed, including nonzero process creation time and revalidation;
the wrong existing executable was refused without launching it. Child readiness
and lifetime are bounded, startup failure fails the test, and IPv6 skips only
after an explicit probe reports unavailable binding. Native control integration
also completed a harmless authenticated WebSocket exchange and proved that a
wrong expected executable receives zero HTTP bytes before rejection.

Independent review covered ctypes ABI, table/token returned-byte bounds and SID
pointer bounds, process lifetime, file/path races, cancellation and lease cleanup.
Findings corrected before acceptance included unsafe token ranges, TCP row counts
checked against capacity instead of returned length, filesystem access before
reported-path rejection, reserved-PID handling and missing checks between native
query stages. Regression tests cover the 16 MiB cap before allocation and exactly
three buffer-growth attempts. The final separate reviewer run passed all **167
identity/control/transport tests** and found no remaining component blocker.

Root verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_windows_peer_identity.py tests/test_obs_control.py tests/test_obs_websocket.py tests/test_obs_protocol.py tests/test_obs_session.py tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py tests/test_packaging_media.py
.\.venv\Scripts\python.exe -m pytest
```

The combined run passed **313 tests in 2.23 seconds**. Full desktop regression
passed **1,360 tests, 13 skipped in 38.68 seconds**. These checks use synthetic
local peers; they do not establish actual OBS interoperability, per-poll overhead
under streaming load, macOS/Linux support, native audio authentication or a
packaged release. No consumer OBS process, credentials or audio was used.

## Constraints, limits and stop

The subsequent [audio-pipe increment](windows-obs-audio-pipe.md) extends this
module with an independently owned process lease. It revalidates TCP before
duplicating the existing process handle without inheritance; the duplicate's
later pipe checks require exact PID/liveness/user/session without depending on
TCP. Native tests prove it survives TCP closure and refuses original-process
exit. The identity suite now has 47 passing tests; the historical 37-test receipt
above remains the original authentication-gate acceptance.

This is OS-backed process attribution, not cryptographic attestation. Table
snapshots and an owning PID do not defeat process injection, duplicated/shared
sockets, administrator interference or a user modifying the trusted executable
before it is opened. `QueryFullProcessImageNameW` returns a path, not a handle to
the image file originally mapped in the process. Comparing the currently opened
path target cannot prove its historical loaded bytes if that path was replaced
after process launch. Claims and tests must describe a stable TCP-owning process,
expected full image path and current file identity; exact loaded-image attestation
is not established by these APIs. A password remains required. Missing or ambiguous attribution
fails closed; no privilege escalation or alternate endpoint is attempted.

The reported image path must match the retained expected DOS path after Windows
case, separator and dot-component normalization; parent traversal is rejected.
Short-name or other filesystem aliases are not guessed into compatibility.
Initial user-selected path validation uses
the existing local-filesystem checks before and after resolution; it does not
guarantee that every filesystem metadata operation is interruptible or avoids
remote work through all possible filesystem redirections. The untrusted peer's
reported path is never accessed through the filesystem.

Preserve all existing work and desktop/Android separation. Do not launch OBS,
read saved credentials, install dependencies, capture audio, mutate preferences
or delete user artifacts for this task. Stop this increment after native synthetic
positive/negative evidence, integration regressions, matching documentation and
independent review pass; then continue the native audio pipe/plugin and live UI.
