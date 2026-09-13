# Utterleaf OBS native bridge prerequisite

This directory contains the original, C-only development module and tools that
write build receipts into a separate output directory. The current increment
proves a narrow native prerequisite: an x64 DLL
can be compiled from the pinned OBS 32.2.2 public-header closure, its exports
and imports can be inspected, and the inert module can be opened, initialized,
unloaded and shut down through `libobs`.

The full goal remains an authenticated OBS audio bridge: a restrictive native
server, process and pipe identity checks, explicit idle-to-arm control, actual
primary streaming-mix and selected-bus PCM delivery, bounded conversion and
storage, cancellation and gap handling, visible control, local recognition,
and live OBS acceptance. Separate native Hello/ACK and retained-process pipe
admission components now have an explicit test build, described below. They are
not linked into the inert module: post-load vendor registration, stream-following,
PCM, controller, Arm and real OBS application behavior remain unimplemented.

## Inputs and legal boundary

`dependencies.json` pins the exact OBS source revision
`ba2f32bdf791005443988a4955e963663e16b1ed` and 39 resources: 37 used public
headers plus `libobs/obsconfig.h.in` and `COPYING`. The build verifies every
resource's URL, byte count and SHA-256 before compiling. It generates
`obsconfig.h`, derives a local import library from the installed `obs.dll`, and
emits source/input/generated-file receipts. The nine ISC header notices in
`OBS-HEADER-NOTICES.txt` reproduce each header's complete leading comment.

The build uses an existing LLVM-MinGW installation and the installed OBS
32.2.2 runtime. Repeated builds with the same installed inputs currently give
byte-identical DLLs, but this is not a hermetic toolchain or toolchain
reproducibility claim: compiler driver configuration, linker behavior, headers
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

The smoke fixture uses a separate build-local OBS configuration, does not start
the OBS application, creates no sources, resets no audio, and does not touch a
microphone, stream, recording, credentials, or consumer profile. Its raw OBS
log can contain machine and security information; keep it local and do not
publish it.

The verified review run used `review-a` and `review-b`. Both DLLs had SHA-256
`f3322eabd7a7dd1f7a3439670d08db89e54155c8e35e8013bae973842bdced84`.
The smoke receipt recorded OBS API version `537001986`, `obs_open_module=0`,
successful initialization and returned shutdown. The local libobs log also
records the module's unload callback. Scratch copies with a flipped
cached header byte and a changed plugin were rejected before compilation or
native load, respectively.

## Native admission tests

`src/handshake.c` and `src/admission.c` implement a separate Windows Hello/ACK
and once-only pipe-admission component. An authenticated caller must first
authorize the expected PID; the component retains its process object and
checks the actual kernel pipe-client PID, liveness, creation time and user/logon
identity before reading a Hello. The explicit DACL allows the current logon,
and failure or cancellation consumes the pending session.

The obs-websocket vendor API does not expose its caller's WebSocket connection.
An expected PID from vendor JSON is a credential holder's assertion, not reverse
connection attribution or trusted Utterleaf executable enrollment. That
integration must be resolved before exposing arming. These primitives are not
linked into the current module or started by loading it.

Run from the owning repository root with an existing Windows LLVM-MinGW toolchain:

```powershell
$output = "C:\Users\unknown\Projects\Mindict\.grok\obs-native-session\check-b"
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --output $output
```

The driver performs fixed-vector and injected CNG-failure checks, actual token/
pipe-security checks and 11 disposable child-process transport tests. It also
builds the independent capability authorizer, runs six state/fault groups and
10 authorization-to-admission child-process tests, and checks the shared CNG
helper against an independently computed .NET/Python vector. It runs
without OBS or audio, scopes Python imports to this checkout and records local
source/tool/compiler/output hashes. Every translation unit uses warnings as
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

The store component is not a pairing UI or vendor adapter. Its caller must still
serialize live authorizer ownership and implement visible pairing/revocation,
vendor handling, atomic Arm and audio integration. Neither successful storage
nor the proof establishes executable identity or Arm authority. The test DLLs
remain local verification artifacts and are never installed into OBS.
