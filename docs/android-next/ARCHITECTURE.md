# Next Keyboard + Voice architecture

**Status: proposed architecture, not implemented or verified.** This proposes a
new Kotlin-owned Android IME at `mobile/next-keyboard/`. It does not replace, copy,
or alter the existing `mobile/android` IMEs or experimental LatinIME port. The
LatinIME work and its evidence remain separate in
[`mobile/latinime/EXECUTION-EVIDENCE.md`](../../mobile/latinime/EXECUTION-EVIDENCE.md).

The target is a lightweight offline everyday keyboard with a familiar staggered
layout, suggestion/action strip, explicit voice, and an optional dense power
surface. FUTO is a comfort reference, never code, assets, a pixel copy, or proof of
parity. The power layer takes useful Hacker's Keyboard-style controls—visible
modifiers, Esc/Tab/navigation and Fn—without crowding the daily layout.

## Decisions

* Kotlin owns the IME lifecycle, layout, rendering, composition policy, editor
  mutation, preferences, voice state and queues. New code takes no LatinIME Java,
  resources, JNI dictionary code or renderer dependency.
* Main-thread `EditorGateway` is the **only** caller of `InputConnection`, editor
  actions, key events, and batch edits. Screens, gesture/decoder workers, and voice
  receive immutable values and cannot retain an `InputConnection`.
* Unicode typing uses text/composition APIs. Power controls use a separate,
  capability-gated key transaction. A failed Ctrl+C is never replaced with `"c"`;
  voice insertion never sends Enter or an editor action.
* Dictionary format, language assets, correction, prediction and swipe decoder are
  unresolved. Their interfaces are deliberate placeholders; no empty strip or
  preference claims they work.
* Capture starts only from explicit tap or enabled hold. There is no ambient audio,
  cloud fallback, typing history, passive lexical learning, contact/account integration, clipboard
  monitoring/history, dynamic code or unverified asset loading.

The existing voice path supplies a reuse contract, not a ready-made architecture:
private no-backup reviewed-model storage; explicit 16 kHz capture; cancelable local
decode; UTF-8 transcript. Its JNI currently accepts a **file path** and `FloatArray`,
creates a Whisper context per decode, is English-only, has a process-wide cancel flag,
and lacks worker-process IPC. `VoiceSession.runTake` also allocates a 120-second
float buffer and then `copyOf(count)` before JNI: two full-size arrays can coexist,
before JNI copies. The new design therefore cannot claim isolated inference, model
reuse, streaming/incremental decoding, or a measured memory saving. Current
`TerminalInput` similarly shows full down/up attempts but its Boolean result does
not prove a host processed an event.

## Proposed module and ownership

`mobile/next-keyboard/` is a standalone Android app/IME module with independent
Gradle dependencies, tests, Android release path and eventual package/signing
migration. It stays separate from desktop, `mobile/android`, and `mobile/latinime`.
Initial manifest: IME service plus explicit setup/settings activities; no INTERNET,
contacts, accounts, storage, boot, downloader/update receiver, provider, exported
worker component, or backup of models/dictionaries.

```text
KeyboardImeService (main) ──owns──> EditorGateway (main) ──> InputConnection
       │                                  ▲
       │ immutable intents                 │ immutable outcomes / UI state
       ▼                                  │
KeyboardScreen + GestureRouter ───────────┼── SessionReducer (main)
       │                                  │
       ├── SuggestionPort ── bounded queue ──> reviewed local decoder
       └── VoiceCoordinator ─ bounded queue ──> SpeechWorkerClient
                                                  └─ proposed Whisper worker
```

Each live IME or recognition entry point owns its own service-local `SessionReducer`
and `EditorGateway`; adapters may share these value contracts but never a live
`InputConnection`, session identity, or mutable reducer. `KeyboardScreen` renders
immutable `KeyboardUiState`; it has no editor policy. A settings/practice screen may
use a fake local gateway only and never a live host connection or shared text buffer.

