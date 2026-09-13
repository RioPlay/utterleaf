# OBS client enrollment and request authorization

September 13, 2026. The proof/admission increment merged through PR #34 at
`9260e6b`; [exact-source desktop CI](https://github.com/RioPlay/utterleaf/actions/runs/34754090586)
passed all five required jobs at `d44126a`. Native and desktop source/evidence
review is clear for that increment. Continue the selected stores below on
`feat/obs-pairing-store`. No live OBS entry point exists.

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

### Next increment: private pairing stores

Implement the selected export/import and persistence boundary in original native
`src/pairing_store.c/.h` and desktop `utterleaf/obs_pairing_store.py`, with their
own tests. The existing authorization component accepts a key but neither
provisions nor persists it. The following is the next implementation contract,
not a claim that stores or pairing UI already exist.

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

Once the new module/tests exist, run from the owning worktree with the `$py`,
`PYTHONPATH` and `$toolchain` values above:

```powershell
& $py -m pytest tests/test_obs_pairing_store.py tests/test_obs_authorization.py tests/test_obs_control.py tests/test_obs_audio_pipe.py tests/test_windows_pipe.py tests/test_privacy.py tests/test_config.py tests/test_backup.py tests/test_backup_store.py tests/test_repo_boundaries.py -o addopts='' -q
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --output "C:\Users\unknown\Projects\Mindict\.grok\obs-pairing-store\verification"
```

Obtain independent source/test/evidence review. Stop editing this component when
those checks pass, then continue explicit pairing UI and vendor/Arm/audio
integration.

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
implement the selected enrollment stores and user flow before exposing vendor
handling.
