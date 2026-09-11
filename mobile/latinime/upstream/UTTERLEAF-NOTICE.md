# Imported AOSP source

Original source: https://android.googlesource.com/platform/packages/inputmethods/LatinIME

Revision: `127336e9f29d69607eab55982324b210279ae8c5`.

Original NOTICE and java/NOTICE are retained. SOURCE.json in the parent directory
records imported paths and SHA-256 hashes of the original Git blobs. All upstream
binary dictionary files were excluded, including empty.dict; the original NOTICE's
Lexiteria statement is retained as history, not asserted as permission to distribute
those dictionaries. No FUTO or Hacker's Keyboard code/assets are imported.

Utterleaf changes so far:

- DictionaryFacilitatorImpl: no dynamic user/contact/history dictionary types in
  the foundation experiment. Async loads carry group identity through loading and
  main-thread availability delivery; stale results are disposed and latches released.
  Retired groups detach under a short lock, then dispose outside it; locale changes
  close unretained dictionaries. A proximity lease now retains its native owner
  throughout decoding; absent/retired proximity resources return no results.
- DictionaryFactory.java replaced by DictionaryFactory.kt: Kotlin literal-input
  factory; provider discovery, broken-provider reporting and bundled decoding removed.
  Original copyright/license notice retained in the replacement.
- LatinIME: dictionary discovery/dump receiver registration and editor-content
  logging removed; obsolete external hide receiver removed; settings route to the
  owned experiment activity and external voice handoff is disabled.
- InputLogic: chosen-word debug logging removed.
- SubtypeLocaleUtils: resolve resource package from the compiled resource table,
  independently of the inherited Java namespace.
- Resource XML: application-specific attribute namespaces use res-auto so the
  isolated Utterleaf application ID can resolve inherited attributes. Each changed
  XML file carries a modification notice; original copyright notices remain.
- BinaryDictionaryGetter: external dictionary discovery disabled. DictionaryInfoUtils
  retains its filename convention without depending on the excluded update service.
- InputView and EmojiPalettesView: superclass inflation callbacks restored.
- AccessibilityUtils: platform announcement constant used for SDK compatibility.
- RichInputMethodManager and SettingsValues: external voice shortcut discovery and
  the corresponding voice key disabled until Utterleaf voice integration.
- KeyboardTheme: dark default, explicit light choice and public preference-key
  adapter for the owned comfort settings.
- LatinIME and InputLogicHandler: editor-session identities guard worker completion
  and final suggestion/gesture UI delivery. Lifecycle changes cancel scoped editor
  work; reset clears batch state. Explicit gesture cancellation renews an active
  identity under the batch lock. Native decoding is not performed under the gate.
- LatinIME: dictionary availability callbacks now arrive on main after facilitator
  generation validation rather than mutating the view from its loading worker.
- LatinIME, InputLogic and InputLogicHandler: owner-thread request capture replaces
  worker reads of live editor/composer state; background batch updates copy pointers
  and recheck sessions before capture. Fallback inputs are captured before dispatch.
  Recorrection indicator clearing is deferred to session-checked UI delivery.
- Suggest: consumes the owned Kotlin SuggestionComposerSnapshot and a captured
  correction threshold instead of a live WordComposer. NgramContext.snapshot detaches
  mutable context words/arrays.
- BinaryDictionary and ProximityInfo: owned Kotlin native-operation admission
  defers terminal disposal while an admitted operation uses native resources.
  Dictionary operations serialize without waiting; internal flush/reopen preserves
  admission state. ExpandableBinaryDictionary handles an unavailable debug header.
- WordComposer: full reset detaches pointer arrays; gesture text replacement keeps
  the active path. InputLogic, InputLogicHandler, RichInputConnection and
  RecapitalizeStatus release local editor caches and queued work on teardown.
- LatinIME and InputLogic: subtype changes renew decoder identity and restore the
  active editor cache from current selection; inactive callbacks avoid editor reads.
- SuggestionStripView, MoreSuggestions, MoreSuggestionsView and MoreKeysKeyboardView:
  terminal cleanup releases reusable suggestion labels, builder keys, hover delegate
  and drawing caches. AccessibilityUtils releases autocorrection word references;
  lifecycle boundaries invoke these local-only helpers.
- GestureFloatingTextDrawingPreview: dismissal and deallocation release cached
  suggestions even when preview display has been disabled.
- Native BinaryDictionary JNI and jni_data_utils.h: bounded suggestion array/context
  validation, checked context construction with exception propagation, and heap
  coordinate copies. Oversized gesture requests are rejected whole under an explicit
  4,096-point resource policy. Other JNI/parser hardening remains open.
- Native Suggest: missing traversal/scoring/weighting policy returns unavailable
  before decoding. No gesture policy is linked in this foundation, and no replacement
  gesture implementation has been imported.
- Native BinaryDictionary JNI: fixed-capacity word copies reject malformed inputs
  before native access; stored words remain limited to 48 codepoints, while exact
  matching retains capacity for 96-codepoint normalized queries. Beginning-of-sentence
  marker insertion checks remaining capacity. Property outputs validate fixed array
  shapes and list receivers before writing. JniDataUtils property serialization stops
  on pending exceptions and releases temporary references.
- BinaryDictionary, ExpandableBinaryDictionary and the registered bulk input-event
  JNI entry point: legacy Sketch bulk personalization is explicitly unavailable,
  raising UnsupportedOperationException before native access, reload, queuing or
  mutation. This avoids the inherited missing-field ABI mismatch and unsafe event
  parsing. Method signatures remain; explicit single-entry dictionary operations
  are separate and retain their existing behavior.