```kotlin
@JvmInline value class EditorSessionId(val value: Long)
@JvmInline value class GestureId(val value: Long)
@JvmInline value class VoiceTakeId(val value: Long)
@JvmInline value class RequestId(val value: Long)

data class EditorIdentity(
    val session: EditorSessionId,
    val connectionGeneration: Long,
    val inputFingerprint: InputFingerprint,
)
data class CaretSnapshot(
    val selectionStart: Int, val selectionEnd: Int,
    val composingStart: Int, val composingEnd: Int, val revision: Long,
)
data class GestureIdentity(
    val editor: EditorIdentity, val gesture: GestureId,
    val ordinal: Long, val startCaret: CaretSnapshot,
)
data class VoiceIdentity(
    val editor: EditorIdentity, val take: VoiceTakeId,
    val startCaret: CaretSnapshot, val asset: VerifiedAssetId,
)
```

These are immutable values. `InputFingerprint` contains bounded non-text capability
metadata only: input class/variation/IME flags/action, locale/layout and terminal
preference. It retains neither `EditorInfo`, private options, host package name nor
host text. `CaretSnapshot.revision` advances on local mutation and relevant selection
updates; it is a guard, not a claim that every editor reports selection faithfully.

```kotlin
interface EditorGateway { // main thread only
  fun open(info: EditorInfo?): EditorIdentity?
  fun retire(reason: RetireReason)
  fun updateSelection(update: SelectionUpdate)
  fun execute(request: EditorRequest): EditorOutcome
}
interface SuggestionPort {
  fun submit(request: SuggestionRequest): SubmitResult
  fun cancel(editor: EditorIdentity, afterOrdinal: Long)
}
interface SpeechWorkerClient {
  fun start(request: SpeechStart): SubmitResult
  fun stop(id: VoiceIdentity); fun cancel(id: VoiceIdentity, reason: VoiceCancelReason)
}
interface VerifiedAssetStore {
  fun activeSpeechAsset(): VerifiedAsset?
  fun import(input: InputStream, expected: ReviewedAssetId): ImportResult
  fun select(id: VerifiedAssetId): Boolean; fun remove(id: VerifiedAssetId): Boolean
}
```

`EditorRequest` is sealed: `CommitText`, `SetComposingText`, `FinishComposing`,
`Delete`, `Move`, `SelectMove`, `EditorAction`, `Paste`, `KeyChord`,
`AcceptSuggestion`, and `InsertTranscript`. Each has editor identity, request ID,
source (`TAP`, `GESTURE`, `VOICE`, `EDIT`, `POWER`), caret precondition where needed,
and ordered predecessor. Outcomes are accepted/refused/stale/unavailable; no retry
or replay occurs in a new connection.

## Lifecycle, privacy and capabilities

`onStartInput`, `onStartInputView`, `onFinishInputView`, `onFinishInput`,
`onWindowHidden`, destruction, restart, and materially changed editor metadata retire
the old identity before publishing a new one. Retire runs in one main-thread turn:
remove callbacks; cancel suggestion/gesture/voice work; finish local composition only
against the retiring connection when safe; clear modifiers, layers and UI; drop the
connection. It takes no explicit worker/native/Binder wait and acquires no native
worker lock; an Android `InputConnection` call remains host IPC and is not presented
as nonblocking. Late output must match full identity before it can alter UI or editor.

| Field policy | Allowed behavior |
| --- | --- |
| Password, visible/web password, numeric password or unknown-sensitive | Literal taps/basic host-safe edits only. No voice, surrounding-text read, composition, prediction, correction, learning, clipboard read, gesture trace retention or power inference. |
| `TYPE_NULL` + explicit Terminal preference | Literal ASCII/key events after power capability checks. No voice/context/composition/suggestions/correction/learning/Unicode key-event substitution. |
| `IME_FLAG_NO_PERSONALIZED_LEARNING` | No learning or personal dictionary update. Initial target also disables smart features conservatively. |
| Ordinary field | Capability-gated text/edit, optional reviewed local suggestions, explicit voice review/insertion. |

`CapabilityNegotiator` is policy/eligibility, not host-support discovery. On open
and again at mutation it permits or forbids commit, compose, bounded-context read,
delete, action, key events, Shift-selection, explicit clipboard paste and named
Enter behavior from connection availability, `EditorInfo`, flags and field policy.
It cannot prove that Undo/Redo, a key event, or any action will work in a host; named
host effects need separate evidence. It never uses app title, package name or
remembered success. Refusal shows unavailable and never falls back to a different
semantic operation.

