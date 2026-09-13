# Explicit OBS transcription stop

## Goal and area

Make a manual stop finish the current Utterleaf audio session without stopping
or changing the OBS stream. This is a prerequisite for the visible session
controller in the [full OBS design](obs-audio-design.md), not a live-capture
release or a replacement for its acceptance gates.

Area: the native session command parser, worker/drain lifecycle and PCM terminal
codec; desktop pipe waiting, command dispatch and receiver; their focused tests.
The owning branch is `feat/obs-session-disarm`, following reviewed PCM draft
PR #38 at `c3c4fe5`. Desktop, native plugin and Android releases stay separate.

## Constraints

- Only the explicitly armed, authenticated, single-use pipe accepts Disarm.
  The fixed command is bound to that session and cannot rearm it.
- The pipe has one I/O owner. UI requests signal intent; they do not perform
  native I/O or wait for the audio worker. Existing hard cancellation remains
  available and discards audio according to the owning controller's policy.
- Waiting while armed has no scheduled duration cutoff and stores no audio.
  Cancellation, peer verification, partial-message and active-audio deadlines
  remain bounded. There is no ambient recording or automatic reconnect/rearm.
- Stop detaches callbacks through the existing frontend ownership mechanism,
  drains accepted blocks within the existing total tail budget, then sends a
  reasoned End and verifies its receipt. Timeout or faults remain incomplete.
- Before any Start/PCM, a Disarmed End with no sequences means no capture took
  place. It must not fabricate a primary bus, audio store or complete transcript.
  If attachment wins the stop race, preserve its accepted, aligned first blocks
  and tail. A partial first set, queue fault or normal stop that already won
  cannot be upgraded to a clean no-audio result.
- Stop/normal stream end races permit at most one exact Disarm command before
  the terminal receipt, within its original deadline. Invalid or repeated
  commands, stale sessions and bytes after the terminal exchange fail closed.

## Acceptance

1. A stop request while waiting for a future stream ends without opening stores.
2. A stop during active capture returns the accepted contiguous tail, a Disarmed
   terminal record and verified receipt; OBS streaming is never modified.
3. A simultaneous normal stream stop and user stop has one terminal exchange.
   Fragmented commands, cancellation and delayed frontend cleanup cannot rearm,
   leak ownership or deadlock shutdown.
4. An indefinitely armed desktop reader remains responsive to manual stop and
   hard cancellation. Active/partial-message stalls and identity loss remain
   terminal, with finite operation storage and fixed buffering.
5. Tests distinguish clean completion, no-audio disarm, incomplete recovery and
   intentional discard. Existing Arm, framing and terminal-receipt checks pass.

## Verification

From the owning worktree, using the shared development virtual environment:

```powershell
& $py -m pytest tests/test_windows_pipe.py tests/test_obs_audio_pipe.py tests/test_obs_audio_arm.py tests/test_obs_protocol.py tests/test_obs_session.py tests/test_obs_audio_disarm.py
& $py native/obs-plugin/tools/build.py --toolchain $toolchain --obs-bin $obsBin --headers $headers --output "$disarm/build"
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --build "$disarm/build" --headers $headers --output "$disarm/verification"
& $py native/obs-plugin/tools/smoke.py --build "$disarm/build"
```

Independent review reads the final source, contract, diff and actual test output.
Synthetic Windows/native checks do not establish actual OBS streaming, physical
devices, live recognition, performance under encoder load or release readiness.

## Review and integration notes

The desktop uses a non-consuming Windows pipe query before issuing a bounded
read. One reader sends the coalesced stop intent and the terminal receipt;
control-socket loss does not revoke its independently owned process lease.
An actual synthetic Windows peer checks the armed Disarm/End/receipt exchange
after the control socket closes. It is not the production OBS server.

Review found and corrected an empty-End acknowledgment after preceding Audio
or Gap frames. The client now remembers every decoded frame across read calls;
an empty Disarmed End is valid only as the session's first frame after its own
stop request. Native review also requires a single receipt deadline, the
normal-stop-first result to remain incomplete before Start, and serialized
attachment/stop ownership so accepted audio cannot be silently discarded.
Independent final review is clear. The final canonical verification passes all
51 commands, including 249 focused desktop tests; the 24-command linked build
and headless refusal smoke also pass. Native fixtures cover attachment/Disarm
arbitration, cleanup allocation/post failure, close during cleanup and one shared
receipt deadline. A coarse-clock assertion was replaced with causal read
completion; the two-read timeout regression verifies that the second read receives
the reduced original budget.

Local evidence lives under `.grok/obs-session-disarm/`: `build/build-receipt.json`,
`verification/test-receipt.json`, `build/smoke-receipt.json` and `hash-audit.json`.
All 383 recorded hash comparisons match the final source, inputs, generated
files, artifacts and logs. The installed toolchain is not fully pinned; this is
development provenance, not a reproducible-build or distribution claim.

## Non-goals and stop

Do not change consumer OBS settings, start audio, install a plugin, add recording
automation, implement the UI in this increment or publish a binary. Stop editing
this increment after the acceptance checks, independent review and matching
documentation pass. The next package connects the visible controller and local
recognition, retaining all mixed/separate-bus and real OBS acceptance requirements.
