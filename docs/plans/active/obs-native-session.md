# Native OBS session admission and arming

## Goal and area

Continue the original bridge after its reviewed build/load prerequisite, merged
through PR #32 at `e61c7dd`. Implement the native server boundary required for
actual primary stream-mix and optional separate-bus capture. This plan does not
replace the full [OBS design](obs-audio-design.md) or its live acceptance gates.

The first components live under `native/obs-plugin/src/` and its separate native
tests/tools: a fixed Hello/ACK implementation, retained client-process admission,
an explicit logon-restricted pipe, bounded cancellable native operations and
once-only pending-session ownership. Follow with vendor registration, atomic
idle-to-arm/start coordination, then the actual PCM callback/worker integration.
Root owns integration; delegated native components have one writer and a
separate reviewer. No native endpoint is exposed at module load.

## Authority and constraints

The public obs-websocket API v3 vendor callback supplies request/response data
and plugin state; it does not expose the originating WebSocket connection. An
expected PID in authenticated vendor JSON is a credential holder's assertion.
Open and retain that process immediately, then validate the actual named-pipe
client against the retained process, its user SID and logon authentication ID
before the first read. This proves the pipe-client boundary, not reverse
WebSocket process attribution. Do not infer attribution from timing or a TCP
table snapshot.

A same-user process holding the OBS password can authorize its own PID under
this boundary. Trusted Utterleaf executable identity requires independently
provisioned enrollment; a path from vendor JSON is not trusted enrollment. The
vendor/enrollment integration must state and test its actual authority before
it exposes arming. No pipe secret goes in vendor JSON, ordinary logs or backup.

Use one pipe instance, an explicit current-logon DACL, remote-client rejection,
noninherited handles and overlapped I/O. Check native completion before releasing
pending buffers even when cancellation fails; do not promise hard kernel-time
bounds. Retain the original process object to prevent PID reuse from replacing
the authorized peer. Failure/cancellation consumes a pending session. Native
callbacks must not perform pipe I/O, recognition or storage work.

The installed OBS application, consumer profiles, routing, recording settings,
microphone and source runtime remain untouched. The module remains separately
GPL-2.0-or-later; toolchain/static-runtime redistribution review stays open.

## Acceptance and verification

- Independent fixed Hello/ACK vector matches the Python client; malformed
  metadata/length/session, CNG failures and owned secret cleanup are checked.
- Native expected-process A/client A can authenticate; expected A/client B is
  rejected before reading a Hello byte. Process exit/reuse, wrong user/logon,
  second pipe instance, cancellation and timeout fail closed without leaks.
- An isolated fixture validates native pipe admission without OBS or audio.
  These checks cannot establish authenticated vendor dispatch or arming.
- Vendor tests later prove that unauthenticated dispatch cannot create state,
  and that stop/disarm/unload race safely with preparation and streaming start.
- Native OBS tests then prove the actual encoder mix, selected buses, bounded
  callbacks, non-interference and visible incomplete recovery under backpressure.

Use the existing LLVM-MinGW compiler with `-std=c11 -Wall -Wextra -Werror` for
native tests, the pinned native build tool for the plugin, and the desktop
Python environment scoped to this worktree for cross-language transport checks.
Record exact commands/results as each component is implemented; obtain separate
source/evidence review. No plugin binary publication follows from these tests.

### Native primitive evidence

The fixed Hello/ACK vector passes against the Windows CNG implementation and
the Python client. Ten injected CNG/heap failure points check acquisition/release
counts, failure ACK erasure and nonzero object-memory erasure before free. ACK
must be writable and disjoint from inputs; the two input ranges may overlap.

The explicit test driver builds these components independently of OBS:

```powershell
$py = "C:\Users\unknown\Projects\Mindict\.venv\Scripts\python.exe"
$toolchain = "C:\Users\unknown\.local\llvm-mingw-20260616-ucrt-x86_64"
$output = "C:\Users\unknown\Projects\Mindict\.grok\obs-native-session\check-b"
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --output $output
```

The September 13 run passes all **11** Python-to-native child-process tests:
exact ACK/single consumption; wrong and exited process rejection; cancellation
before connection, after a partial Hello and after success; connection and read
timeouts; invalid timeout consumption; malformed Hello; duplicate instance.
Windows virtual-environment Python may launch another interpreter process, so
the fixture launches the base interpreter directly to retain the actual pipe
client PID. The production process check has no parent/child exception.

The native identity fixture verifies actual same-logon process tokens, the
pending pipe's single logon-SID allow ACE and read/write permissions, three
noninherited handles, reserved/dead-process rejection and balanced handle counts
over **64** create/destroy cycles. Independent user/logon/session/authentication
ID mutations are unit checks; they do not establish real cross-user/logon,
remote-client or forced PID-reuse acceptance. Injected kernel completion failure
and broader resource-failure coverage also remain follow-up gates.

All C translation units compile with `-Wall -Wextra -Werror`. The test-only
macro-renamed heap shim link emits three local-import warnings; the normal
native build does not. The driver applies a 60-second outer timeout per command,
scopes Python imports to the owning checkout, checks source stability and writes
source/compiler/artifact/log hashes into a local receipt. This records the local
toolchain without making it hermetic. No OBS app, audio or microphone is used.

The scoped desktop regression command also passes **54** tests:

```powershell
$env:PYTHONPATH = (Get-Location).Path
& $py -m pytest tests/test_repo_boundaries.py tests/test_windows_pipe.py tests/test_obs_audio_pipe.py -q
```

## Status and stop

In progress on `feat/obs-native-session`. Independent source, test-driver and
saved-evidence review is clear for the bounded handshake/admission components.
Cancellation now prevents new pipe borrowing, while previously borrowed handles
still require caller-owned workers to stop and join before destruction.
Vendor/enrollment/arming and PCM are not implemented or verified. Stop editing
each component after its stated checks and review pass, then continue the
remaining full OBS workflow. Do not mark live capture or the application complete
based on handshake or synthetic pipe evidence.

Primary references: [pinned vendor API](https://github.com/obsproject/obs-websocket/blob/1ef34bf48110c2a18184e50e41cd0b1a855e2147/lib/obs-websocket-api.h),
[pipe creation](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew),
[kernel pipe-client PID](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid).
