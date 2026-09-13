# Utterleaf OBS native bridge development

This directory contains the original, C-only development module and tools that
write build receipts into a separate output directory. The current increment
proves the native build prerequisite and adds linked pairing, plugin-state,
frontend Tools and vendor-dispatch components. It defines an exclusive
per-user owner, bounded admission worker, pairing TaskDialog and strict
`IssueAuthorization`/`PrepareSession` vendor requests. The x64 DLL builds from
pinned public resources. The headless `libobs` fixture verifies that it refuses
initialization before opening pairing state. Actual frontend load, UI interaction
and real OBS acceptance remain unverified.

The full goal remains an authenticated OBS audio bridge: a restrictive native
server, process and pipe identity checks, explicit idle-to-arm control, actual
primary streaming-mix and selected-bus PCM delivery, bounded conversion and
storage, cancellation and gap handling, visible control, local recognition,
and live OBS acceptance. Separate native Hello/ACK and retained-process pipe
admission components now have an explicit test build, described below, and the
bounded admission worker is linked into the module. Frontend/device behavior
and real OBS acceptance remain unverified. The separate
[Arm increment](../../docs/plans/active/obs-session-arm.md) now implements fixed
authenticated-pipe commands, bounded exact I/O and native/desktop Arm state in
reviewed development source. Its 199 desktop tests, 34 native build/test commands,
linked build and headless smoke pass. Startup remains busy until a real STOPPED
event: a synchronous OBS failure lacking that event can require a later completed
stream lifecycle or OBS restart before fresh Arm. PCM, the visible capture
controller, live recognition and actual frontend acceptance remain open.

## Inputs and legal boundary

`dependencies.json` pins the exact OBS source revision
`ba2f32bdf791005443988a4955e963663e16b1ed` for 40 public resources, including the
frontend header, configuration template and license. The obs-websocket API header
is pinned separately at `1ef34bf48110c2a18184e50e41cd0b1a855e2147`, for 41 total
resources. The build verifies every
resource's URL, byte count and SHA-256 before compiling. It generates
`obsconfig.h`, derives local import libraries from installed `obs.dll` and
`obs-frontend-api.dll`, embeds the common-controls activation manifest, and
emits source/input/generated-file receipts. The nine ISC header notices in
`OBS-HEADER-NOTICES.txt` and the obs-websocket notice reproduce each header's
complete leading comment.

The build uses an existing LLVM-MinGW installation and the installed OBS
32.2.2 runtime. The earlier inert prerequisite produced byte-identical repeated
builds; that result does not establish reproducibility of this linked increment.
This is not a hermetic toolchain: compiler driver configuration, linker behavior, headers
outside the locked closure and static-runtime inputs are not fully pinned.
MinGW/static-runtime redistribution licensing remains open. The original plugin
source is GPL-2.0-or-later and is kept separate from the Apache desktop client;
no plugin binary is published or installed. No OBS implementation source or
plugin template is copied.

## PowerShell build and smoke check

Run from the repository worktree. The example supplies every path explicitly and
does not download anything unless `--fetch` is added deliberately.

```powershell
$py = "C:\Users\unknown\Projects\Mindict\.venv\Scripts\python.exe"
$toolchain = "C:\Users\unknown\.local\llvm-mingw-20260616-ucrt-x86_64"
$obsBin = "C:\Program Files\obs-studio\bin\64bit"
$headers = "C:\Users\unknown\Projects\Mindict\.grok\obs-native-build\headers"
$output = "C:\Users\unknown\Projects\Mindict\.grok\obs-native-build\review-a"
& $py native/obs-plugin/tools/build.py --toolchain $toolchain --obs-bin $obsBin --headers $headers --output $output
& $py native/obs-plugin/tools/smoke.py --build $output
```

The smoke fixture uses a separate build-local OBS configuration. It verifies a
null frontend handle, successful `obs_open_module`, refusal by `obs_init_module`,
and returned shutdown. It compares only metadata of the three fixed pairing-store
nodes before and after; it never reads their contents or creates those paths.
It does not start the OBS application, create sources, reset audio, or access a
microphone, stream, recording, credentials, or consumer OBS profile. Its raw OBS
log can contain machine and security information; keep it local and do not
publish it.

