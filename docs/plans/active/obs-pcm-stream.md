# Native OBS streaming audio

September 13, 2026. Continue the full [OBS audio design](obs-audio-design.md)
on `feat/obs-pcm-stream`, based on reviewed Arm source `073bb99` in draft PR #37.
Pairing setup remains in draft PR #36. Published previews are unchanged.

## Goal and area

After explicit authenticated Arm and the subsequent native STARTING/STARTED
sequence, send the actual OBS streaming encoder's mix and explicitly requested
additional buses over the existing pipe. Keep capture memory bounded regardless
of stream duration; preserve ordering, timestamps and explicit loss information.
Stopping, disarming, revocation, identity loss and shutdown end capture and join
all users of borrowed OBS audio before freeing memory.

Area: original native wire encoder, callback queue, OBS audio adapter and plugin
worker/lifecycle integration; focused C and native/Python interop fixtures,
build/test drivers and the desktop roadmap. The visible desktop controller and
local live recognition remain required follow-ups, not alternative completion.

## Constraints

- Keep enrollment, Hello/ACK and explicit Arm unchanged. Complete the Arm reply
  before any Start/Audio/Gap/End bytes; one worker serializes all pipe writes.
- Resolve the primary bus from the actual streaming output's slot-zero audio
  encoder after STARTED. Never assume Track 1 or substitute microphone/desktop
  capture. Additional buses remain OBS mixes, never inferred speakers.
- The audio callback only validates fixed metadata and copies borrowed native
  planes to preallocated bounded storage. No allocation, conversion, file/pipe
  I/O, logging, blocking wait or ownership teardown on the audio thread.
- Convert on the worker to the existing stereo float32 ULAP format. Preserve
  finite amplitudes and OBS timestamps; no silent clamping, rate/layout guesses,
  sequence wrap or unbounded length allocation. Unsupported or changed formats
  must fail visibly through terminal/incomplete state.
- Full queues drop whole blocks with explicit gaps. Disconnect and drain
  callbacks before freeing their state. Respect the documented OBS/runtime
  lifecycle boundary; never require a worker waiting on frontend work to join
  from the frontend thread.
- No stream/recording/routing/profile changes, ambient recording, automatic
  reconnect/rearm, plugin installation or publication. Keep original GPL native
  source separate from Apache desktop code and Android. Use pinned public APIs;
  do not copy OBS implementation.

## Acceptance and verification

- Native Start/Audio/Gap/End encodings match the existing Python decoder byte for
  byte, including exact limits, finite PCM, sentinel terminal sequences and
  malformed-input rejection. Use independent fixed fixtures and cross-language
  decoding, rather than roundtripping through the same native encoder.
- Callback queues stay bounded, return promptly when full, preserve all accepted
  block samples once and in order, and account for dropped blocks and shutdown
  tails. Exercise actual producer/consumer thread races and sequence exhaustion.
- Adapter checks actual output/encoder/bus/format ownership and connects only
  after consent. Test partial attach failure, callback/disconnect races, stop,
  cancel, replace, exit and late callback cleanup without real audio devices.
- Existing authenticated I/O and Arm tests keep passing. The integrated native
  build/test and headless checks must bind final sources; independent review
  reads the contract, diff and actual outputs.
- Real supported OBS frontend/audio, format conversion, long-stream load,
  non-interference and visible recovery acceptance remain explicit gates before
  live support or a plugin release can be claimed.

## Non-goals and stop

Do not expose a half-connected capture control or call synthetic samples proof of
real streaming compatibility. Stop editing each component when its named checks
and independent review pass, then continue native integration and the visible
desktop workflow. The full application goal remains open.

## Current work