- Native header JNI and JniDataUtils: metadata uses bounded Unicode scalar copies
  rather than signed modified-UTF-8 bytes. Malformed strings and oversized attribute
  collections are rejected before creation. Both shared metadata-creation callers
  stop on pending exceptions. Header output validates receivers and snapshots data
  before overridable Java callbacks, with exception-safe temporary references.
  HeaderReadWriteUtils parses numeric attributes using ASCII digits and checked
  integer accumulation, preserving valid integer endpoints and default fallback.
- Native dictionary path entry points: bounded standard UTF-8 conversion matches
  Java File names, including supplementary Unicode; malformed/oversized paths and
  unrepresentable offset/length arguments are rejected without truncation. The
  dictionary policy factory rejects truncated derived header paths. MmappedBuffer
  checks regular-file ranges against fstat on the opened descriptor and bounds
  alignment arithmetic; FileUtils rejects file sizes that cannot fit its int API.
  Concurrent external file truncation remains separate work.
- BinaryDictionary production format migration now returns unavailable before
  changing its owner or files, pending a recoverable replacement transaction.
  The private native candidate-copy helper checks flush failures, retains policy
  ownership with RAII and handles empty iteration. ExpandableBinaryDictionary
  preserves existing files after invalid-format, migration, corruption and
  automatic rebuild failures. Blocked owners reject queued reads, mutations and
  flushes; identity-checked retirement cannot close a replacement. Explicit clear
  remains separate from automatic recovery. Safe production migration is unfinished.
- Native v402/v403 persistence uses an owned transaction helper with nonwaiting
  directory locking, retained generation identities, bounded recognized staging
  files, checked file/directory synchronization and atomic exchange/no-replace
  publication. There is no delete-then-rename fallback. Failed admitted writes
  quarantine uncertain owners; Java opens a replacement before releasing old
  resources. Debug-only fault hooks support synthetic failure/process-death tests.
  Unsupported storage operations return unavailable; post-publication failure can
  expose the new complete generation while retaining the old staged generation.
- InputLogic selection callbacks: inactive sessions return without reacquiring editor
  context; unexpected cursor/selection changes retire old-caret requests and local
  previews before existing cursor handling. Expected IME updates preserve identity,
  and inside-word movement preserves composition. LatinIME exposes its existing
  local transient-state retirement helper to this boundary.
- Native normalized scoring validates JNI arrays and codepoint ranges, uses checked
  heap buffers and three edit-distance rows, and returns a conservative unavailable
  score beyond explicit 4,096-codepoint / 1,048,576-cell work limits. Java preflight
  avoids oversized temporary arrays. Existing Unicode and adjacent-transposition
  scoring semantics are retained within those bounds. Native statistics queries
  preserve the four existing command names using bounded conversion and output.
- CharUtils base-character lookup checks the lower bound before table indexing.
  Exact-match JNI queries reject invalid codepoints while retaining Unicode,
  existing surrogate semantics and a single supported leading sentence marker.
- Stored word/context JNI inputs reject malformed codepoints and the native U+001F
  serialized-string terminator before mutation. Header metadata also rejects U+001F
  before creation to prevent silent prefix serialization. Decoder padding has a
  separate contract and is not changed by these stored-string checks.
- DicTraverseSession JNI initialization uses bounded previous-word storage and
  validates the declared prefix and dictionary availability before binding a
  session. Unsupported suggestion context returns no results without decoding an
  empty fallback context or throwing for ordinary unrepresentable editor text.
- LatinIME and InputLogic: finish without an input view retires local caches and
  queued work; a retired-state marker forces setup past equivalent-editor callback
  coalescing on the next start-view.
- BinaryDictionary, Dictionary/Collection, ExpandableBinaryDictionary and the
  facilitator interface/implementation: local session retirement forwards to safe
  native traversal-cache cleanup without removing dictionary entries or files.
  ComposedData exposes request validity; owned Kotlin snapshot carriers preserve
  owner-captured identity for checking after native admission. LatinIME dispatches
  retirement after session transitions and cancellation.
- LatinIME: superclass finish callbacks run at the public framework boundary rather
  than after connection replacement; deferred finish-view bookkeeping does not call
  the editor or clear new local composition. InputLogicHandler and LatinIME remove
  retired UI result payloads while preserving separately scheduled startup work.
- LatinIME and KeyboardSwitcher: changed height/theme geometry reloads on same-field
  restart; feedback refreshes from current settings. Ordinary unchanged restarts
  retain the existing lightweight path.
- LatinIME: editor and touchable insets use the visible keyboard's window position
  so system navigation and user comfort padding do not hide the upper keyboard
  from the editor or its touch region. Owned Kotlin reserves navigation spacing.
- Four tablet XML key resources also supply base fallbacks: key_settings,
  key_space_3kw, key_space_7kw and keys_exclamation_question; notices retained.
- excluded-sources.txt defines source omitted from compilation, including obsolete
  setup/settings UI, dictionary downloads/providers and spellchecker services.
  Imported originals remain available for provenance. The build also excludes
  obsolete setup/download resources.

The application's manifest and Kotlin entry points are supplied separately by
Utterleaf. The placeholder raw empty resource is not a dictionary; its upstream
provider is not registered. No binary dictionary/model is shipped in this experiment.
This inventory is not a completed privacy audit or approval for public release.