The linked September 13 build at `.grok/obs-enrollment-flow/build-a` has DLL SHA-256
`b029401c1f5da71bf3c27c7dce084aa9c183d8ce8366f2ad1907c1447fe871cf`.
Its smoke receipt records OBS API version `537001986`, `obs_open_module=0`,
`obs_init_module=false`, returned shutdown and unchanged fixed-store metadata.
This checks headless refusal, not actual OBS frontend/vendor registration.
The [build plan](../../docs/plans/active/obs-plugin-build.md) retains the separate
historical inert prerequisite evidence and remaining release gates.

## Native admission tests

`src/handshake.c` and `src/admission.c` implement a separate Windows Hello/ACK
and once-only pipe-admission component. An authenticated caller must first
authorize the expected PID; the component retains its process object and
checks the actual kernel pipe-client PID, liveness, creation time and user/logon
identity before reading a Hello. The explicit DACL allows the current logon,
and failure or cancellation consumes the pending session.

The linked obs-websocket vendor API does not expose its caller's WebSocket connection.
An expected PID from vendor JSON is a credential holder's assertion, not reverse
connection attribution or trusted Utterleaf executable enrollment. That
integration must be resolved before exposing arming. The module's vendor
callbacks enforce strict fixed requests and hand off only to bounded
owner/admission state; they do not provide caller attribution.

Run from the owning repository root with an existing Windows LLVM-MinGW toolchain:

```powershell
$build = $output
$testOutput = "C:\Users\unknown\Projects\Mindict\.grok\obs-enrollment-flow\native-final"
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --output $testOutput --build $build --headers $headers
```

The driver performs fixed-vector and injected CNG-failure checks, actual token/
pipe-security checks and 11 disposable child-process transport tests. It also
builds the independent capability authorizer, runs six state/fault groups and
10 authorization-to-admission child-process tests, and checks the shared CNG
helper against an independently computed .NET/Python vector. It runs
without the OBS application or audio, scopes Python imports to this checkout
and records local source/tool/compiler/output hashes. Every translation unit uses warnings as
errors; the test-only macro-renamed heap shim link has three local-import
warnings. The [native session plan](../../docs/plans/active/obs-native-session.md)
records commands, results and remaining kernel-failure, cross-user/logon,
vendor/arming and live-audio acceptance gates. Do not distribute the test DLL.

The [enrollment contract](../../docs/plans/active/obs-native-enrollment.md) defines
the 60-byte challenge, 15-second lifetime, one proof attempt, private capability
ownership and revocation. These components receive an already-provisioned test
capability. The separate `pairing_store.c` now implements CurrentUser DPAPI
native persistence, explicit replacement/forget and non-replacing transfer-file
export. The desktop client imports into its own role-specific private store.
The driver adds the native store state/fault checks and a cross-language fixture
that exports from native code, imports/reloads in Python and produces a native
admission proof using the loaded key. All storage fixtures use disposable roots;
they do not touch a consumer pairing, OBS profile or audio source.

The store component is separate from the linked pairing Tools dialog and vendor
adapter. The caller still must complete frontend/device acceptance, durable live
revocation, atomic Arm and audio integration. Neither successful storage nor the
proof establishes executable identity or Arm authority. The test DLLs
remain local verification artifacts and are never installed into OBS.

The current driver also checks the runtime's pin/start/close state with controlled
substitutions and real Windows threads, including close overlapping dispatch,
precommit replacement failure and worker cancellation. Actual child processes
compete for the private store owner. With `--build` and `--headers`, it verifies
the recorded build/header inputs, runs a shimmed bridge registration/teardown
fixture and six parser cases through real libobs data APIs (without libobs startup).
The linked checkpoint's 28 compilation/test commands pass in
`native-final/test-receipt.json`.
Omitting both optional arguments leaves those two frontend-boundary fixtures
explicitly unrun; it does not establish their acceptance.

Add `--ui` on a Windows desktop to also run the isolated native TaskDialog
fixture. The setup follow-up passes all 29 top-level driver commands at
`.grok/obs-enrollment-flow/setup-native-final/test-receipt.json`; the UI command
contains its own five compile/link/run commands and nested receipt. Its real
common-controls manifest activation, modal owner, command links, Escape
cancellation with zero mutations, duplicate-open guard and cleanup pass for
unpaired, paired and storage-error states. The three window captures contain
only the fixture. Pass-through observation wrappers call the actual Windows
TaskDialog function; no OBS or store implementation is linked into that fixture.
This verifies native dialog behavior in isolation, not real OBS frontend load,
file-picker import/export interaction, physical input or accessibility support.