Context is purpose-specific and bounded, never full-document extraction. Candidate
limit for a decoder review: 256 Unicode code points around the caret, copied into an
immutable request and cleared at completion/retire. Restricted fields read none.
Grapheme-aware deletion/word handling is a separately tested Unicode utility, not
UTF-16 guessing.

## Stable keycaps and privacy-gated adaptive touch

Keycaps, labels, row geometry, focus rectangles and accessibility hit targets remain
stable. Optional adaptive touch changes only bounded invisible hit-zone geometry; it
never moves or relabels a key. This is a narrowly scoped proposed authorization for
**geometric calibration** based on explicit correction/accepted-target feedback. It
does not authorize lexical history, passive word learning, storage of typed words,
correction strings, raw touch paths, host/app identifiers, or a background learning
job. The detailed calibration algorithm and evaluation belong in the separately owned
adaptive-touch specification; this document fixes its lifecycle/privacy boundary.

`TouchGeometry` is a small reducer component, not a general learner. It accepts only
the current layout ID, a known intended key ID, and bounded geometry deltas; it emits
a validated aggregate profile for that same layout. Its persisted profile contains
only bounded aggregate key-zone parameters/counts, has a version and layout binding,
and is rejected when malformed, over its fixed size, or for another layout. It stores
no raw event, timestamp stream, word, correction text, editor metadata or app ID.
Raw touch/correction information, if needed to form one aggregate update, is
in-memory only and cleared at the next policy/session boundary.

```kotlin
enum class AdaptiveTouchMode { OFF, LEARN, FROZEN }
data class PrivacyEpoch(
    val editor: EditorSessionId,
    val policyGeneration: Long,
)
data class CalibrationFreshness(
    val privacy: PrivacyEpoch,
    val layout: LayoutFingerprint,
    val profileId: ProfileId,
    val profileGeneration: Long,
    val deletionGeneration: Long,
    val snapshotVersion: Long,
)
interface LearningPolicy { // main-thread authority
  fun effective(field: FieldPolicy, accessibilityExploration: Boolean): LearningPermit
  fun enterManualIncognito(): PrivacyEpoch
  fun leaveManualIncognito(): PrivacyEpoch
  fun invalidateForSession(editor: EditorSessionId): PrivacyEpoch
}
```

`LearningPolicy` is central: every capture, aggregate update, worker publication and
persistence request carries its `PrivacyEpoch`. Aggregate snapshot publication also
carries `CalibrationFreshness`: privacy epoch, layout fingerprint, profile ID/profile
generation, deletion generation and snapshot version. The policy owner admits and
publishes a snapshot through one serialized writer transaction; it compares the full
freshness value at that atomic publication point, never as an unsynchronized
check-then-publish promise. A mismatch rejects the update and clears its transient
aggregate. This specifically prevents training queued before Incognito was enabled
from landing after the toggle. No background task may resume it later. An already
accepted pre-Incognito snapshot write may finish flushing its old aggregate, but it
cannot add Incognito input, publish stale training, or resurrect an explicitly cleared
profile; the implementation must not claim it can retract an OS write already in
progress. The single-writer versioning, atomic publication and crash-recovery tests
are required by the adaptive-touch specification.

| Effective mode | Geometry use and collection |
| --- | --- |
| Off (default) | Static baseline geometry; apply no profile and collect/update nothing. |
| Learn | In ordinary eligible fields only, apply the current bounded aggregate profile and update it from permitted geometric feedback. |
| Frozen | In ordinary eligible fields only, apply the existing bounded aggregate profile but collect and update nothing. |
| Incognito (manual or forced) | Static baseline geometry; no profile application, collection or new calibration update/publication. Already accepted storage flushes have the limited semantics above. |

