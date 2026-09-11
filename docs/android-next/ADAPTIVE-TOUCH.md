# Adaptive touch and Incognito

Proposed behavior, September 11, 2026. No adaptive engine is implemented by this
design. The visible keys stay in place. A dedicated touch resolver interprets
coordinates against bounded neighboring key zones; a keycap's rectangle is not
the entire touch model. Incognito means no learning.

## Controls and effective policy

| Choice | Touch behavior | Learning |
| --- | --- | --- |
| Off — default | Static, reviewed proximity geometry, including gaps | None; no calibration samples retained |
| Learn — explicitly enabled | Apply the current qualified local calibration | Update only from narrowly qualified correction signals or deliberate practice |
| Frozen | Apply the saved calibration | No samples or updates |
| Incognito — overrides the above | Neutral static geometry | No acquisition, training or new profile updates |

Manual Incognito is a global local preference, sticky across fields and process
restarts. Tools provides its quick toggle, and the contextual bar displays
“Incognito.” Password, unknown-sensitive, raw terminal and no-personalized-learning
fields enforce the policy automatically; their marker says “Incognito · required.”
Leaving a forced field restores the manual preference, never disables a manual
Incognito choice. Incognito is a keyboard policy, not a promise about the host app.

Ordinary-field Incognito may still use a reviewed nonpersonal dictionary and
explicit local speech because neither learns. Sensitive-field restrictions still
block context, prediction and voice as specified in [architecture](ARCHITECTURE.md).
No mode adds lexical history, passive word learning, clipboard history or telemetry.
The user's geometric-calibration request is a scoped exception to the earlier
blanket no-learning design; it does not authorize those other data paths.

Inspect shows aggregate key centers/spread and the active layout profile, never
words, individual taps or a chronological heatmap. Clear calibration is a separate
explicit data action. Turning Off or entering Incognito preserves the old profile.
Reset preferences turns calibration Off and preserves profiles, models and
dictionaries. Reset cannot silently turn off an active manual Incognito choice;
leaving it requires its explicit toggle. Pending drafts never override effective
privacy policy.

## Geometry before personalization

The native renderer draws a single layout; the touch resolver owns all pointer
classification, including gaps, edges, two-thumb overlap, slides and cancellation.
It does not create an Android Button per letter. Layout geometry and semantic key
IDs are immutable, shared inputs to rendering, touch resolution and accessibility.
Per-pointer ownership is fixed at gesture admission under one layout/policy
generation; reflow or privacy change cancels pending pointers before changing rules.

Start with static nearest-neighbor proximity and explicit gesture thresholds.
Personalization then changes a bounded per-key offset and horizontal/vertical
spread, with overlapping candidates resolved deterministically. It changes neither
key labels nor visual positions. Restrict adaptation to ordinary letter keys;
Space, Enter, Delete, modifiers, microphone and utility actions retain reviewed
fixed behavior. No language-model guess may turn a utility action into text or vice
versa. Touch calibration and word prediction remain separate components/settings.

Initial algorithm candidates are diagonal robust distributions or bounded distance
weights. Evaluate them on the same synthetic and consented physical corpus before
choosing. Proposed safety caps: no more than eight local letter candidates per
touch, mean movement at most 20% of key pitch on either axis, nonzero bounded spread,
deterministic tie-breaking, finite-value validation and shrinkage toward the static
prior when evidence is sparse. These are tuning candidates, not proven accuracy
thresholds. No arbitrarily deforming mesh or neural model is needed for this slice.

Use explicit layout/geometry fingerprints, orientation and selected handedness,
not inferred identity or host package. Resizing, split/one-handed changes and layout
revisions select a separately compatible profile or fall back to static geometry;
never blindly scale or mix samples. Accessibility exploration and switch scanning
use stable semantic targets and suspend adaptation until a separately reviewed
interaction establishes equivalent predictability. Ordinary pointer probability
regions need not pretend to be rectangular accessibility nodes.

## Corrections are weak evidence, not ground truth

An immediate replacement can be a change of mind, so unrestricted Backspace-based
learning is unsafe. The initial candidate qualifies only this bounded sequence:

