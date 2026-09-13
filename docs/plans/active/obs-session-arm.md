# Explicit OBS session arming

September 13, 2026. Continue on `feat/obs-session-arm`, stacked on reviewed
pairing setup `e71b627` in draft PR #36. That exact setup source passed all five
desktop jobs in [CI 34760760046](https://github.com/RioPlay/utterleaf/actions/runs/34760760046).
This plan implements the next part of the full [live audio contract](obs-audio-design.md).
The published previews remain unchanged.

## Goal and area

After explicit enrollment and pipe authentication, require a separate one-use
Arm transaction. Admit it only while OBS is idle. Only a later ordered frontend
STARTING then STARTED may authorize that session's future audio delivery. Keep
the authenticated connection alive while armed, detect client departure, and
retire it on disarm, stop, cancellation, revocation or exit. Connecting or finding
an existing stream must never grant capture consent.

Area: native authenticated I/O, bounded session command codec, plugin worker and
frontend state coordination; desktop `ObsAudioPipe` explicit Arm operation;
focused native/desktop interop and race tests. The connection controller and PCM
callback/recognition remain required follow-ups, not replacements for this scope.

## Constraints

- Keep enrollment proof and Hello/ACK unchanged. Arm travels only inside the
  already authenticated duplex pipe, never vendor JSON. Keep the prepared session
  ID and requested additional mix mask until worker teardown.
- Keep unauthenticated and authenticated-but-unarmed deadlines bounded at 15
  seconds each. Armed waiting has no arbitrary recording-duration countdown.
  Retain one joined worker, one request slot and bounded wire/I/O buffers.
- Use the existing retained process/pipe identity and cancellation/drain logic
  before and after native I/O. Never allocate from untrusted wire lengths.
- Serialize Arm's OBS idle observation with frontend state transitions. Do not
  block the frontend on a worker that needs frontend work. Queued callbacks must
  survive late invocation after EXIT without touching retired heap state or OBS.
- Success acknowledges a committed Arm, not successful capture. Lost replies and
  errors are terminal; no automatic retry/reconnect/rearm. Session IDs are routing
  metadata and do not independently authenticate anything.
- No OBS installation, consumer profile or microphone changes during fixtures.
  Original native GPL source remains separate from Apache desktop code and Android.

## Acceptance and verification

The fixed Arm record is 28 bytes, `<4sBBH16sBBH`: `ULAC`, version 1, kind
1=request or 2=reply, zero header reserved, the prepared 16-byte session ID,
prepared additional mix mask (0–63), status, zero trailing reserved. Request
status is 0; reply status is 1=committed or 2=refused. Only the exact prepared
session/mask may be used. A reply precedes any future ULAP frame on that pipe.
An unrecognized or malformed command terminates the attempt.

- Native exact I/O: authenticated roundtrip, fragmentation, wrong/preauth peer,
  timeout, cancellation, EOF and failed-read wiping using actual child processes.
- Command framing: exact lengths, magic/version/kind/session/mask/reserved/status
  checks; malformed, duplicate and replayed commands terminate.
- Consent ordering: refuse already-active/starting streams; STARTING before Arm
  commit refuses, Arm before STARTING then STARTED authorizes only once; no Start
  or PCM before that transition. Failed OBS start must not manufacture STARTED.
- Lifetime: client close, pending UI task, stop, replacement, forget and EXIT
  races cancel/drain/join; late callbacks cannot access OBS or freed runtime.
- Desktop Arm sends once, checks its bound reply, preserves coalesced future PCM,
  and closes on error/cancel; concurrent close must unblock it.
- Run focused native fixture drivers and affected Python OBS/pipe tests, then
  native integration build/test checks and independent source/evidence review.
  Record exact commands and results here as implemented. Fixture results do not
  establish real OBS frontend/audio load or physical-device usability.

## Non-goals and stop

Do not add an alternate recorder, change OBS routing, silently attach to existing
streams, publish a plugin, or treat this as completed live transcription. Stop
editing the Arm increment when its observable checks and independent review pass;
continue the actual mix callback, controller, live recognition and acceptance
gates required by the desktop roadmap.

## OBS lifecycle boundary

The pinned OBS 32.2.2
[streaming frontend](https://raw.githubusercontent.com/obsproject/obs-studio/ba2f32bdf791005443988a4955e963663e16b1ed/frontend/widgets/OBSBasic_Streaming.cpp)
emits STARTING before calling the output start operation and STARTED later. Its
synchronous start-error path emits a private Qt stopped signal without necessarily
a public frontend STOPPED event. Once STARTING is observed, the bridge keeps its
frontend busy guard set through STARTED and STOPPING, and clears it only on
STOPPED. The Arm check also requires both current activity queries to be false.

`obs_output_active()` covers active/reconnecting outputs, so false alone does
not rule out an asynchronous connection attempt. The pinned
[libobs output implementation](https://raw.githubusercontent.com/obsproject/obs-studio/ba2f32bdf791005443988a4955e963663e16b1ed/libobs/obs-output.c)
does not provide a public completion event for a synchronously rejected start.
A later queued UI callback is not proof that the start call has returned: nested
frontend event processing can run queued work early. An absent signal or elapsed
grace period therefore cannot safely establish idle. A 30-second deadline
for STARTING to reach STARTED terminally disarms an orphaned/slow startup; it
does not establish that OBS became idle. Waiting while armed and recording after
STARTED have no duration cutoff.

Known limit: after a failed start that omits STOPPED, a fresh Arm remains refused
until OBS emits STOPPED in a later actual lifecycle or OBS restarts. Utterleaf
does not initiate that lifecycle or change stream settings. Clear user-facing
explanation and real OBS failure/recovery acceptance remain requirements for the
pending desktop controller. These component fixtures do not establish that
experience. If EXIT is missed, unload closes native gates without calling OBS.

## Component verification

The final native driver passes **34 build/test commands**, including actual
child-process exact I/O, injected API failures, fixed commands, Windows runtime
thread/event ordering, queued frontend lifecycle and real-libobs vendor dispatch.
Exact-I/O cases cover fragmentation, bounds, partial-read wiping, EOF, typed
cancellation and blocked-write draining. Injected event-creation, zero/over-count
transfer and failed probe cases cannot report success; cancellation or deadline
expiry during the final peer check wipes the read and wins over success.

The runtime fixture covers late generations, accepted/refused Arm, STARTING before
the queued callback, startup expiry, late STARTED, and cancellation through
revocation/close. Bridge fixtures refuse startup/started/stopping states even
when activity flags are false, and prove stale/duplicate/closed UI tasks cannot
touch retired state. The explicit desktop Arm and affected
protocol/session/pipe/privacy/boundary bundle passes **199 tests in 5.50 seconds**,
with no skips. Separate source review cleared the final codec/runtime and
conservative bridge gate; root reviewed the delegated I/O and desktop changes.

The linked x64 DLL builds against the pinned headers and installed OBS runtime.
Headless smoke opens it, refuses initialization before any pairing-store startup,
returns from shutdown, and leaves fixed-store metadata unchanged. The DLL SHA-256
is `9ce5f225fef16af2ccdcdbf5e30ea637df5a306863e0285d8329e33f1e7925a3`.
Three existing linker warnings remain confined to the test heap shim. The native
dialog fixture was not repeated for this increment; its earlier setup evidence
remains separate. No OBS application, source or audio device ran in these checks.
Exact-source CI for this Arm checkpoint remains pending.

From the owning worktree, the desktop command was:

```powershell
$env:PYTHONPATH = (Get-Location).Path
& "C:\Users\unknown\Projects\Mindict\.venv\Scripts\python.exe" -m pytest tests/test_obs_audio_pipe.py tests/test_obs_audio_arm.py tests/test_obs_session.py tests/test_obs_protocol.py tests/test_windows_pipe.py tests/test_privacy.py tests/test_repo_boundaries.py -o addopts='' -q
```

Local native evidence is under `.grok/obs-session-arm/`; the separate exact-I/O
development receipts under `.grok/obs-enrollment-flow/` are historical. The
authoritative final receipts are `build/build-receipt.json`,
`build/smoke-receipt.json`, and `verification/test-receipt.json` under that Arm
directory. Commands from the owning worktree:

```powershell
$py = "C:\Users\unknown\Projects\Mindict\.venv\Scripts\python.exe"
$toolchain = "C:\Users\unknown\.local\llvm-mingw-20260616-ucrt-x86_64"
$obsBin = "C:\Program Files\obs-studio\bin\64bit"
$headers = "C:\Users\unknown\Projects\Mindict\.grok\obs-native-build\headers"
$build = "C:\Users\unknown\Projects\Mindict\.grok\obs-session-arm\build"
$verification = "C:\Users\unknown\Projects\Mindict\.grok\obs-session-arm\verification"
& $py native/obs-plugin/tools/build.py --toolchain $toolchain --obs-bin $obsBin --headers $headers --output $build
& $py native/obs-plugin/tools/smoke.py --build $build
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --output $verification --build $build --headers $headers
```

Continue the visible controller and actual PCM path. Future Start/PCM writes must
remain serialized after the complete successful Arm reply, even if native state
already reached STARTING/STARTED while that reply was in flight. This increment
emits no frames. Real frontend recovery, audio load, redistribution/toolchain
review and release acceptance remain open.
