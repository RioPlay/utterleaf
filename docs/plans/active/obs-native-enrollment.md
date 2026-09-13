# OBS client enrollment and request authorization

September 13, 2026. Active on `feat/obs-native-enrollment`, based on PR #33 merge
`006d482`. The [native session primitives](obs-native-session.md) passed their
bounded local checks and independent review; exact-source desktop CI
[34752363075](https://github.com/RioPlay/utterleaf/actions/runs/34752363075)
passed all five required jobs at `5306df0`. No live OBS entry point exists.

## Goal and area

Authorize a deliberately enrolled Utterleaf client before it can create a
privileged OBS session or arm audio delivery. Integrate the existing native
process/pipe admission with original vendor handling and independently verified
request authority. Keep native source/tests under `native/obs-plugin/`, desktop
control/tests under `utterleaf/` and `tests/`, and Android unchanged.

## Verified API constraint

The pinned obs-websocket API v3 exposes neither caller/session identity nor an
authentication result or auth-required query to vendor callbacks. Network
Identify succeeds without credentials when authentication is disabled. The
ordinary Utterleaf client refuses a Hello without authentication, but that does
not protect the plugin against other callers. These facts were checked against
the [public header](https://raw.githubusercontent.com/obsproject/obs-websocket/1ef34bf48110c2a18184e50e41cd0b1a855e2147/lib/obs-websocket-api.h)
and [network dispatch](https://raw.githubusercontent.com/obsproject/obs-websocket/1ef34bf48110c2a18184e50e41cd0b1a855e2147/src/websocketserver/WebSocketServer_Protocol.cpp).

The vendor request handler drops its session context; in-process plugin requests
reach the same callback without that context. Neither callback arrival nor an
asserted PID, path or session ID establishes caller authority. See the pinned
[request handler](https://raw.githubusercontent.com/obsproject/obs-websocket/1ef34bf48110c2a18184e50e41cd0b1a855e2147/src/requesthandler/RequestHandler_General.cpp)
and [vendor dispatcher](https://raw.githubusercontent.com/obsproject/obs-websocket/1ef34bf48110c2a18184e50e41cd0b1a855e2147/src/WebSocketApi.cpp).

Do not inspect private OBS types, infer authentication from TCP timing, or read
consumer configuration/passwords to fill this API gap. Treat vendor transport as
untrusted. The admission helper's authenticated-caller precondition must come
from independent enrollment and request verification, never callback arrival.

## Constraints and decisions still required

- Design explicit enrollment, cancellation, replacement and revocation before
  implementing privileged vendor calls. State the actual same-user/injected-code
  threat limits; a pathname received from a request is not trusted enrollment.
- Define request proof, binding to the intended process/session/operation,
  bounded lifetime and replay consumption using reviewed OS-backed primitives.
  No private enrollment material or pipe secret may enter vendor JSON, logs,
  ordinary settings backup or unrelated transcript storage.
- Keep challenge/pending state bounded, and prove that malformed, unauthenticated
  or replayed requests cannot create or arm a privileged session. Enrollment,
  successful authentication and reconnecting must not themselves start audio.
- Preserve actual pipe-client process checks before the first Hello read and
  the existing single-use and cancellation behavior. Check native completion
  before destroying owned buffers; no detached workers.
- Keep the module inert until its integration gates pass. Do not launch OBS,
  install the plugin, change profiles/routing/recording or acquire microphone
  audio during primitive verification. No new binary publication follows here.

## Acceptance and verification

### Selected contract

Support one active pairing capability initially. The planned OBS Tools panel
creates a pairing package only on an explicit local action; replacement requires
a separate confirmation. Generate a 32-byte CNG key and protect the versioned,
strictly bounded package with DPAPI CurrentUser and a protected user file DACL.
Desktop Settings imports this user-selected package into its own private store.
Neither UI displays or copies the key. Removal of the transfer file is best-effort
and visible; a copied package remains usable by its Windows user until plugin
revocation. Forget pairing is separate from Reset defaults. This flow and its
stores are planned, not implemented by the proof component.

The capability proves possession, not executable identity. It does not protect
against a compromised process under the same Windows user. DPAPI normally binds
decryption to that user's credentials/computer, with roaming-profile exceptions;
do not claim machine binding without qualification. Python cannot guarantee
erasure of all secret copies. See
[DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata),
[CNG random generation](https://learn.microsoft.com/en-us/windows/win32/api/bcrypt/nf-bcrypt-bcryptgenrandom)
and [CNG HMAC](https://learn.microsoft.com/en-us/windows/win32/api/bcrypt/nf-bcrypt-bcryptcreatehash).

Each active authorizer owns one key, one outstanding challenge and at most one
pending admission. The canonical challenge has exactly 60 bytes:

| Offset | Content |
| --- | --- |
| 0–3 | ASCII `ULAA` |
| 4 | Version 1 |
| 5 | Operation 1: prepare; no Arm authority |
| 6 | Reserved zero |
| 7 | Additional OBS mix mask, 0–63; primary mix is always separate |
| 8–11 | Client PID, unsigned little-endian 32-bit |
| 12–27 | Nonzero 16-byte public session ID chosen by the client |
| 28–59 | 32-byte CNG server nonce |

The proof is HMAC-SHA256 with the pairing key over ASCII
`Utterleaf OBS prepare authorization v1`, its terminating NUL, then the complete
canonical challenge. The client must validate every fixed field and match its
own PID, session ID and requested mix mask before signing. Its existing native
OBS server identity and password-authentication checks remain prerequisites.
Vendor JSON will carry only strict fixed-length public encodings, never a key
or the pipe Hello secret. The JSON adapter remains to be implemented.

A challenge lasts 15,000 milliseconds on the server's monotonic clock. A matching
repeated issue request may retrieve it; a different request cannot replace it
before expiry. Exactly one prepare attempt consumes it, including malformed,
wrong-MAC and mismatched-field attempts. Successful proof creates admission only
after consumption; a failed process/pipe creation still consumes the proof.
Invalid requests never open a process or create a pipe. One pending admission
prevents further challenges until its owner releases it. Unauthorized callers
can deny availability by consuming a challenge; bound state and reject, without
claiming that caller attribution or per-IP rate limits exist in this API.

Normal authorizer operations use one SRW lock to serialize state and commit.
Process/token queries during admission creation are under that lock, but pipe
I/O, thread joins and OBS calls are not. Revocation permanently invalidates the
object and clears its key/challenge, then cancels its pending admission outside
the lock. The caller must stop/join admission workers and quiesce all authorizer
calls before releasing or destroying owned state. A replacement uses a new
object after revocation and teardown of the old one; never replace a live key.
The later Arm commit must check that this same owner remains active. No proof
or successful pairing arms capture on its own.

Independent design review accepted this capability/nonce boundary and identified
the stated same-user, transfer-copy and hostile-caller availability limits.
Implementation and final source/evidence review remain separate.

### Implemented proof/admission component

The native `authorization.c` now issues and consumes the canonical challenge,
verifies its proof and creates the owned admission only on success. It retains
one immutable capability generation and implements release and permanent
revocation. `is_active` only reports an owned, unrevoked prepared admission;
it does not prove a completed pipe handshake, peer liveness, idle OBS or Arm
authorization. Revocation/teardown ownership remains as specified above.

The shared native CNG helper replaces duplicated handshake hashing while
preserving the original Hello/ACK wire format. The desktop
`obs_authorization.py` signs only a challenge whose fields match the caller's
PID, session and selected mixes. Neither side imports into an app entry point.

Local verification on September 13 passes **177** focused desktop tests,
including 30 new client proof tests. The native driver passes **10** actual
authorization/pipe child-process tests, the existing **11** admission cases,
the independent .NET/CNG/Python proof vector, crypto input/erasure boundaries,
ten CNG failure points and six deterministic authorizer state/fault groups.
The latter include exact 15-second expiry, delayed HMAC/admission creation,
random/HMAC/create failures, challenge consumption, key clearing, revocation
and a two-thread prepare race with exactly one winner. These controlled
substitutions test state handling; they are not cryptographic or real OBS proof.

```powershell
$py = "C:\Users\unknown\Projects\Mindict\.venv\Scripts\python.exe"
$env:PYTHONPATH = (Get-Location).Path
& $py -m pytest tests/test_obs_authorization.py tests/test_obs_control.py tests/test_obs_audio_pipe.py tests/test_windows_pipe.py tests/test_repo_boundaries.py -o addopts='' -q
$toolchain = "C:\Users\unknown\.local\llvm-mingw-20260616-ucrt-x86_64"
$output = "C:\Users\unknown\Projects\Mindict\.grok\obs-native-enrollment\integration-final"
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --output $output
```

The driver records native and Python client source hashes, compiler, artifacts
and logs. The test-only heap shim retains the three previously documented local
import warnings; normal translation units compile with warnings as errors.
Final independent source/evidence review is clear for this component. The pairing-file flow,
DPAPI stores, persistence/cancel/forget/reset behavior, vendor JSON adapter,
atomic Arm, actual OBS invocation and audio integration are not implemented or
verified. Existing desktop/Android binaries remain unchanged.

### Checks

1. Independently review the concrete enrollment and proof design, including its
   user flow, storage ownership, replay rules and failure behavior.
2. Add deterministic proof/malformed/replay/expiry/revocation fixtures, including
   authentication-disabled and in-process vendor invocation cases. Use native
   disposable peers to bind the authorized request to the actual process.
3. Verify explicit local persistence, cancel and reset/revoke behavior without
   deleting models or transcripts. Add no settings or capture defaults until
   these checks and their user-facing behavior are reviewable.
4. Run the native test driver documented in `obs-native-session.md`, affected
   desktop control tests and independent source/evidence review. Record exact
   commands and results as each part exists; current admission evidence does not
   validate the future enrollment protocol.

## Non-goals and stop

Do not expand into Android, custom speech models, theming, OBS routing changes
or release packaging. Finish each reviewed component, then continue atomic
idle-to-arm/start coordination and actual primary-mix/separate-bus PCM under the
full [OBS design](obs-audio-design.md). Integrate the reviewed proof/admission
component, then implement the selected enrollment stores and user flow before
exposing vendor handling.