1. One direct letter tap commits one grapheme into an ordinary unselected field,
   with no composition, unresolved gesture, voice, paste or prediction transaction.
2. The next editing intent deletes exactly that just-owned grapheme, with matching
   editor, caret and policy identity. Host outcomes/selection must corroborate the
   operation; ambiguous or delayed observations invalidate the sample.
3. One immediate neighboring letter replaces it without another move, edit,
   selection, restart, layout change or repeat. The *original mistaken touch*
   supplies a low-confidence position for the replacement key.

Only one potential signal is held, expires within two seconds, and is discarded
on every invalidating action. It contains numeric coordinates, semantic key IDs
and identity guards; no word or editor text is copied into the calibration engine.
Do not infer corrections by reading surrounding text. In hosts where exact local
ownership cannot be established, skip learning. Reject non-neighbor changes,
outliers and repeated-delete/replace loops; cap each update and give sparse evidence
low weight. Repeated adversarial samples must still remain inside geometric caps.

Guided practice with explicit known target keys provides a separate supervised
path. A cold profile remains effectively static until its confidence gate passes.
Correction-only learning may converge slowly; do not promise improvement for every
user. Before enabling the feature, compare static versus Learn versus Frozen,
including change-of-mind edits and users whose errors get worse. Improvement must
show lower correction effort without worse uncorrected error rate; otherwise keep
the static default and revise the classifier.

## Data, lifetime and persistence

Store only bounded aggregate offsets/spread/confidence per semantic key and geometry
profile. Provisional cap: eight profiles, 64 trainable keys each and 32 KiB total
serialized data; exact encoding includes schema/version and integrity validation.
No raw touch arrays, typed strings, replacement strings, host identifiers, personal
dictionary, timestamps or input logs are persisted. Profiles stay in private
no-backup storage, with no automatic export or synchronization.

The main owner checks `LearningPolicy` before accepting a signal and again before
accepting an aggregate update. Updates carry editor, layout, privacy and profile
generations. Incognito/Off/Frozen entry or Clear advances the relevant generation,
cancels queued updates, drops the pending correction signal, and prevents stale
completion from changing either active geometry or the accepted saved profile.
No worker keeps a mutable renderer, composer or editor connection.

Persistence must distinguish already accepted pre-Incognito aggregates from new
training: an already admitted storage write may finish flushing old data, but it
cannot incorporate Incognito input, publish stale training or resurrect a cleared
profile. Use a single bounded writer with versioned snapshots and deletion
generations; implementation must prove atomic publication and crash recovery. Do
not claim that cancellation retracts OS writes or zeroizes managed memory. No
per-tap disk I/O, main-thread file writes or worker wait is permitted. Unsaved
ordinary-session updates may be discarded when privacy changes; losing calibration
progress is preferable to weakening the gate. Manual Incognito remains active in
memory on failed/partial save; show “Incognito not saved” and do not claim durable
state before acknowledgement. Startup treats corrupt policy conservatively, but a
crash before any durable write can restore the previous valid preference. No
implementation can promise persistence for an unacknowledged failed write.

## Required tests before availability

- Identical keycap layout with Off/Learn/Frozen; finite, bounded, deterministic
  resolution at edges, gaps and ties; one output per admitted pointer.
- Exact correction versus cursor move, composition, repeated delete, intentional
  replacement, different key layout, emoji and stale host acknowledgement.
- Incognito mid-tap/mid-correction/mid-update/mid-save; no new signal, active update
  or stale profile publication; normal typing remains usable.
- Forced privacy cannot be overridden; acknowledged manual Incognito survives
  field switches, hide/reopen and process death. Failed writes keep the live
  session protected and visibly unacknowledged; restart limitations are explicit.
- Clear during save and process death never resurrects cleared data. Preference
  reset preserves user assets/calibration and active manual Incognito.
- Learn/Incognito/lifecycle interleavings with deterministic queues, malformed
  profile bounds, cold static fallback, and no raw content in on-disk artifacts.
- Named-device error/comfort trials, two-thumb and accessible alternatives, plus
  hot-path CPU/allocation measurements with learning both Off and On.

The conversation mockup only previews controls and illustrative probability zones.
It does not learn the user's touches and supplies no native typing-quality evidence.
