# OBS client enrollment and request authorization

September 13, 2026. The proof/admission increment merged through PR #34 at
`9260e6b`; [exact-source desktop CI](https://github.com/RioPlay/utterleaf/actions/runs/34754090586)
passed all five required jobs at `d44126a`. The private-store increment merged
through PR #35 at exact source head `c7f86f6202ff9cd6acc647443b9d0ce768b6359b`,
with merge `3bd072deb7f03952f42d5516ff3c5818e1ab53e8` at
`2026-09-13T12:03:22Z`. Exact-head CI
[34755748029](https://github.com/RioPlay/utterleaf/actions/runs/34755748029)
passed all five desktop jobs; release publication was skipped. No live OBS
entry point exists.

On `feat/obs-enrollment-flow`, the typed desktop preparation adapter below now
passes **341** focused tests, including **66** enrollment cases. Independent
source and final test review are clear after the documented failure-path additions.
The native owner, Tools flow and vendor registration are now linked bounded
components; frontend/device and real OBS acceptance remain unverified. No
installed release changes here.

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
- Keep capture disabled until its integration gates pass. Do not launch OBS,
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
revocation. Forget pairing is separate from Reset defaults. The storage component
below implements persistence; the desktop import/replace/forget flow is now
exposed in the development source through the separate
[pairing setup dialog](obs-desktop-pairing-ui.md).

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
or the pipe Hello secret. The typed client adapter and strict native dispatch
are implemented in the linked increment below; actual OBS acceptance remains open.

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
Final independent source/evidence review is clear for this component. Its proof
tests do not verify the later stores, app pairing flow, vendor JSON adapter,
atomic Arm or actual OBS/audio integration. Storage evidence is recorded below.
Existing desktop/Android binaries remain unchanged.

### Enrollment workflow integration contract

Continue on `feat/obs-enrollment-flow`. The area includes native pairing Tools,
one per-user live owner, vendor dispatch, and the desktop control/setup flow.
Keep the five existing Settings destinations; eventual OBS setup opens from
Speech & privacy in its own window. No connection, import, preparation or
restart may arm capture. Android and published desktop binaries are unchanged.

The first desktop adapter adds `ObsControl.prepare_session(key,
additional_mix_mask=0) -> bytes`: an explicit call generates its own fresh,
nonzero 16-byte session and uses the actual caller PID. Accept only a nonzero
32-byte `bytes`/`bytearray` capability and an exact integer mask from 0 through
63 (not `bool`). One control connection permits one preparation attempt.
The existing version/status request entry remains read-only; a separate narrow
adapter sends only these fixed requests under vendor name `Utterleaf`:

| Request | Exact request data | Exact successful response data |
| --- | --- | --- |
| `IssueAuthorization` | `clientPid`: integer 5–4294967295; `sessionId`: 32 lowercase hex characters, nonzero; `additionalMixMask`: integer 0–63 | `ok`: true; `protocolVersion`: integer 1; `challenge`: 120 lowercase hex characters |
| `PrepareSession` | `challenge`: 120 lowercase hex characters; `proof`: 64 lowercase hex characters | `ok`: true; `protocolVersion`: integer 1 |

The failure response is `{ "ok": false }`. Reject extra fields, incorrect types,
noncanonical hex, versions and echoes. The outer `CallVendorRequest` response
must contain exactly the matching `vendorName`, matching `requestType` and an
object `responseData`, in addition to the existing matching OBS request ID/type
and success-status checks. This envelope follows the pinned
[OBS protocol](https://github.com/obsproject/obs-websocket/blob/1ef34bf48110c2a18184e50e41cd0b1a855e2147/docs/generated/protocol.md#callvendorrequest).
Require `CallVendorRequest` in the advertised capabilities only when preparing;
status-only connections remain compatible without the plugin.

After receiving the challenge, revalidate the authenticated native peer
immediately before calling the existing proof function, with no intervening
network operation. That function validates every challenge field against the
actual PID, fresh session and selected mask. Never put the capability or pipe
Hello secret into JSON. Clear the adapter's owned mutable key on every exit;
Python/OpenSSL erasure remains best-effort. Do not retain or log request secrets.
Malformed, refused, mismatched, cancelled, timed-out or uncertain operations
close the connection with no retry. A nonblocking reentrant operation lock
serializes complete prepare/status/event/peer-lease operations; a second thread
is rejected and closes the connection. Close itself remains able to interrupt I/O.

Return only the client-created session ID after confirmed prepare success.
The existing pipe client derives its fixed name from this ID and independently
checks the server against the retained control-process lease; do not accept a
response-selected pipe path or PID. Preparing does not connect the pipe, confirm
handshake readiness, or establish an idle/armed state. A failed response may
leave a native admission until its bounded server expiry; do not claim rollback.

Acceptance: focused control, proof, transport, pairing/privacy/boundary checks;
synthetic loopback request/response interoperability; independent review of the
contract, diff and results. Verify invalid local inputs before any request,
challenge binding and post-challenge identity failure before any proof is sent,
strict replies, event ordering, cancellation, concurrent-operation rejection,
fresh session generation, one attempt and no automatic capture or logging.
Use scoped `PYTHONPATH` and `python -m pytest tests/test_obs_control_enrollment.py
tests/test_obs_control.py tests/test_obs_authorization.py tests/test_obs_websocket.py
tests/test_obs_audio_pipe.py tests/test_privacy.py tests/test_repo_boundaries.py
-o addopts='' -q` from this worktree. Native ownership, callback shutdown,
pairing Tools, bounded admission expiry, vendor dispatch, visible setup, atomic
Arm and PCM still require their own integrated verification. Stop changing this
adapter when its checks and review pass; continue that required native/UI work.

Implementation verification on September 13: the exact nine-file focused pytest
bundle (control enrollment, control, proof, WebSocket, audio pipe, pairing store,
Windows pipe, privacy and repository boundaries) passes **341 tests, no skips,
in 6.20 seconds**. The 66 enrollment cases include an actual ephemeral loopback
WebSocket exchange and independent literal-domain HMAC validation. That server
uses a stub for native process identity; it is not a running OBS instance.
Existing native identity/pipe checks retain their separately recorded scope.
Five real two-thread cases exercise overlap with preparation, status, event
polling, lease retention and close; both success and post-proof failure observe
the adapter's mutable key cleared. Schema/echo/binding failures, cancellation,
terminal uncertainty, one attempt, fresh sessions and no payload logging pass.
Independent source/test review found no source defect, requested the latter
failure/concurrency checks and cleared their final implementation. No full package or native rebuild
is warranted by this Python-only adapter; no app/UI entry is enabled yet.

#### Selected native callback lifetime and ownership

The public C frontend API has no Tools-item removal function. The pinned
[vendor dispatcher](https://github.com/obsproject/obs-websocket/blob/1ef34bf48110c2a18184e50e41cd0b1a855e2147/src/WebSocketApi.cpp)
copies a callback before releasing its mutex and invoking it; unregistering a
request therefore does not establish callback quiescence. Keep the original C
implementation and solve lifetime explicitly rather than freeing callback data
after unregister alone.

Before registering any callback, pin the module with
[`GetModuleHandleExW(PIN | FROM_ADDRESS)`](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-getmodulehandleexw),
using an address of static module data. Failure refuses load. Claim a never-reset
first-load latch and allow only one generation per OBS process; after shutdown
the gate must never reopen. Windows keeps a pinned module resident until process
termination. Plugin reload/update consequently requires restarting OBS.

All callbacks receive static module state, never a heap-runtime pointer. That
state holds a permanently initialized SRW lock, a phase and the runtime pointer.
Callback entry checks the accepting phase while holding the lock before accessing
runtime state. A file picker releases the lock without retaining borrowed runtime
state, then reacquires and checks the phase before any commit. Return data is
copied locally before calling OBS response APIs outside the gate. Closed Tools
callbacks return; closed vendor callbacks return only `{ "ok": false }` without
accessing runtime, frontend, stores or logging. Pinning protects our code/data,
not OBS APIs after their own teardown.

At `OBS_FRONTEND_EVENT_EXIT`, first disable vendor dispatch and close the runtime
gate under the static lock, signaling only stable cancellation objects. Unregister
requests before any joins. Then detach runtime, take its operation lock before
accessing the mutable authorizer, revoke/cancel/join the worker and drain retained
runtime leases before freeing the store, exclusive owner and runtime. This
rejects callbacks copied earlier but invoked later. Do not remove the frontend callback from inside
itself. The [frontend contract](https://github.com/obsproject/obs-studio/blob/ba2f32bdf791005443988a4955e963663e16b1ed/docs/sphinx/reference-frontend-api.rst)
makes EXIT the final opportunity to call frontend APIs. Module unload is an
idempotent native-resource fallback; if EXIT was missed, it must not call
frontend or websocket unregister APIs whose teardown order is not established.
No joins, dialogs or OBS/frontend calls occur under the static/authorizer lock.

The live owner holds a verified noninheritable share-zero private file handle
at `Utterleaf/obs-plugin/owner-v1.lock` beneath LocalAppData until teardown.
Validate path/locality/DACL through the existing store boundary; do not duplicate
a weaker path-only check. A second OBS process cannot install an authorizer or
dispatch privileged requests. A crash releases the handle; the inert lock file
may remain. Creating/replacing/forgetting pairing suspends dispatch and uses the
same owner. Forget always revokes the live generation, including deletion failure;
report nondurable deletion failure distinctly.

These constraints are implemented with the bounded fixture evidence below;
real OBS interaction remains unverified. Acceptance must simulate a copied callback after close, overlapping close and
dispatch, failed pin, second load, missing EXIT, in-flight worker cancellation,
and a second actual Windows process competing for ownership. A joinable worker
must also expire a prepared admission without depending on another incoming
request. Finalize that bounded handshake/READY lifetime before exposing Prepare;
the full Arm/PCM state machine remains required.

### Linked native integration verification

The native increment links `plugin_state`, `pairing_ui`, `vendor_dispatch`, stores,
authorization and admission into the original module. It adds a single native
Tools entry and a common-controls manifest. Both vendor endpoints remain disabled
until both registrations succeed. Failed rollback unregister retains its flag
for EXIT retry, while the disabled gate refuses copied callbacks. Unload only
disables native dispatch and closes state; it makes no frontend/websocket calls.

Replacement commits the store before retiring the old generation. A precommit
failure preserves its exact authorizer, challenge and worker; postcommit store
uncertainty or failed authorizer activation leaves pairing unavailable. The UI
distinguishes these from a successful pairing whose export failed. Forget revokes
before attempting deletion and reports nondurable failure. Informational dialogs
use Close, while file selection/confirmations can cancel before mutation.
UI rendering, keyboard/accessibility interaction and real frontend load still
require acceptance.

One joinable admission worker bounds authentication to 15 seconds and READY
retention to at most another 15 seconds, then cancels without further requests.
A completed worker handle and one canceled admission can remain until the next
state call or close safely reaps them. `admission_pending=false` describes the
worker, not zero retained handles or a closed pipe handle. No PCM or Arm exists.

The September 13 driver at `.grok/obs-enrollment-flow/native-final/test-receipt.json`
passes all **28 compilation/test commands**, including real Windows owner-process
competition, controlled pin/reload/missing-EXIT/worker cases, close overlapping
an in-flight Issue call, and the bridge wrapper's registration/teardown failure
paths. Six parsed-request tests use actual libobs data APIs with a substituted
runtime boundary and no OBS startup. They cannot verify duplicate/null JSON
fields that libobs parsing discards. The receipt binds native/client sources,
compiler, logs/artifacts, pinned headers and the associated build inputs.
Three existing test-only heap-shim link warnings remain; production compiles
with warnings as errors.

The linked build uses 41 verified public resources. Its DLL SHA-256 is
`b029401c1f5da71bf3c27c7dce084aa9c183d8ce8366f2ad1907c1447fe871cf`.
`build-a/smoke-receipt.json` verifies headless refusal before store startup,
returned libobs shutdown and unchanged metadata for the three fixed consumer
store nodes; no contents are read, consumer paths created or OBS application/audio
started. The exact build/test commands are in the native README. These are local
fixture results, not successful frontend initialization or live OBS acceptance.
Final independent source/test/documentation and receipt review is clear. The
reviewer rehashed build inputs/outputs, both OBS runtimes, invoked tools, smoke
inputs, native/client sources, dispatch inputs and all test artifacts/logs against
the current files. All five desktop CI jobs passed for the linked native checkpoint `15e1c77` in
[34758907354](https://github.com/RioPlay/utterleaf/actions/runs/34758907354).
The draft PR does not establish actual OBS frontend or live-audio acceptance.
The [desktop pairing setup follow-up](obs-desktop-pairing-ui.md) records its own
new source, owner/UI checks and isolated native TaskDialog acceptance; that later
work is not covered by the earlier CI run.

### Private pairing stores: contract

The selected export/import and persistence boundary lives in original native
`src/pairing_store.c/.h` and desktop `utterleaf/obs_pairing_store.py`, with their
own tests. The authorization component accepts a key but neither provisions nor
persists it. The following contract covers storage; implementation evidence and
remaining UI/integration gates are separate below.

Use one bounded binary envelope in both languages:

| Bytes | Outer file |
| --- | --- |
| 0–3 | ASCII `ULPK` |
| 4 | Version 1 |
| 5 | Role: native store 1, transfer package 2, desktop store 3 |
| 6–7 | Zero |
| 8–11 | Unsigned little-endian protected-blob length, 1–4096 |
| 12 onward | Exactly that many DPAPI bytes; no trailing data |

DPAPI plaintext is exactly 72 bytes: `ULKI`, version 1, the same role, two zero
bytes, the nonzero 32-byte capability key, then a 32-byte HMAC. Compute the HMAC
with that key over ASCII `Utterleaf OBS pairing package integrity v1`, its NUL,
and the first 40 plaintext bytes. Validate exact size, role, fixed fields and tag
before accepting the key. Use the existing CNG helper and Python stdlib HMAC,
with a constant-time tag comparison. This checks for corrupted plaintext even
when DPAPI returns success; Microsoft recommends additional integrity checks in
the [Unprotect remarks](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata).
It does not establish the exporting executable's identity or defeat same-user
replacement. Keep the previously specified process verification before use.

Use CurrentUser DPAPI with `CRYPTPROTECT_UI_FORBIDDEN`. The description, optional
entropy, prompt and reserved arguments must each be NULL. Never use LOCAL_MACHINE. Clear
owned sensitive buffers and native DPAPI outputs before `LocalFree`; preserve
the documented Python/OS memory-erasure limits.

Resolve LocalAppData through
[SHGetKnownFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath).
The native authoritative store belongs at
`Utterleaf/obs-plugin/pairing-v1.dat` beneath that directory; desktop imports
belong at `Utterleaf/desktop/obs-pairing-v1.dat`. Use separate native/desktop
subdirectories. Import must decrypt and validate role 2, then protect a new
role-3 record. Never persist transfer bytes as the desktop store or place keys
in existing roaming configuration, backups, logs, models or transcripts.

Create native and desktop store files, transfer packages and new app-owned
directories with a protected current-user-only DACL and noninheritable handles.
Use stable TokenUser SID, not the admission helper's logon SID. Check owner and a
protected non-NULL DACL containing exactly one noninherited allow ACE for that SID
with `FILE_ALL_ACCESS` through held handles. Existing app-owned objects that do not
meet this boundary fail without silently changing their permissions. The existing
LocalAppData root and a user-selected export/import parent are not app-owned:
validate their locality/path separately and do not replace their ACLs.

Initially support local drive-letter volumes reporting persistent ACL support.
Reject UNC/network storage, unsupported volume security, non-disk handles,
reparse paths and oversized files. Inspect final paths, volume and attributes
using held handles, including the owning directory during operations. Document
redirected/reparse LocalAppData and non-ACL volumes as unsupported. Same-user
pathname interference is outside the security claim; path checks alone must not
be described as protection against it.

Use a random `CREATE_NEW` temporary file in the verified destination directory,
explicit DACL, bounded write, write-through and `FlushFileBuffers`, then a
same-directory [MoveFileExW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw)
commit. Initial creation/export never replaces an existing destination. Replacing
a fixed store requires an explicit replacement action and serialized owner.
Reopen and revalidate the final object before reporting success. Do not use
`ReplaceFileW` under the assumption that it retains the new file's ACL: it
[preserves the old DACL](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew).
Do not claim power-loss guarantees beyond Windows/filesystem behavior. Never
promote leftover temporary files at startup; their cleanup is best-effort.

An absent store means no pairing. Corrupt or inaccessible state is a visible
error, not permission to generate or restore a key automatically. Native
replacement commits the new store before retiring the old authorizer and
installing the new one while privileged dispatch is suspended. Never join
workers under the authorizer SRW lock. Export failure does not roll back an
already committed native key; allow a new explicit export of that key.

Import holds the selected package against modification through validation and
desktop commit. Remove that same package only after the committed desktop store
verifies, using its held handle where deletion access is available. Otherwise
report that pairing saved but the transfer file remains. Cancellation before
commit changes no store and removes no transfer file. A copied transfer file is
still usable by its Windows user until authoritative OBS revocation.

OBS Forget suspends privileged dispatch, then removes the authoritative store.
Whether removal succeeds or fails, revoke/join the current live authorizer before
ending the operation. If removal fails, keep current dispatch disabled and report
that revocation is not durable: restart may restore the old key until its store
is removed. Do not claim durable success on that path. Desktop Forget removes only its own copy
and must explain that it does not revoke copied packages. Reset defaults touches
none of these files. A later UI integrates these operations explicitly; no import,
replacement, restart or connection may arm capture.

Acceptance for this increment is real Windows native role-1 create/reload,
role-2 export to Python import/role-3 persistence, reload and native authorization
using the same key.
Cover role/length/tag corruption, DPAPI failures, current-user ACLs, noninheritance,
reparse/remote/unsupported-volume refusal, pre-existing app-owned objects with
the wrong DACL, existing destination, failed writes
and commits, cancellation, package-removal failure, forget and restart behavior.
Use disposable directories/keys and injected failure points; do not change the
consumer's actual pairing, settings, OBS profile, audio or permissions. Add no
third-party dependency. Keep native store/test ownership separate from the
desktop module/tests, with the test driver and docs owned by the integrator.

Run from the owning worktree with the `$py`, `PYTHONPATH` and `$toolchain` values
above:

```powershell
& $py -m pytest tests/test_obs_pairing_store.py tests/test_obs_authorization.py tests/test_obs_control.py tests/test_obs_audio_pipe.py tests/test_windows_pipe.py tests/test_privacy.py tests/test_config.py tests/test_backup.py tests/test_backup_store.py tests/test_repo_boundaries.py -o addopts='' -q
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --output "C:\Users\unknown\Projects\Mindict\.grok\obs-pairing-store\verification"
```

Obtain independent source/test/evidence review. Stop editing this component when
those checks pass, then continue explicit pairing UI and vendor/Arm/audio
integration.

### Implemented store component and verification

The native store now resolves LocalAppData, creates and validates its private
directories, generates/persists a role-1 capability, exports role 2, reloads,
explicitly replaces and forgets. Status codes distinguish missing state,
existing destinations, corrupt records, unsafe permissions, cancellation,
cryptographic/I/O failure and a committed write that could not be verified.
Output keys are cleared on failure. The store does not own a live authorizer;
the integration owner still must implement the dispatch/revocation ordering
above. Native destruction requires the caller to quiesce other operations.

Desktop `ObsPairingStore` imports a user-selected role-2 package into its own
role-3 store, reloads and forgets it. Import requires an explicit replacement
option for existing state; corrupt/inaccessible state fails visibly. It retains
the package when deletion is unavailable or final commit verification fails.
Both implementations hold verified directory handles, reject insecure existing
objects and keep data out of ordinary config/backup/model/transcript paths.
Desktop operations serialize within a process; cross-process store ownership
remains an integration requirement. Construction creates private directories,
never a capability, capture or connection. Explicit test-root substitutions
exercise disposable storage; production callers use LocalAppData.

Local verification on September 13 passes **292** targeted desktop tests,
including **48** pairing tests, with no skips. Real Windows checks cover import,
reload, explicit replacement, cancellation, corrupt existing state, unsafe ACLs,
write/commit/delete failures, post-commit uncertainty and unrelated-file
preservation. The full explicit native driver passes the existing admission,
authorization and crypto checks, the new five-group store state/fault fixture,
and five cross-language cases. The latter independently decrypt native role 1,
import native role 2 into desktop role 3, reload it and use that key for a native
authorization proof admitting a disposable child process. No pipe worker or PCM
delivery is started by that interoperability check. A real Windows directory
junction is rejected by both implementations without creating descendants in
its target. Native fixture cleanup checks for unexpected temporary artifacts,
refuses to follow reparse entries and reports cleanup failures.

Normal native translation units compile with warnings as errors; standalone
native static analysis also passes. The existing test-only heap shim retains
its three documented local-import warnings. Independent production-source and
test and final receipt review is clear. The local evidence records 22 native
commands, 57 source/artifact hashes, five interop cases and five store
state/fault groups; three known warnings are isolated to the test heap shim.
Exact receipts are `.grok/obs-pairing-store/verification/test-receipt.json` and
`.grok/obs-pairing-store/ci-34755748029/receipt.json`. These results do not
verify different-user DPAPI behavior, power-loss durability, consumer pairing
UI, real OBS dispatch, durable live-authorizer revocation or audio. These
components are linked into the development module, but no binary is published
by this increment and no live OBS/audio acceptance follows.

### Full enrollment checks

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
full [OBS design](obs-audio-design.md). The proof/admission component is integrated;
the private stores are integrated through PR #35. Complete the selected native
ownership and user flow before exposing vendor handling.