Manual Incognito is an app-global, sticky preference that remains active across field
changes and process restart until the user explicitly turns it off. Its requested
state is fail-closed while persistence is pending: no learning can resume, and the UI
does not call it durable until atomic preference acknowledgement. A failed/partial
write remains Incognito in the live process with Retry or Keep-session choices. On
startup a missing/corrupt policy record is conservative, while a verified older saved
Off state may restore when a new Incognito write never landed; no phantom persistence
guarantee is made. It is not a destructive data action: entering it clears transient
training state but preserves an existing local aggregate profile without updating it.
Ordinary-field Incognito may still use a reviewed nonpersonal dictionary and explicit
local voice; sensitive-field restrictions remain stricter. Password/unknown-sensitive fields and
`IME_FLAG_NO_PERSONALIZED_LEARNING` force Incognito regardless of the selected mode;
the user cannot override that policy. Accessibility touch exploration also forces
static geometry and disables adaptation/collection until an explicit accessibility
evaluation establishes otherwise.

Preferences Reset restores the selected adaptive-touch mode to Off while preserving
the calibration profile, like verified models; it must never turn off an active manual
Incognito choice, which requires its own explicit exit. A separate, explicit “Clear
touch calibration” action removes that profile after confirmation; it does not touch
models, dictionaries or unrelated preferences. The new setting needs persistence,
reset, Incognito toggle/restart, sensitive-field, accessibility and stale-publication
tests before it is implemented.

## Taps, gestures and ordered tails

When no gesture run is unresolved, ordinary taps bypass the ledger and execute through
the gateway without worker waiting. Suggestions/gesture decoding are optional
enhancements and must pass the same gateway before text changes. While a gesture run
is unresolved, every accepted mutating tap/cursor/edit command is an ordered pending
intent in that bounded run; its pending state is visible and it never claims immediate
editor completion. The UI thread still does not wait for a worker or native lock.

The known correctness issue is specific: an older gesture tail may finish after a
newer one; replacing the full editor generation at every start loses the legitimate
previous word, while accepting the old tail can clear newer state or overwrite its
composer. Use a per-editor **ordered tail ledger**, never one active flag or a
generation per gesture.

```text
editor S: tail 41 (gesture A) → tail 42 (tap/cursor/cancel) → tail 43 (gesture B)
                 | decoder late                              |
                 +-- finalizes only its own ordinal, in order
```

`GestureRouter` assigns a strictly increasing ordinal only within a short unresolved
gesture run. `TailLedger` admits at most **two** unresolved gesture tails and **16**
small intervening dependent intents; admission reserves capacity before accepting a
dependent command. An entry is `Pending`, `Ready(result)`, `RecoverableError`,
`Cancelled`, `Refused`, or `Finalized`, carries its predecessor, and drains only the
longest contiguous *successful or explicitly cancelled/refused* prefix.

Each entry captures two different anchors: `externalSelectionEpoch`, which changes
only for a host selection/composition update that the gateway cannot attribute to its
own just-applied request, and `expectedLocalRevision`, resolved from its predecessor's
accepted outcome. A final A advances the local revision/caret; B therefore consumes
that predecessor-scoped outcome rather than comparing its original `startCaret` with
the newer post-A caret. This preserves A → B ordering without treating self-authored
caret changes as stale. An unexpected host move, selection/composition change, input
restart, or field change immediately cancels the entire gesture run, rejects all its
unapplied writes, clears its UI, and shows cancellation; it is never queued as an
ordinary barrier behind work that might mutate the old anchor.

* A final A runs before its tap/B successor only when still valid; it cannot write
  B's composing state.
* Cancellation/refusal is an ordered terminal no-op so B progresses without A being
  treated as successful.
* Every mutating tap/cursor/edit command during a run has a reserved ordinal and
  remains visibly pending until its predecessor succeeds or the run is explicitly
  cancelled. Outside a run, ordinary taps bypass the ledger.
* Session retirement terminally cancels every entry and clears the ledger. Nothing
  publishes to a new editor.

Reserve capacity **before** accepting a gesture or dependent command. If either bound
is full, return `STALLED` before that input is accepted: no ambiguous input, a visible
“Input busy; release or wait” state, accessible announcement and Cancel. Do not
silently drop an ended tail, overwrite B, or discard A. Already accepted entries keep
their order and resolve with applied, visible cancellation, or visible error outcome.
Cancellation does not free its ordering position until recorded terminally.

