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
and live OBS acceptance. None of the server, post-load vendor registration,
stream-following, PCM, controller, Arm, or real OBS application behavior is
implemented or proven by this prerequisite.

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
