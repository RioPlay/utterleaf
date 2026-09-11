# Kotlin migration of the LatinIME foundation

Approved direction: Kotlin for Utterleaf-owned Android code and incremental
conversion of the inherited Java foundation. Preserve LatinIME behavior and its
architecture while simplifying the implementation. Native decoder code remains
C++; Kotlin does not make JNI or native parsing memory-safe.

1. Establish a working full Java/Kotlin/resources/JNI build and synthetic IME
   regression fixture before converting the touch/composition core.
2. Write new entry points, session policy, editor/terminal adapters and voice UI
   in Kotlin. Reuse Utterleaf's existing Kotlin voice engine/model contracts.
3. Convert bounded utility and policy classes first. Preserve Java interoperability
   where inherited callers remain, with explicit nullability and lifecycle semantics.
4. Convert settings and presentation components behind persistence/reset and
   accessibility checks; then migrate composition/touch components with matched
   gesture/editor tests. Do not mix behavior redesign with a large mechanical port.
5. Remove superseded Java after its callers and tests use the Kotlin replacement.
   Keep an inventory of remaining Java/JNI boundaries and conversion evidence.

Preserve upstream copyright/license notices and mark modifications. SOURCE.json
records the exact imported upstream bytes; derived files may differ and must have
documented modifications. No assertion of a complete Kotlin port until all intended
Java components have actually been migrated and verified. No removal based solely
on Aden's absence of callers: Android and JNI entry points need source verification.

The current first build introduces Kotlin `UtterleafIme` and `FoundationActivity`
around the actual LatinIME service. These are foundation code, not proof of the
planned voice, terminal, correction or full accessibility implementation.

Owned Kotlin `KeyboardEditorInfo` now supplies the immutable input flags, private
options and copied action label needed by cached layout parameters/KeyboardId.
Inherited Java layout and accessibility logic consume that snapshot, preserving
their existing decisions without retaining a framework EditorInfo in the cache.

The suggestion boundary now adds Kotlin `SuggestionComposerSnapshot` and
`SuggestionDecoder`. Captured text/flags and deep pointer copies isolate composer
inputs; existing Java Suggest and native decoding remain in place. This is a bounded
ownership improvement, not a full conversion or proof of native resource safety.

Kotlin `NativeOperationGate` now controls admission and deferred disposal for the
inherited binary dictionary and proximity handles. It allows same-thread nesting,
rejects competing operations without waiting, and disposes outside its monitor
after the last admitted operation returns. Java/JNI implementations remain in
place; this does not replace native parser hardening or dictionary review.

The gate now also supports one fixed, coalesced maintenance action that runs under
exclusive ownership outside the bookkeeping monitor. BinaryDictionary uses it to
retire traversal sessions while keeping dictionary data open. Snapshot carriers
retain an owner-captured identity predicate, checked after native admission to
prevent a late stale decoder from recreating retired caches. The combined traversal
acceptance run passed; source/reference cleanup is not a complete native security audit.

The internal notice viewer is owned Kotlin and reads only generated bundled assets.
Gradle refreshes upstream modification notes and verifies reviewed source hashes;
emulator tests cover package consistency and local readability. This does not migrate
the inherited keyboard renderer or establish full dependency-license compliance.

An opt-in, debug-only Kotlin recovery host now supplies a separate synthetic editor
process for external IME-death testing. It has no renderer or dependency on the
foundation app and cannot produce a release variant. The emulator verified typing
and deletion after IME restart and same-field re-show while the host survived;
physical and wider-editor acceptance remain separate.

Dictionary storage fault fixtures and crash-probe instrumentation are owned Kotlin;
their control declarations exist only in the debug source set. The atomic directory
transaction helper remains native C++ beside the inherited multi-file writers so
generation checks and publication share one descriptor/lock scope. This does not
introduce another renderer or migrate the shipping app's storage.