Workers are deliberately small, not a generalized async framework: one foreground
voice take and one serial gesture/suggestion decode. The second admitted tail waits
in the two-tail ledger; its decoder context is generated only after its predecessor
has resolved, so it uses the predecessor-scoped caret/text state without a blind
rebase or speculative context-free rescore. At most one coalesced replacement
suggestion exists for the same unresolved composing tail. They never block the UI or
call `InputConnection`.
Before enqueue, copy coordinates, layout/options, bounded context and identity. Main
delivery checks identity, capabilities, caret/ledger predecessor and cancellation.
Decode failure is **not** a terminal no-op: it holds the run at `RecoverableError`,
retains only its bounded request data for **five seconds**, and presents Retry,
Discard gesture, and Cancel run. Retry preserves the same ordinal and may use a fresh
bounded worker request; Discard/Cancel explicitly terminally cancels the whole
dependent run so queued B cannot silently continue after accepted A was lost. At five
seconds it clears retained data and becomes visible cancellation. No automatic retry
crosses a field, gesture, model or decoder generation.

Swipe is unavailable until an approved local decoder exists. Tap typing remains and
the UI tells users why. A future decoder accepts immutable `GestureRequest` only and
requires provenance/license, bounded CPU/RAM, cancellation, multilingual/error
handling, physical-device quality and accessibility evidence before enablement.

## Text, edit and power controls

`TextPipeline` maps daily keys, symbols, alternates and accepted suggestions to text
or composition requests. The reducer owns shift/caps, selected-text replacement,
punctuation and composing ranges. Correction is separate, off until implemented, and
may replace only a valid composition with a one-tap restore held for the active
session. No implicit learning exists; later local entries must be inspectable,
deletable, exportable and policy-excluded where required.

`EditPipeline` maps visible Move/Select, back/forward Delete, Select all, Cut/Copy/
Paste, Undo/Redo and Enter to named requests. Paste reads only after the explicit
tap, has a size bound and never adds Enter. Unsupported actions return unavailable
once; no blind retry/key-event fallback.

Power mode requires an explicit preference and capability gate, an exit and Clear
modifiers control. It retains letters with direct Ctrl/Alt/Shift, Esc/Tab, arrows,
Home/End and PgUp/PgDn; Fn reveals F1–F12, Insert and forward Delete. Meta/numpad
remain proposed. Each displayed control gets a named `KeyContract` plus host evidence
before release.

`KeyChordTransaction` captures editor identity and the full event plan first. It
sends `ACTION_DOWN` then `ACTION_UP` using virtual-keyboard source, soft flags,
normalized meta state, consistent down time and repeat count; it attempts release
even if down fails. The initial supported held-modifier meaning is **local arm**:
Ctrl/Alt/Shift stays visibly armed while touched/latched, and every target key emits
one complete chord with that meta state; it does not leave a physical modifier down in
the host. A later physical hold requires a gateway-owned lease for the original
connection and a strict down/up lifetime contract; it is unavailable until tested.
Finger drift/cancel, layer/mode/field change, hide and retire clear local state; no
cleanup event is sent to a new editor. Event acceptance is never host-compatibility
proof. Shift-selection uses a held-shift transaction only where capability and host
tests establish it.

## Voice state and asset ownership

Each live IME/voice-only/recognition entry point owns its own `VoiceCoordinator` and
immutable `VoiceIdentity`; coordinators never share a live editor connection, take,
PCM buffer or transcript. One app-private `SpeechLeaseArbiter` owns the scarce
microphone/inference lease across every entry point. It admits one owner lease or
returns Busy; it never implicitly stops/cancels another owner. The lease covers
capture, inference, stop/cancel completion, service death and release, and blocks
model import/selection that could race inference. If inference later crosses a
process boundary, the arbiter uses private authenticated IPC and explicit service-death
retirement; it still shares no editor/take state. The existing native bridge has a
process-global cancel flag, so the first implementation keeps this single global
voice lease until a tested dedicated worker supplies scoped cancellation. Capture and
inference leave the UI thread.