The preceding Arm checkpoint `073bb99` passed all five desktop jobs in
[CI 34763204298](https://github.com/RioPlay/utterleaf/actions/runs/34763204298).
The following original native components are now built into the development DLL,
but are not yet called by the session runtime:

- `audio_protocol.c` writes bounded Start/Audio/Gap/End packets. Independent
  literal vectors and decoding by the existing Python receiver pass, including
  binary stdout containing a newline byte on Windows.
- `audio_queue.c` copies up to 1,024 native frames into fixed storage, with one
  producer and one consumer, lock-free publication, whole-block loss accounting
  and explicit final gaps. Storage is at most 96 slots of 32 KiB plus metadata
  per bus; it is allocated once and never grows with stream duration. The adapter
  must choose the time bound, detach callbacks before reading the final gap, and
  join both users before destruction. The thread fixture forces full/drop,
  drain and reused-slot handoffs, then checks ordered samples and gap accounting
  across 4,096 blocks. This is not a measured audio-thread latency guarantee.
- `audio_convert.c` uses the pinned public libobs resampler on the worker to
  convert planar float to stereo at unchanged sample rate. Synthetic per-channel
  impulses pass for all six supported rates and seven known speaker layouts;
  mixed vectors and finite values outside ±1 also pass. Surround follows OBS's
  stereo downmix, including its omission of LFE, rather than retaining separate
  surround channels. Count or timestamp-offset changes fail; caller output stays
  untouched on failure. No real stream compatibility is established.

The canonical driver now includes these fixtures and loads the selected libobs
by absolute path for conversion, with current-directory/PATH lookup excluded.
It retains the desktop virtualenv for NumPy-backed protocol validation. The
public resampler header adds one pinned resource, for 42 total. The original
native source/license boundary and existing toolchain limitations are unchanged.

Root ran the following from the owning worktree with the existing `.venv` Python,
LLVM-MinGW installation and pinned header cache. Output is under
`.grok/obs-pcm-stream/` in the original workspace:

```powershell
& $py native/obs-plugin/tools/build.py --toolchain $toolchain --obs-bin $obsBin --headers $headers --output "$pcm/build"
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --build "$pcm/build" --headers $headers --output "$pcm/verification"
& $py native/obs-plugin/tools/smoke.py --build "$pcm/build"
```

The linked build passes all 21 commands; all 42 top-level native verification
commands pass. The protocol helper includes native-vector and emitter child
invocations. The smoke check opens the module, refuses headless initialization,
returns from shutdown and leaves fixed pairing-store metadata unchanged. The
test-only heap shim retains its three previously documented linker warnings.
No OBS application, audio device, consumer configuration, plugin installation or
release is involved. No desktop source changed, so the full desktop suite was
not repeated for this native-only increment.

Receipts bind component checkpoint `bc6907a`, 42 public resources and generated artifacts:

- Build: `829e9b90f45655e637ddd4e852042084932bd81e9c563089546725cd574da786`.
- Native verification: `8546de4b2c95570e8f359902120eb2c8b79afd992169865b88a70a408f05b6a7`
  (57 native source entries, four desktop inputs, 19 artifacts and 42 logs).
- Headless smoke: `ca8d5c20eeabb2d25980ba376b545bce279c1a1442b16fc84654988b92df0247`.

Independent component, driver/receipt and tightened queue-fixture review is clear.
Actual callback attachment, Start/PCM/End
delivery, teardown integration, the visible controller, local recognition and
all real OBS acceptance remain open. The existing Python session treats the
first Gap as an incomplete capture and preserves only its recoverable prefix;
the codec fixture does not establish continuation through gaps.

### Integration verification

Current source connects capture, conversion and transport to the armed
session runtime. A message-only Windows window schedules generation-checked
frontend work without calling OBS from workers. The callback uses fixed per-bus
queues; worker and frontend references must remain valid independently during
cancel, disconnect and shutdown. Focused adapter review found and corrected a
last-release/retirement race. The combined build and checks below now pass.

The transport stages aligned first blocks before Start, drains accepted blocks
on normal stream stop, and treats gaps, source changes and transport failures as
incomplete. A fixed session-bound End acknowledgment lets the server confirm
that the client decoded the terminal packet before disconnecting, without a
blocking pipe flush. This extends the internal control protocol; both native
and Python fixtures must cover the receipt and its failure paths.

The desktop holds its client handle after that receipt until the server
disconnects, under the original cancellation/deadline controls. This allows
the server's last peer validation to finish. Additional bytes after End are
rejected. Normal stop has a five-second total budget for queued data and the
receipt, with shorter per-operation deadlines. That budget does not limit
recording duration; an exhausted tail is incomplete. Hard cancellation and
EXIT close transport without promising a reasoned End packet; the reserved
Disarmed/OBS-exit reasons are not emitted by this increment. Callback quiescence
and cancellation still wait for native operations to relinquish their buffers.

Stream stack storage is fixed at approximately 320 KiB in the current worker;
capture queues and converters are separately bounded allocations. Synthetic
tests now cover 1,024-frame packets, six buses with 48 tail blocks each, exact
terminal sequences, receipt failures and stopped queues observed before the
frontend publishes its stop event. Native admission and desktop child fixtures
exercise the receipt/disconnect exchange. These are synthetic/native component
checks, not actual OBS streaming acceptance.

Acceptance for this increment additionally requires delayed/stale frontend work,
stop during attach, duplicate stop during draining, cancel without frontend
progress, native End/receipt delivery and exact-source build/test receipts.
The component receipts above do not validate these edits. Root ran the same
build/test/smoke tools with new output paths so the component evidence stays
intact:

```powershell
& $py native/obs-plugin/tools/build.py --toolchain $toolchain --obs-bin $obsBin --headers $headers --output "$pcm/integration-build"
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --build "$pcm/integration-build" --headers $headers --output "$pcm/integration-verification"
& $py native/obs-plugin/tools/smoke.py --build "$pcm/integration-build"
```

All 24 build commands and 51 native verification commands pass. The latter
includes 84 focused Windows pipe/Arm/terminal-receipt Python tests. The driver
binds 67 native source files, 14 desktop inputs, 23 test artifacts and 51 logs;
root independently compared 331 source/input/artifact/log hashes. The smoke
check still refuses headless initialization and preserves fixed pairing-store
metadata. No OBS application, audio device or consumer configuration was used.

- Build receipt: `4b2b262a1cf66e15df26a3fc2623b263a7e791cb8fbd2b34a05f77cf2534a3fa`.
- Test receipt: `eee66813c7ae6051a4db5817839dbab25c2543c043cfe2f43e2a51f3f770fe69`.
- Smoke receipt: `7b3501c377df8130b10fe470b18a9ffdd98aae673f438b09187ee2578cef1fc5`.

Independent capture, transport, runtime/bridge, dispatcher and client-receipt
review is clear after the fixes above. Final verification includes the corrected
module description. No app entry
point, live OBS compatibility or new release is established by this work.
