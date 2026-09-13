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
full [OBS design](obs-audio-design.md). The current step is the concrete enrollment
design; no proof protocol, enrollment store or vendor implementation exists yet.
