# Original OBS plugin build and native acceptance

Status: native prerequisite build/load verified; full bridge not implemented.
September 13, 2026. Follows the
[Windows audio pipe](windows-obs-audio-pipe.md) and [OBS design](obs-audio-design.md).

## Goal and area

Build the original C-only Windows OBS bridge against the installed 32.2.2 public
C interfaces, with explicit exports, pinned resources and a reproducible build.
Prove loading and harmless lifecycle callbacks in a separately configured
synthetic OBS test environment before connecting live PCM. Keep plugin source,
GPL licensing/notices and release output separate from the Apache desktop client
and Android. Do not copy template or other plugin implementation code.

## Initial inventory and build approach

The following inventory preceded the build/load work recorded below.

The installed `obs.dll` and `obs-frontend-api.dll` are AMD64 PE/COFF and export the
needed libobs/frontend functions with undecorated C names. They include the actual
encoder/mixer and audio callback interfaces identified in the
[implementation evidence](obs-audio-implementation.md). Matching OBS headers and
import libraries are absent. The release publishes source/runtime/installer/PDB
assets, but no Windows development archive was found in its asset inventory.

No Visual Studio instance, MSVC or Microsoft Windows SDK was found. Existing
Android CMake/NDK tools do not provide those Windows dependencies. A second,
targeted inventory did find an installed Windows-targeting LLVM-MinGW toolchain
at `C:/Users/unknown/.local/llvm-mingw-20260616-ucrt-x86_64/bin`, including
`x86_64-w64-mingw32-clang.exe`, `gendef.exe`, `llvm-dlltool.exe`, `ld.lld.exe` and
`windres.exe`. Clang identifies its target as `x86_64-w64-windows-gnu`. Workspace
drive C: had 63.31 GiB free at that inventory; recheck before resource acquisition.

No C ABI blocker was identified for a narrow plugin with this existing compiler.
This project-owned build lane is not an upstream-supported toolchain. The initial
inventory alone did not verify native compatibility. The official template uses Visual Studio; its current
requirements/OBS pin differ from the 32.2.2 source presets. Do not treat a template
toolchain requirement as proof that an independently built C-only DLL is impossible.

1. Acquire only the exact official OBS 32.2.2 public-header closure, generated
   configuration inputs and full licenses/notices needed for the original bridge.
   Record source revision/archive SHA-256, each copied resource and provenance.
   Public API headers are dependencies; do not import OBS implementation files.
2. Generate `obsconfig.h` from the pinned `libobs/obsconfig.h.in` with explicit
   reviewed values; the source `obs-config.h` fixes the API version at 32.2.2.
3. Record the installed DLL versions/hashes and derive local COFF import libraries
   from their exports. Treat these as reproducible development artifacts, with
   output isolated from user installation and consumer release folders.
4. Compile/link an original x64 C DLL using an explicit `.def` for the required
   OBS module entry points. Inspect exports/imports and dependency provenance.
   Avoid Qt/C++ dependencies unless later requirements make them necessary.
5. Validate module load, API version, post-load vendor registration and unload
   with a synthetic isolated OBS profile/runtime. No real credentials, consumer
   profiles, microphone, stream service or recording/routing settings are needed.

## Verified native prerequisite (September 13, 2026)

The original inert module now builds with the existing LLVM-MinGW installation
at `C:/Users/unknown/.local/llvm-mingw-20260616-ucrt-x86_64`, installed OBS
`C:/Program Files/obs-studio/bin/64bit`, and the locked cache at
`C:/Users/unknown/Projects/Mindict/.grok/obs-native-build/headers`. Two clean
outputs (`review-a` and `review-b`) produced the same DLL SHA-256:
`f3322eabd7a7dd1f7a3439670d08db89e54155c8e35e8013bae973842bdced84`.

The build receipt locks all 39 resources (37 headers plus `obsconfig.h.in` and
`COPYING`), records six source hashes and ten generated artifacts, checks the
AMD64 PE/COFF shape, expected module exports, and the reviewed OBS/CRT imports.
The generated notice receipt reproduces the complete leading comments of all
nine listed ISC headers byte-for-byte after line-ending normalization.

The smoke loader was run with a 30-second subprocess timeout. It observed OBS
API version `537001986`, `obs_open_module=0`, inert module load and unload, and
returned from shutdown. The fixture started libobs with a disposable config,
created zero sources and did not start the OBS application or reset audio. Raw
logs remain local because OBS logs machine and security information.

Rejection checks on disposable scratch copies failed closed for a corrupted
cached header (`Pinned input differs: libobs/obs.h`) and a changed plugin
(`The reviewed build input changed: utterleaf-obs-bridge.dll`) before native
load. These checks never modified the installed OBS files or the original cache.

This establishes the native build/load prerequisite only. The installed
toolchain is not fully pinned, so identical outputs do not establish hermetic
or toolchain reproducibility. MinGW/static-runtime redistribution license review
remains open; no binary was published or installed.

The pinned obs-websocket API header is C-compatible and routes vendor calls
through libobs proc handlers; it does not require linking C++ or Qt. Consuming its
static-inline public interface still requires exact provenance/license review.

Primary evidence:

- [OBS 32.2.2 release](https://github.com/obsproject/obs-studio/releases/tag/32.2.2)
- [Public header/install configuration](https://github.com/obsproject/obs-studio/blob/32.2.2/libobs/CMakeLists.txt)
  and [API version](https://github.com/obsproject/obs-studio/blob/32.2.2/libobs/obs-config.h)
- [Pinned WebSocket vendor API](https://github.com/obsproject/obs-websocket/blob/1ef34bf48110c2a18184e50e41cd0b1a855e2147/lib/obs-websocket-api.h)
- [Official template requirements](https://github.com/obsproject/obs-plugintemplate/wiki/Build-System-Requirements)
  and [OBS 32.2.2 presets](https://github.com/obsproject/obs-studio/blob/32.2.2/CMakePresets.json)

## Acceptance, constraints and stop

Exact build commands and fixture settings are implemented in
[native/obs-plugin/README.md](../../../native/obs-plugin/README.md). Acceptance
requires clean compilation from pinned inputs, expected module exports and no
unreviewed runtime dependency, native load/unload evidence, and independent
build/license review. The prerequisite checks above pass; the full feature is
still open.

After the initial build/lifecycle gate, implement the restrictive named-pipe
server, actual control-client/process validation, atomic idle-to-arm state,
cross-channel start coordination and bounded callback/worker PCM delivery. Then
complete primary-mix/separate-bus, surround conversion, cancellation, storage-gap
recovery, load/non-interference, visible UI and local live-recognition acceptance.
Stop each verified component's edits when its checks and review pass; the full
OBS workflow and release gates remain the completion target.

Do not alter the installed OBS app or consumer configuration as a build shortcut,
install a large replacement toolchain before testing the existing viable lane,
resume manual artifact deletion, publish a binary or imply that separate
processes settle the combined distribution's legal requirements. The existing
[distribution review gate](obs-audio-design.md#licensing-and-distribution-gate)
continues to apply before shipping.