```text
IDLE --tap/allowed hold--> PREPARING --mic started--> RECORDING
PREPARING/RECORDING --Stop or hold release--> FINALIZING --audio closed--> TRANSCRIBING
TRANSCRIBING --valid transcript--> REVIEW --explicit Insert--> INSERTED --> IDLE
TRANSCRIBING --hold mode, valid transcript + identity/caret check--> INSERTED --> IDLE
any nonterminal --Cancel/permission loss/session retire/worker death--> CANCELLED --> IDLE
any worker failure/timeout --> ERROR --> IDLE (Retry creates a new take)
```

By default only an explicit Review Insert emits `InsertTranscript(identity, text)`
after editor/caret checks. The distinct, disabled-by-default hold-release preference
is its own explicit insertion authorization: release after a successful take may emit
that same request without opening review, while a tap-started take always opens
review. A transcript with a mismatched identity/caret is cancelled and discarded; it
never inserts into a new field or silently becomes retained review text. The selected
mode is announced and neither flow submits or runs a terminal command. Stop stops
capture before transcription; Cancel discards PCM/transcript and cancels worker.
Model import/switch is refused while a take owns the speech lease. A take resolves
its asset once at start. Silence stop is off until separately designed and verified.

`VerifiedAssetStore` keeps the established good properties: a fixed in-app reviewed
catalog, streaming hash/size verification into private no-backup storage, bounded
input, atomic publish only after validation, failed import preserves active asset,
explicit deletion, and Reset preferences preserves assets. An import selects only a
catalog ID already shipped/reviewed by the app; it never trusts an importer-supplied
hash, manifest, URL or provenance claim. Changing the current English catalog needs
manifest/provenance review. Hash proves identity, not parser safety. Clear audio/result
buffers when practical; do not promise managed-string zeroization.

Initial implementation may use a bounded app-private speech worker with one take and
single-owner PCM buffer plus actual sample count; do not create a full `copyOf` before
native decode. The JNI slice/cancellation lifetime must be explicitly validated.
PCM16 storage/conversion is a tradeoff, not an assumed saving. An `isolatedProcess`
inference service is only a candidate: current JNI needs approved transport redesign
(read-only FD for verified model and bounded shared/FD-backed audio or equally
copy-bounded transport), internal Binder authentication, service-death retirement,
timeout semantics and no path leakage. Never send arbitrary paths, model bytes or an
unbounded PCM Binder parcel. Until complete, document private-worker memory limits.

## UX, preferences, evidence

Daily: staggered keys, wide Space, comma/period, optional number/arrow rows,
secondary hints, symbols and a suggestion/action strip with Voice/Tools. Tools reuse
strip space. Alternates have visible tap paths and cancellation adds no text. Power
rows/layers preserve target size. Voice, settings, switcher, action picker, cancel
and Clear modifiers remain reachable in all configurations.

Preferences are local groups: Typing & languages, Layout & comfort, Gestures &
feedback, Voice & models, Editing & terminal. Defaults: dark/comfortable; number and
arrow rows off; sound off; suggestions/correction/swipe off; tap-to-review voice;
silence stop/terminal off. Every setting has bounded persistence, cancel/tap
alternative, save/reopen/restart/upgrade tests and Reset-to-defaults; Reset preserves
models and explicit user data.

Validation sequence: start with a small literal-key/gateway module and fake-adapter,
composition and lifecycle/sensitive tests; then daily/symbol/edit UI with Unicode,
selection, Enter, resize and real-IME tests. Only when gesture decoding is being
implemented, add deterministic A → tap/cursor/cancel/error → B tail permutations
proving no lost A/overwritten B and visible saturation. Add named terminal/editor task
evidence; voice permission, conflict, stop/cancel, stale transcript, import/model
collision and worker-death tests; then dictionary/decoder provenance, device
performance, battery/RAM and physical accessibility gates. Emulator evidence is not
physical-phone, external-editor, terminal or assistive-technology acceptance.

No source implementation, model, decoder, build artifact or release is delivered by
this document. Existing LatinIME evidence does not validate this new design.
