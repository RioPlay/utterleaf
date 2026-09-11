# Foundation execution evidence

September 11, 2026. Foundation development on `feat/android-latinime-foundation`;
signed preview01 is published for testing, separately from Android alpha13.

## Published experimental preview01

[PR #20](https://github.com/RioPlay/utterleaf/pull/20) merged at
`3c79ae9487e1f37aa11dc5c0e91acc0f186cba80` after
[CI 34606586960](https://github.com/RioPlay/utterleaf/actions/runs/34606586960)
passed all 112 emulator tests without failures/errors/skips, build/unit/lint/notices,
actual IME recovery and six dictionary publication process-death cases.

At the user's explicit request, a [signed test download](https://github.com/RioPlay/utterleaf/releases/tag/android-foundation-v0.1.0-preview01)
was published from verified source `d2965d3fc856cd006961c1395575bc7924c970d6`.
Package `org.utterleaf.keyboard.experimental`, version `0.1.0-foundation01`/1,
Android API 26+, ARM64/x86-64. It is a non-debuggable release APK signed with a
dedicated experimental identity, independent of alpha13 and developer debug keys.
APK SHA-256: `de8623794cce675d0ea43e640db65c7cbf2609b01107cbbccde44753960199d3`.
Certificate SHA-256: `ef9c0ef959df3e0828f204975a6f7c64ec2dc64655399e206940c61fb730a4bb`.

Signatures v2/v3, 16KB ZIP alignment and 18 exact notice documents verified. A fresh
API 35 x86-64 emulator installed that signed APK and passed both real-IME typing
and capability tests (`foundation-signed-release-ime-test.log` in the local build
root). Independent release/notice review found no concrete missing notice text in
the selected runtime closure; this is not a complete legal certification. The
public download was fetched and matched byte-for-byte. Release assets include
checksums, build identity and a companion copy of the embedded notices.

No completed replacement, physical-phone or assistive-technology acceptance is
claimed. Voice, production dictionaries/correction and swipe remain unfinished.

## Editor reference and theme/locale cache retirement follow-up

Luna and Terra implemented disjoint cache and editor-lifetime changes, followed by
independent Terra review. Theme/locale invalidation now clears the four strong
keyboard slots without disposing proximity resources retained by active owners.
Deferred callback comparison uses a three-field immutable Kotlin snapshot;
InputAttributes retains private options rather than the full framework EditorInfo.
Handler terminal cleanup cancels deferred bookkeeping without editor callbacks.

Review corrected a test that restored retired caches and the real-IME fixture's
reflective assignment to the new snapshot type. Added regressions cover cache
reconstruction/retained proximity owners, handler destruction, captured private
options, snapshot mutation and null comparison semantics.

The final local command `:app:testDebugUnitTest :app:connectedDebugAndroidTest
:app:lintDebug :app:assembleRelease` passed: 12 JVM and 119 API 35 x86-64 emulator
tests, zero failures/errors/skips. Lint: zero errors, 4,021 warnings and one hint.
Both APKs verified all 18 notice documents against current source. Local log:
`foundation-reference-retirement-final.log` under the UtterleafBuild root.
Unsigned release SHA-256:
`b446dee46efac970856f4acaedf169fefb7fc841ba97f8015cb03b0bbf8bfd40`.
These changes are newer than published preview01; no new APK publication or
physical-device acceptance is implied. W2 remains open.

[PR #21](https://github.com/RioPlay/utterleaf/pull/21) subsequently merged at
`52abb29cc3c572e2a16cf06b6f0be46d9c1d8a24` after
[CI 34615270665](https://github.com/RioPlay/utterleaf/actions/runs/34615270665)
passed 119 emulator tests, build/unit/lint/notices, actual IME process recovery
and all six dictionary publication crash cases. Downloaded report XML confirmed
zero failures/errors/skips; both external-probe evidence files reported pass.

## Hardware-keyboard suppression retirement

Source review found that the immediate hardware-suppression configuration path
cleared local input but left running suggestion requests valid. InputLogic now
exposes its existing locked invalidation boundary; the suppression helper uses it
before the existing composition finish attempt and clears transient state in
finally. Active editor identity is renewed, never reopened if already closed.
The subtype path uses the same extracted helper without changing its semantics.

Terra implemented the two production-file changes; Luna owned the separate Kotlin
regression; independent Terra review checked locking, null bootstrap and failure
cleanup. Review corrected test gate timing, main-thread access and the fixture's
expectation for the inherited composition-finish call. The final regression uses
the actual helper and attached worker with controlled queues and a host connection.
It verifies queued and late results reject, a current request succeeds, local
state retires and a closed session stays closed. The transient-cleanup override
observes invocation only; it does not validate the base resource cleanup effects.

Full local verification passed 12 JVM / 121 API 35 x86-64 emulator tests, lint and
unsigned release assembly (`foundation-hardware-suppression.log`). Both final-source
focused tests and lint passed after test teardown hygiene edits
(`foundation-hardware-suppression-final.log`). Zero failures/errors/skips; lint
zero errors, 4,021 warnings and one hint. Both APKs verified 18 notice documents.
Unsigned release SHA-256:
`9ab553450253f3d2ec5acb20bd2d714e17ce5d695573a053bc2941fff3876ae9`.
The controlled helper test does not establish physical keyboard-attachment behavior.
No new signed APK is published by this follow-up.

## Implemented

- Standalone public-SDK Gradle/CMake build, pinned AOSP source and separate app ID.
- LatinIME renders and handles real IME touch input; native dictionary round-trip
  tested with a synthetic fixture. No production dictionary/model is bundled.
- Restricted manifest, backup exclusions, secure windows, sensitive-field context
  blocking, disabled implicit learning and external voice handoff.
- Kotlin entry points and dictionary factory; inherited Java/native implementation
  retained for incremental migration rather than a wholesale untested rewrite.
- Dark keyboard default; explicit light theme, height, bottom space and feedback
  preferences with draft/apply/discard, practice and scoped reset.
- Request-time editor identities reject stale worker results and queued UI results.
  Start/restart/finish/hide invalidate prior identities; batch reset clears state
  even when the corresponding old result is rejected.
- Gesture cancellation renews an active request identity under the batch lock,
  rejecting canceled tail results without reactivating a finished editor or blocking
  the next valid request.
- Suggestion requests capture text, capitalization/correction flags, deep pointer
  copies, context and settings on the owner thread before worker dispatch. Native
  decoding uses these captured inputs without holding session or batch locks.
- Recorrection indicator changes occur only during session-checked UI delivery.
- Same-field height Apply/Reset now enables LatinIME scaling and reloads changed
  geometry. Theme replacement and feedback refresh run inside the actual lifecycle
  handler, including deferred setup, rather than afterward in a competing renderer.

## Reviewed corrections

The session specialist and independent adversarial reviewer identified stale tail
gesture publication through the worker and UI queues. Review also caught overly
broad start-view cancellation (which could discard legitimate locale/cache setup)
and batch state left active after suppressing an old tail result. Both were corrected.

Live comfort coverage initially failed: the saved scale lacked LatinIME's resize
enable flag, and same-field restart reused old geometry. Height-only Apply/Reset,
separate theme replacement and typing/deletion afterward now exercise those paths.
Tests also inspect session invalidation in the framework-created IME when switching
fields, restarting as a password field, and hiding/reopening the keyboard.

The decoder specialist found that the old worker path read live composer flags
before and after JNI, queried editor context, and passed aliased pointer arrays.
Request capture now runs on the owner thread, before enqueue; the Kotlin composer
snapshot deep-copies pointers and supplies a separate legacy JNI carrier for each
access. Context strings/arrays and correction settings are also captured. Background
batch callers copy pointers before returning, then recheck their session on the owner
queue under the existing batch lock. Fallback callbacks use request-time values.

- Native decoding no longer touches mutable Keyboard state directly; request
  capture now passes immutable ProximityInfo into the dictionary facilitator.
  Suggestion snapshots, spell-check path and proximity tests now verify that
  decoder retirement and exception handling keep the captured owner
  stable until completion. Full suite status for this fix remains 25 unit +
  102 emulator tests on API 35, with lint/connected stability intact.

Independent adversarial review found a remaining recorrection-indicator write on
the worker. Clearing now happens in the session-checked UI message. Deterministic
tests pause at the dictionary boundary while the owner resets/types, exercise copied
coordinates and post-decode capitalization for typing and gestures, and check mutable
context detachment. Queue tests cover cancellation before owner-thread batch capture
and reject stale indicator changes at final UI delivery.

These checks establish isolated composer/context inputs and the tested cancellation
paths. They do not establish complete decoder thread isolation: dictionary replacement,
native traversal/resource lifetime and finalizer behavior remain audit items. No real
dictionary is bundled; synthetic dictionary-boundary tests do not establish physical
swipe recognition, touch comfort or phone cancellation acceptance.

## Dictionary loader lifecycle correction

The next W2 pass found that a delayed loader looked up a group by locale at worker
execution and later compared that group's locale with itself. This could attach a
result to a retired group, including after same-language reloads, and notify stale
listeners. Early returns and exceptions could leave load waiters unfinished. Locale
replacement also failed to dispose dictionaries belonging to the prior language.

Loads now capture the exact group identity when queued. They check it before loading,
before transferring ownership and again at main-thread availability delivery. Rejected
factory results are closed; load completion is released in nested `finally` blocks,
and reset/close releases invalidated waiters immediately. No production dictionary is
opened: the restricted factory still returns an empty collection.

Source review by the specialist caught a cleanup race when reset/close compared
mutable replacement references outside the lock. Retired references now detach under
the state lock; disposal happens afterward. Independent adversarial review found no
blocking issue in that bounded protocol. That pass did not establish native active-reader
safety; the separate lifetime pass below addresses admitted operations.

Seven deterministic loader tests use a per-instance queue and synthetic dictionaries.
They cover queued/in-flight same-language replacement, close during loading, failed
factory recovery, stale final UI notification, reuse versus language replacement, and
concurrent close while disposal is blocked. The first full run exposed an IME fixture
race: framework visibility/`isActive` can precede the service's input-session transition.
The fixture now waits for observed session invalidation before checking the next field.

## Native and editor data lifetime

Kotlin `NativeOperationGate` now provides nonblocking exclusive admission with
same-thread nesting for BinaryDictionary operations. Closing rejects new operations
immediately; active JNI work keeps its traversal sessions and native dictionary until
its final lease releases. Resource disposal runs outside the gate monitor. Internal
flush/reopen preserves this protocol without reopening public admission. Busy callers
receive unavailable results; no automatic retry or language-quality claim is implied.

The facilitator also retains a leased ProximityInfo owner for the whole dictionary
loop, including exception paths. Deterministic tests simulate finalizer retirement
during decoding rather than depending on GC timing. A paused real native dictionary
call checks close during admission and final cleanup. These are bounded ownership
checks, not a complete JNI/parser audit or authorization to load external dictionaries.

Full composer reset detaches pointer arrays, preventing a shorter later composition
from inheriting a prior gesture tail. Gesture text replacement deliberately preserves
its active path. Service destruction closes suggestion admission, removes queued work
and releases local editor references without host IPC or waiting for an active decoder.
That decoder may retain its immutable request until completion. Subtype changes now
renew the identity under the existing batch lock, release queued snapshots, and rebuild
active editor caches from current selection. Inactive subtype callbacks avoid editor
reads. The real IME fixture moves the cursor, invokes the subtype callback and types/
deletes afterward; controlled tests cover old callbacks and canceled queues.

Lifecycle boundaries release pooled suggestion labels/descriptions/tags, expanded-pane
builder keys, hover delegates, drawing caches and accessibility autocorrection words.
Gesture preview dismissal clears its words even if previews have since been disabled.
Independent review and synthetic cache tests cover cleanup and subsequent strip reuse;
expanded-pane reopening and physical accessibility interaction remain unverified.
Reachable-reference cleanup is not secure memory zeroization.

Traversal sessions now retire separately from dictionary data. The native gate
coalesces one fixed maintenance action and keeps exclusive ownership while it runs
outside its bookkeeping monitor. An active decoder finishes first; terminal close
supersedes pending maintenance. Cleanup detaches session maps before closing native
sessions and never deletes dictionary entries/files.

The owner-captured editor identity travels through each Kotlin snapshot carrier and
is checked inside native admission, before traversal lookup. This prevents a worker
that passed an earlier check from recreating old caches after idle retirement. Tests
exercise idle/active cleanup, late admission, close/maintenance races, exception
recovery, dictionary/collection forwarding, and expandable-wrapper cleanup while
its write lock is held. Synthetic dictionary handles, entries and file bytes survive
session cleanup. Start-view-only restarts also retire native sessions while preserving
the separate locale/cache setup queue.

## Framework finish targeting and queued results

Source review of the [pinned API 35 framework](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-15.0.0_r1/core/java/android/inputmethodservice/InputMethodService.java)
confirmed that Android invokes finish callbacks while the old connection is current,
then installs the replacement before start-input callbacks. The inherited LatinIME
deferral moved superclass finishing past that replacement, so it could finish composing
text on the wrong editor. Superclass finish calls now run exactly once at their public
framework boundary; local retirement runs in `finally`. Deferred finish-view handling
does no editor IPC or local composition cleanup. Immediate hardware-configuration
cleanup remains a separate path.

Two text-bearing UI result message types now have targeted removal after identity
changes. Cancellation/subtype removal occurs inside the existing batch lock before
new work can enter; startup locale/cache messages and newly queued cancellation
feedback remain intact. Independent review passed the source and controlled proxy-
editor/queue tests. The finish-boundary acceptance run passed 12 JVM and 57 emulator
tests with zero failures/errors/skips. The first word-boundary run found one failing
normalized-query fixture; review corrected its assumption about the inherited walker
depth limit. The combined notices/word-boundary run then passed.

## JNI input hardening

The next native review found input-size-dependent stack arrays before decoder
validation, unchecked fixed-size ngram context construction, and missing checks on
several output buffers. The bounded fix validates array shapes/counts, preserves
pending JNI exceptions, and uses heap coordinate copies. Tap decoding requires fewer
than 48 codepoints; empty tap input remains prediction. A new 4,096-point ceiling
rejects an entire oversized gesture request and limits the four raw copies to 64 KiB.
This is an explicit resource policy, not a measured recognition limit; it does not
bound the source gesture accumulator or establish long-gesture physical acceptance.
Word-based JNI entry points now copy into fixed-capacity arrays after checking
null/empty/oversized inputs. Ordinary stored words retain their 48-codepoint limit;
exact matching retains 96-codepoint query capacity for normalization. Beginning-of-
sentence marker insertion checks remaining capacity, and malformed optional shortcuts
reject the whole add. A failing fixture exposed the inherited exact-match walker's
separate 46-stored-codepoint depth limit: longer words can be stored/read but their
normalized queries are not guaranteed to match.

Property-output JNI now validates its three fixed array shapes and six list receivers
before writing. Serialization releases temporary JNI references and stops immediately
on exceptions, preserving the original throwable. A throwing list callback can leave
earlier Java outputs written; this does not promise atomic output. Tests cover normal
shortcut/ngram values and exceptions in both list paths; the combined runtime run passed.

The legacy Sketch bulk-personalization ABI referenced a nonexistent `mIsValid` field,
then continued JNI work with an exception pending. Both Java wrappers and its registered
native entry point now explicitly reject this unsupported API before native data access,
GC, worker/reload scheduling or callbacks. The signatures remain for compatibility;
explicit single-entry dictionary operations are unchanged. Scoped source searches found
no current foundation UI/importer caller, which is not proof against arbitrary JNI
callers. This deliberately unavailable API does not implement safe dictionary import
or remove that roadmap requirement. The combined run passed synchronous-rejection and
unchanged-dictionary-data tests through the wrappers and registered JNI stub.

Header metadata creation now accepts bounded Unicode scalar strings (256-codepoint
keys, 2,048-codepoint values) and rejects malformed/null/NUL/unpaired-surrogate inputs
before creating a dictionary. An explicit 256-input-attribute resource limit is a
foundation policy, not an upstream file-format limit. ASCII and valid Unicode round-
trip tests pass, including supplementary characters and maximum-length fields.
Existing serialization still omits empty-valued attributes on disk. The shared
on-memory and file-creation callers stop on exceptions. Numeric attributes now use
ASCII digits and checked integer accumulation, including valid INT_MIN/INT_MAX.

Header outputs validate receivers and snapshot the attribute map, size and version
before invoking overridable Java list callbacks. The reentrant regression flushes
and reopens the dictionary inside a callback, verifies coherent old-header output
and confirms new dictionary data survives. Six header instrumentation tests passed.
Path JNI now converts valid Unicode scalars to standard UTF-8 so native names match
Java File names, including supplementary characters. Null/empty/NUL/unpaired or
encoded-PATH_MAX inputs reject without truncation; derived header paths also reject
truncation. Open offsets/lengths must fit native int bounds. MmappedBuffer validates
regular-file ranges against fstat on the opened descriptor and checks alignment
arithmetic in a wider type. Tests passed for exact BMP/supplementary paths, unchanged
data after rejection, and a synthetic V202 dictionary at an unaligned file offset.
This does not make a file immutable against later external truncation or complete
the future verified-import policy. Migration remains separate native work.

The linked AOSP gesture-policy factory has no registered implementation. Source
review found that a gesture reaching Suggest could dereference its missing policy.
A safe unavailable path now rejects missing traversal/scoring/weighting policies.
Independent review and tests distinguish accepted tap inputs/prediction, malformed
request rejection, and safe unavailable gestures using native output writes. No
admitted gesture test was run before fixing this gap. The foundation does not currently provide native swipe
recognition; the existing gesture snapshot/cancellation tests do not establish it.
Swipe remains required work, including implementation/provenance and device gates.

A later same-editor audit found a distinct ordering gap: an older gesture's delayed
tail can clear a newer gesture's active flag and overwrite its composer. Renewing the
whole editor token at every gesture start would discard a legitimate previous word,
so that is not an acceptable fix. An unexecuted regression draft is retained under
`test-drafts/OverlappingGestureDispatchTest.kt.disabled`, outside every source set.
It is not included in passing test counts. Complete gesture/tap/tail ordering remains
a required correctness gate before enabling real swipe recognition.

An external emulator-only process-death probe verified an actual SIGKILL followed by
a fresh process: applied height persisted, one synthetic no-backup asset survived,
and the cold-launched practice field was empty. It restores the exact prior preference
map and deletes only its token-owned test files. Evidence directory:
`C:/Users/unknown/AppData/Local/UtterleafBuild/process-death-probe/28eb15fba941417497076338516c82f9/`.
The recorded UID was 10263; old PID 16153 and verification PID 16227 differed.
This does not establish saved-task restoration, framework IME recovery, or preservation
of every model/data format. The phased probe is excluded from ordinary Gradle tests.

The separate **actual IME process-recovery probe** also passed on the API 35 emulator.
An opt-in debug-only Kotlin host kept its editor in a separate process; instrumentation
measured actual keyboard key positions before the verified IME PID was killed. No
instrumentation was restarted afterward. Host PID 20887 and its activity instance
survived IME PID 20845 being replaced by 21124. Actual keyboard touches preserved
`a `, then produced `a b ` and deleted the final space. Geometry and cursor assertions
passed. Recovery required **one same-field user re-show** after the observation window;
this is not an automatic-reappearance claim. Independent review checked the evidence:
`C:/Users/unknown/AppData/Local/UtterleafBuild/ime-process-recovery/84942d3143c8439e869efe5551332563/`.
The controller verified exact enabled/default IME and animation-setting restoration
with no errors, and removed only its token-owned fixture files. This is one synthetic
editor/portrait/emulator scenario, not physical, saved-task, voice or model recovery.

## Packaged notices

The reviewed notice catalog is now a tracked build input. Generated assets contain
only cataloged documents with hashes of their packaged bytes; the three original
upstream notices are refreshed from source on each affected build. An internal
Kotlin activity displays those local documents, without external browsing. The
[dependency inventory](DEPENDENCY-INVENTORY.md) includes dependency/asset evidence
and scoped native notice excerpts. Reviewed libunwind and Android CRT notices now
bring the catalog to 18 documents; precise CRT source-to-object provenance and nested
dependency attribution remain open. This is not a completed license audit or publication
claim. The combined run verified all 18 document hashes
and the internal secure viewer on the emulator. The separate
`tools/verify_packaged_notices.py` check compared both APKs byte-for-byte with current
source, including refreshed modification notes. The checked unsigned release SHA-256
was `d694db8f7f2704699ec999f4a92bde92ceb7d73fc784ce039f92a83e2b686f30`.
The verifier also compares the 47 resolved dependency coordinates with the reviewed
inventory, independent of protobuf ordering. Exact notice bytes are protected from
Git line-ending conversion. Native link maps are local build evidence, not APK assets.
Foundation CI now runs this source comparison and includes Markdown changes because
notices are build inputs; the first remote run passed the source comparison.

## Local verification

Toolchain: JDK 17, Gradle 8.13, SDK 36, NDK 28.0.13004108.

```powershell
./mobile/latinime/gradlew.bat -p mobile/latinime --no-daemon `
  :app:testDebugUnitTest :app:connectedDebugAndroidTest :app:lintDebug :app:assembleRelease
```

The storage-transaction acceptance run passed 12 JVM tests and 102 API 35 x86-64 emulator tests, with
zero failures/skips. ARM64 and x86-64 native compilation passed. Release assembly
is unsigned and is not publication evidence. Lint has zero errors, 4,021 warnings and one hint; missing translations are reported as warnings, not hidden.
The [lint triage](LINT-TRIAGE.md) records category counts and concrete accessibility
and static-lifetime follow-ups without suppressing findings.
The latest local log is
`C:/Users/unknown/AppData/Local/UtterleafBuild/foundation-storage-transaction-acceptance.log`.
The preceding header/recovery build additionally enabled `-PincludeRecoveryHost=true` and built/linted
the separate debug host (zero lint errors, four warnings). Both external death
probes remain excluded from the ordinary test count. The actual recovery controller
ran separately after reinstalling all three debug/test APKs.
This run also verifies no-view local retirement and a controlled deferred equivalent-
editor callback sequence in the real service, followed by injected typing/deletion.
It does not establish physical rotation acceptance. The first traversal run exposed
Kotlin trailing-lambda constructor compatibility; review also corrected a test that
treated the native directory format as one file. The corrected full run passed.
Deferred superclass finish-call targeting passed the separate controlled proxy tests.
JUnit XML reports confirm zero failures, errors or skips. The paused decoder tests
use a synthetic dictionary-facilitator boundary; native persistence/header tests are
separate. Full framework capture with delayed real native decoding remains unverified.

Coverage includes actual IME touch/field switching, sensitive context queries,
manifest restrictions, native synthetic dictionary persistence and invalid headers,
theme defaults, settings accessibility values, recreation, discard and data-preserving
reset. This is bounded regression coverage, not a complete native security audit.

A later repeat caught a first-touch synchronization failure: the harness now waits
for framework IME visibility as well as layout readiness. Dialog actions also wait
for detachment before continuing. These are explicit observable conditions, not
extra fixed sleeps. The updated eight-test emulator suite passed locally.

Synthetic screenshots use an opt-in instrumentation-only capture helper, restoring
secure flags afterward. Visual review found missing settings margins; an initial
padding fallback and assertion were added. Production capture protection remains on.

## Selection, preservation and scoring follow-up

Unexpected selection changes now retire old-caret requests before existing cursor
handling; expected IME callbacks keep their identity and inside-word moves preserve
composition. Inactive callbacks cannot reacquire editor context. The first combined
run executed 90 emulator tests with three failures in the new synthetic selection
fixture: its SettingsValues initialization was missing. The corrected fixture owns
an isolated real settings snapshot, leaving the process singleton untouched. All
four selection tests passed in the subsequent 93-test run. The real framework IME
test also verifies cursor retirement and typing/deletion before subtype switching.

Eight new migration/preservation regressions passed in that run. Production format
migration returns unavailable before changing the owner or files until a recoverable
replacement transaction is implemented. The private candidate-copy helper propagates
write failures and handles empty iteration; it does not replace production data.
Automatic invalid-format, corruption, migration and rebuild failures preserve files
and block subsequent automatic work. Controlled executor tests inspect the live owner
before retirement to prove queued writes are skipped, and verify stale cleanup cannot
close an explicitly cleared replacement. The corruption-retirement boundary is invoked
on a healthy synthetic owner; this does not test native corruption detection.

Three further scoring/statistics tests passed. Native scoring rejects invalid
codepoints before character-table indexing, validates JNI arrays and uses three
heap rows instead of an input-sized stack matrix. Explicit resource bounds are
4,096 codepoints per input and 1,048,576 work cells; unavailable work returns zero
without truncation. An independent full-matrix oracle covers Unicode and adjacent
transpositions. Positive exact-boundary tests include 8,192 UTF-16 units representing
4,096 supplementary codepoints. All four existing statistics commands remain
supported; malformed queries return unavailable and preserve synthetic entries.

Further audit found ordinary v402/v403 flush deleted the old directory before
rename and missed some buffered I/O failures. The reviewed replacement implementation
uses checked staging, held generation identities, nonwaiting directory locks and
atomic exchange/no-replace publication. Four storage tests passed, covering seven
failure stages in both formats, stale-writer refusal, nonblocking contention and
preservation of unknown staging/original user files. A busy native lease does not
make an otherwise valid owner appear unavailable. An uncertain owner remains
allocated until safe disposal but rejects ordinary operations and traversal setup.

Six separate external process-death cases passed on API 35 x86-64, killing the
verified experimental UID/PID before exchange, after exchange, and after both
directory synchronizations for formats 402 and 403. Fresh processes verified the
expected complete generation and old-copy hashes, then successfully wrote and
reopened recovery data. Evidence is in
`C:/Users/unknown/AppData/Local/UtterleafBuild/dictionary-storage-crash/b38815e479c64d0bad5606e825acc101/`.
The six old/new PID pairs were 23553/23601, 23651/23698, 23747/23795,
23846/23894, 23943/23989 and 24038/24084, all UID 10290. These six cases are
outside the ordinary 102-test count. Debug APK inspection found the fault class
and native control exports; neither was present in the unsigned release APK on
either ABI. Both APKs passed the 18-document current-source notice verifier.

Five additional exact/stored/context/traversal tests passed. Stored strings and
headers reject the native U+001F terminator before serialization; exact matching
rejects malformed codepoints and shared character lookup checks its lower bound.
Real Java suggestion calls with unrepresentable or oversized previous words
return empty results without worker exceptions. Traversal initialization uses a
fixed buffer and preserves the existing valid explicit-prefix contract.

The foundation minimum API is 26. NDK 28 exposes the libc `renameat2` symbol only
from API 30, so the helper uses the architecture's syscall number rather than
linking that newer symbol. The Android 8.0 release's
[ARM64 seccomp policy](https://raw.githubusercontent.com/aosp-mirror/platform_bionic/android-8.0.0_r1/libc/seccomp/arm64_policy.cpp)
and [x86-64 seccomp policy](https://raw.githubusercontent.com/aosp-mirror/platform_bionic/android-8.0.0_r1/libc/seccomp/x86_64_policy.cpp)
include the respective syscall numbers in allowed ranges. This is baseline source
evidence, not minimum-API/OEM runtime acceptance. Atomic exchange and separate
directory synchronization follow the documented
[rename semantics](https://man7.org/linux/man-pages/man2/renameat2.2.html) and
[fsync semantics](https://www.man7.org/linux/man-pages/man2/fsync.2.html). Unsupported
operations have no destructive fallback. Synthetic SIGKILL probes cannot establish
power-loss durability or physical storage behavior.

## Remaining release gates

- September 11 recovery recheck at `a9952e7`: opt-in recovery-host assembly passed.
  The first external API 35 run failed the host process/activity/geometry invariant
  (`ime-proximity-recovery/6a952f92dc2c46caaf1fe6fa3a17302f/evidence.json`
  under the local build root). The controller previously omitted rebound state
  on this failure; it now records that state before checking and names the changed
  field, without relaxing the invariant. The next run passed with same-field user
  re-show (`99851cc02fcc41fbb2fc9c7b95caefb0`), as did one repeat
  (`e0033c22432f47cc9a2fcaf33219c78c`). The initial intermittent failure
  remains unexplained; this diagnostic change is not a lifecycle fix.
- Editor/cache follow-up: cached layout parameters and KeyboardId now retain only
  immutable keyboard metadata. KeyboardLayoutSet's forced-cache retirement,
  LatinIME's applied EditorInfo and InputAttributes references remain separate
  lifetime work. The [bounded metadata review](EDITOR-METADATA-REVIEW.md) records
  consumers and scope; no complete cache-retirement or framework recreation claim.
- Remaining callback/data-lifetime audit, native hardening and framework process-recovery tests.
- Real local dictionaries: provenance, import bounds, correction/language quality.
- Daily gestures/refinements, compact actions and real terminal/editor integration.
- Utterleaf voice engine, model setup, editable review and cancellation integration.
- Full legal/asset/dependency inventory and packaged notices before distribution.
- Warning triage, native hardening, measured latency/memory and accessibility QA.
- Minimum-API and physical ARM64 phone testing; emulator checks do not establish
  TalkBack acceptance, touch comfort, battery use or physical-device stability.
- Upgrade/data preservation, remote CI, signed release and Obtainium verification.

These remain requirements; the foundation milestone does not remove them from scope.

PR #19 merged on September 11 at `d7e1338fc0ba53b4a0774f7238c46ba8ee82a0c5`.
Both its [final PR foundation run](https://github.com/RioPlay/utterleaf/actions/runs/34565781700)
and the [main foundation run](https://github.com/RioPlay/utterleaf/actions/runs/34566337066)
passed. Those results cover the earlier foundation checkpoint, not the subsequent
proximity-input refactor. No foundation APK was published.

The [PR #20 foundation run](https://github.com/RioPlay/utterleaf/actions/runs/34600392501)
passed at `45430c8`: build/unit/lint checks, the 102-test emulator suite, actual
IME recovery after same-field user re-show, and six dictionary publication
process-death cases. This covers the proximity-input refactor and diagnostic
change, but does not explain the earlier intermittent local geometry failure.

Follow-up review: independent Terra source/JNI review found no blocker in the
bounded proximity capture/admission change. The captured owner is leased across
dictionary calls and stale request identity is checked independently. This is
source review, not complete decoder isolation or new physical-device evidence.
Luna's recovery audit identified first-visible inset settling as a hypothesis,
not a proven cause. On an invariant mismatch the controller now keeps up to six
subsequent synthetic host snapshots, stopping at the first collection exception
and preserving the original failure. In-memory branch checks covered six samples
and one transport error; the external probe passed after same-field user re-show
at `ime-lifecycle-review-recovery/64ae4f2cca864473b03b5ea196beab06` under the local
build root. Readiness and pass criteria were not relaxed.

## Owner-checked service and view cleanup

Terra implemented a bounded service/view lifetime correction, followed by a
separate Terra adversarial review. KeyboardSwitcher checks the exact LatinIME
owner before delayed deallocation or destruction. Valid deallocation cancels view
events and silently clears pointer trackers and the queue's backing storage while
preserving wiring for view reuse; destruction additionally drops shared service,
view, theme and pointer-proxy references. Review caught two gaps and the final
patch closes both: typing/double-tap timer messages are canceled, and stale service
cleanup cannot clear successor-owned previews, accessibility or settings state.

Two new Kotlin instrumentation tests exercise modeled stale-owner cleanup, silent
queue disposal, non-null reference detachment and timer cancellation. The actual
framework IME test also hides the keyboard, invokes its owner-valid deallocation,
reopens the same view, then verifies literal typing and deletion through touches.
This does not establish every Android service recreation or physical-device path.

The final local command passed `:app:testDebugUnitTest`,
`:app:connectedDebugAndroidTest`, `:app:lintDebug` and `:app:assembleRelease`:
12 JVM tests and 104 API 35 x86-64 emulator tests, zero failures/errors/skips.
Lint remains at zero errors, 4,021 warnings and one hint. Both debug and unsigned
release APKs passed the 18-document current-source notice verifier. The unsigned
release SHA-256 is `7000c8986996f34471e9fd5a28e361c9e17cc5b3dec557d22b5edf4f479863be`.
Log: `C:/Users/unknown/AppData/Local/UtterleafBuild/foundation-teardown-acceptance.log`.
The external IME process-recovery probe also passed against the final debug APK
after same-field user re-show; evidence is under the local build root at
`ime-teardown-acceptance/66d71e3f51f944a2b09643af668fdad4/evidence.json`.
The earlier intermittent geometry failure remains an open investigation.

## Immutable cached keyboard metadata

Terra implemented owned Kotlin `KeyboardEditorInfo`; Luna supplied carrier tests,
and a separate Terra reviewer checked source semantics and the expanded builder
tests. KeyboardLayoutSet captures the four required values once at construction,
including an immutable plain-string action label. KeyboardId and accessibility
consume those copied values instead of retaining framework EditorInfo. Existing
action precedence, navigation, password distinctions and equality are preserved.
Later subtype selection reads the captured FORCE_ASCII/private options. No other
editor reference or forced-cache retirement policy was changed.

The tests cover source-object/label mutation, null-editor defaults, private-option
handling during later subtype selection, action and navigation flags, equality,
and declared cached-field structure. Fixture initialization and a mistaken custom
label/Next expectation were corrected against existing source semantics before
the passing run; production behavior was not changed to satisfy the tests.

The [teardown CI run](https://github.com/RioPlay/utterleaf/actions/runs/34603501626)
passed build/unit/lint/notices but failed two UI fixture assertions. Log inspection
placed the first failure before keyboard creation: the fixture awaited an active
editor before requesting serving after initial IME selection. It now requests
one `restartInput` after focus readiness, then still requires active/visible IME
state. The notice fixture now waits for its accessibility dialog text rather than
checking one immediate root snapshot. Independent review retained the original
security/text/lifecycle assertions. Fresh remote verification remains separate.

Local final command passed unit tests, connected tests, lint and unsigned release
assembly: 12 JVM and 112 API 35 x86-64 emulator tests, zero failures/errors/skips.
Lint is unchanged at zero errors, 4,021 warnings and one hint. Both APKs passed
the 18-document source-notice verifier; unsigned release SHA-256:
`b627d47d5d1380aea14d61a43f01ce54db01b3629e0f2255c6c2d32c62bc2acd`.
Log: `C:/Users/unknown/AppData/Local/UtterleafBuild/foundation-metadata-verified.log`.
The final APK also passed external IME process recovery after same-field user
re-show, with evidence under the local build root at
`ime-metadata-acceptance/1c091d2af1a64a10aa7ddda419ffdf42/evidence.json`.

The [next CI run](https://github.com/RioPlay/utterleaf/actions/runs/34605220732)
still failed the two UI fixtures; build/unit/lint/notices passed and 110 of 112
emulator tests passed. The first keyboard readiness check failed before requesting
serving, so the earlier serving/timing explanation was insufficient. Both
activities reached resumed/displayed state in the logs; the failed focus predicate
and notice root state were not recorded. A test-only follow-up now waits for
layout/window readiness before its single focus/click request, records individual
non-content readiness states and at most eight owned window roots, and retains
the existing security/input/text assertions. Readiness property reads run on main.
The four focused keyboard/notices tests passed locally with no failures/skips
(`foundation-ui-readiness-final.log` in the local build root). Remote root cause
and acceptance remain open until the new evidence resolves them.

An isolated `android-foundation.yml` workflow now mirrors local build and emulator
checks and uploads reports only; no foundation APK is published by this workflow.
The [first remote run](https://github.com/RioPlay/utterleaf/actions/runs/34563567144)
passed compilation, unit tests, lint and packaged-notice verification, then passed
101 of 102 emulator tests. The real-IME fixture requested display before Android
served the field (`PHASE_CLIENT_VIEW_SERVED`), so its helper now waits for an
attached, focused-window, served editor before requesting display. CI also explicitly
enables the software keyboard alongside its virtual hardware keyboard; this is
disposable-emulator setup, separate from the observed ordering failure. External
recovery probes were not reached in that run. Subsequent remote results are tracked
in [PR #19](https://github.com/RioPlay/utterleaf/pull/19).

The [second remote run](https://github.com/RioPlay/utterleaf/actions/runs/34564523438)
passed the same build checks and 101 of 102 emulator tests, exposing a separate
three-button navigation overlap: the injected space activated Home. Switching the
local emulator from gesture to three-button navigation reproduced it. Synthetic
geometry diagnostics placed the space center at y=2305.5 while navigation began at
y=2274 on the 1080x2400 display. The correction reserves navigation bottom insets
on the input root independently of comfort padding and computes editor/touchable
insets from the visible keyboard's actual window position. The fixture retains
real touch injection, rejects navigation-overlapping coordinates, and exercises
top-row typing as well as space/delete. Remote recovery probes were not reached
in that failed run; PR #19 records subsequent verification.

Local navigation acceptance: the full 12 JVM / 102 emulator test run, lint and
unsigned assembly passed with three-button navigation
(`foundation-navigation-acceptance.log`). After the final outline/popup local-coordinate
correction, both `FoundationImeTest` methods passed separately in three-button and
gesture modes (`foundation-navigation-final-threebutton.log` and
`foundation-navigation-final-gestural.log`); lint and unsigned assembly passed again.
Lint remains at zero errors, 4,021 warnings and one hint. Both APKs passed the
18-document source-notice verifier; the final unsigned release SHA-256 was
`7b5d40c9818d31f97b766387eb75f9cabfd82409dfee5f33e1640a1957d2be6a`.
The external IME recovery probe also passed in three-button mode with the same
editor and explicit user reshow, under
`ime-navigation-recovery/a9af3bd6df8b4d7cb4afbce2edac1b5d/evidence.json` in the local
build root. These remain API 35 x86-64 emulator results, not physical acceptance.
