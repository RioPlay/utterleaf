# Utterleaf Android keyboard product specification

[Mobile roadmap](mobile-roadmap.md) · [Capability gates](android-keyboard-capabilities.md) ·
[Foundation decision](android-keyboard-foundation-decision.md) · [Active rebuild](plans/active/android-keyboard-rebuild.md)

Decision date: September 12, 2026. Build a complete independent Android keyboard
that people can choose for everyday comfort, accuracy and control as well as
security and privacy. Design, accessibility, reliability and performance are
acceptance requirements throughout development. The breadth of FUTO's useful
features is a benchmark; Utterleaf owns its implementation and visual identity.
This specification describes the target. The roadmap records what actually works
and where it has been verified.

## Product standard

The core loop is **type → notice → repair → continue**. Switching to speech,
another language or a power layout must preserve that loop. A feature is not
finished until its default, visible feedback, cancellation, recovery, settings and
accessibility behavior work together. Visual polish includes typography, contrast,
spacing and state clarity; it also includes keeping controls stable under a thumb.

Security first and privacy second constrain implementation. They do not justify
awkward setup, weak correction or a neglected interface. Conversely, a requested
convenience does not authorize passive recording, typing collection, unchecked
model loading or background clipboard retention. Offer a useful explicit action
when that satisfies the underlying need safely.

"Best" is an ambition to test, not a release claim. Measure completed tasks,
remaining errors, repair effort, comfort and responsiveness on named phones and
languages. No keyboard is universally optimal for every hand, script and access
method. Useful customization should accommodate those differences without making
the first-run experience a configuration project.

## FUTO capability baseline

Reviewed September 12, 2026 against official documentation and the versioned
[0.1.30 release](https://github.com/futo-org/android-keyboard/releases/tag/0.1.30).
These are documented capabilities, not comparative test results. Undated settings
pages can lag releases: the theme page still describes custom themes as future
work, while 0.1.30 includes advanced theme import. Versioned release evidence takes
precedence for shipped status.

| Area | Documented reference | Utterleaf target and boundary |
| --- | --- | --- |
| Everyday typing | [Typing settings](https://docs.keyboard.futo.tech/settings/keyboardtyping): correction, suggestions, capitalization, spacing, number/arrows rows, key hints and timing | Dependable tap input first; independently configurable assistance and feedback, stable utility positions and readable labels |
| Touch and repair | [Spacebar](https://docs.keyboard.futo.tech/gestures/spacebar), [backspace](https://docs.keyboard.futo.tech/gestures/backspace), [symbol gesture](https://docs.keyboard.futo.tech/gestures/123) | Accurate cursor/selection gestures with visible alternatives; cancellation must not insert an unintended character or leave deletion running |
| Actions and reach | [Action assignment](https://docs.keyboard.futo.tech/actions/assigningactions), [supported actions](https://docs.keyboard.futo.tech/actions/supportedactions): editable toolbar, emoji, clipboard, editing, one-hand/split/floating modes | A calm default, reachable Edit/Voice/language/emoji, later configurable shortcuts and geometry; editor actions require named host evidence |
| Languages | [Languages/models](https://docs.keyboard.futo.tech/settings/languagesmodels): per-language resources and multilingual correction/swipe | Separate layout, dictionary, composition, prediction, swipe and speech coverage; switching and mixed-language repair must be tested independently |
| Correction and prediction | [Prediction controls](https://docs.keyboard.futo.tech/settings/textprediction): correction thresholds, English transformer, blacklist and personalized suggestions | Suggestions and replacement have separate switches; immediate restoration; explicit inspectable vocabulary; no passive collection of typed communication |
| Swipe | [0.1.29 release](https://github.com/futo-org/android-keyboard/releases/tag/0.1.29): new decoder and alternative swipe candidates | Reviewed engine/data, low-latency local decoding, visible alternatives and recovery for names; preserve accurate tap input and gesture separation |
| Speech | [Voice settings](https://docs.keyboard.futo.tech/settings/voiceinput): offline recognition, microphone options and optional silence stop | Local capture, review/edit/insert, explicit start/stop/cancel; only verified models; interruption recovery and phone measurements precede longer takes or optional endpoint detection |
| Appearance and layouts | [0.1.30 themes](https://github.com/futo-org/android-keyboard/releases/tag/0.1.30), [custom layouts](https://docs.keyboard.futo.tech/settings/customlayouts) | Coherent light/dark themes, meaningful size and reach controls; later bounded data-only layouts/themes with preview, validation and rollback |

FUTO identifies its project as a modified LatinIME fork in its
[official README](https://github.com/futo-org/android-keyboard). Its
[privacy policy](https://keyboard.futo.tech/privacy), updated June 19, 2024,
describes no network permission alongside browser-mediated acquisition and optional
emailed crash reports that may contain typing or dictionary data. These are vendor
disclosures, not an independent audit. Utterleaf will keep diagnostics free of raw
input and handle each export or external action as a separate data path.

Feature parity means meeting useful user tasks. It does not require matching
automatic clipboard history, passive personalization, arbitrary imports, cloud
services, external voice providers or another product's licensing/asset choices.

## Interaction design

| Surface | Required experience | Failure and recovery |
| --- | --- | --- |
| First run | Enable → select → type; microphone/model setup is optional and visibly separate. Show a usable preview and a clear practice action | Denied microphone permission or missing resources leaves typing ready; status explains the missing optional capability |
| Daily | Familiar staggered rows, broad Space, stable punctuation/Delete/Enter, compact actions; no decorative prediction placeholder | Pressed feedback is immediate. Cancelled touches produce no late input. Ordinary two-thumb overlap must not silently drop letters |
| Edit | Selection state, arrows, select all, copy/cut/paste and supported undo/redo; one action returns to letters | A refused action reports unavailability without speculative retries. Paste never submits a form or terminal command |
| Correction | Original spelling remains available; intentional names, negation, numbers, URLs and code are protected | Restore is visible after replacement; reject once without repeatedly forcing the same correction. Caret/field changes invalidate stale replacements |
| Languages and emoji | Visible language switching, local emoji search and tap-accessible alternates; preserve text when switching | Missing dictionary/model is explicit. An alphabetic layout is not advertised as complex-script composition support |
| Voice | Reachable start, visible recording/processing/review states, stop/cancel and local editing before insert | Field loss/hide cancels; no automatic restart. A failed insert retains a safe review/retry path only while the original session remains valid |
| Terminal | Deliberate literal mode, visible modifiers, Esc/Tab/arrows and a replacing Fn layer | Balance and clear local modifiers; never send cleanup to a new field, reinterpret refused chords as letters or automatically submit |
| Settings | Group Typing & correction, Layout & touch, Languages & voice, Privacy & data, Advanced input. Explain consequences next to controls | Save/reopen/restart persists explicit preferences; cancellation is predictable; Reset to defaults restores preferences without deleting models or vocabulary |

Daily typing should not gain another permanently stacked toolbar for every new
feature. Reserve one compact action area; suggestions appear only when implemented
and enabled. Detailed editing, emoji and resource management use purposeful panels.
Any toolbar customization must preserve an obvious route back to typing, keyboard
switching and settings. Common tasks must not require traversing nested menus.

Use consistent key shapes, label baselines and spacing. Test both themes, portrait,
landscape, smallest supported width, large fonts and system insets. Key height and
label size are independent. More vertical padding does not solve narrow touch
targets. One-hand alignment is a near-term ergonomic feature; split/floating modes
follow their own phone/tablet and accessibility evidence. None should wait for a
prediction model merely because it is listed later in a feature taxonomy.

Press, hold, preview, selection, cancellation, disabled and error states belong in
design review. Gestures have tap-accessible alternatives. A custom renderer, if
introduced, must retain individual actionable accessibility nodes and meaningful
states; native buttons alone also do not establish TalkBack typing usability.
See [Android custom-view accessibility](https://developer.android.com/guide/topics/ui/accessibility/views/custom-views).

## Independent architecture

Evolve the existing Kotlin/Public Android SDK application in small reviewable
changes. Keep desktop dependencies, tests and releases separate. Keep working
speech import and session protections while replacing weaknesses in input handling.
Do not rewrite native speech or introduce a second UI runtime to restyle keys.

| Boundary | Responsibility | Invariant |
| --- | --- | --- |
| Layout and presentation | Declarative geometry, labels, themes and accessible actions | Stable geometry during a touch; no editor text in persisted layout data |
| Pointer/gesture state | Pointer identity, overlap, hold/cancel and gesture arbitration | Bounded transient state; deterministic event order; no passive trajectories or adaptive heatmaps |
| Editor session | Text, composition, selection, editor actions and terminal dispatch | Current connection generation authorizes every operation; no blind cross-field retries |
| Language services | Reviewed dictionaries, composing state, suggestions, correction and later swipe | Off UI thread when expensive; bounded documented context; stale results rejected and context cleared |
| Speech | Capture ownership, verified models, cancellation and local review | Explicit capture only; generation isolation and field checks remain authoritative |
| Preferences/resources | Local choices and verified data imports | Reset preserves user data; imports are bounded and atomic; no arbitrary executable add-ons |

These are responsibility boundaries, not a demand to create six frameworks or
general plugin systems. Extract a module when a concrete behavior needs the
boundary and tests can demonstrate its value. Profile before replacing rendering
or introducing native code for ordinary key dispatch.

## Quality gates for every increment

| Gate | Required evidence |
| --- | --- |
| Correctness | Deterministic rapid/repeated/overlapping action traces; selected text, Unicode sequences, Enter flags and rejected editor actions; zero duplicate or wrong-field commits in the named cases |
| Interaction | Complete first-run, type/repair, language switch, voice cancellation, settings save and reset tasks; record task failures, repair actions and participant difficulty |
| Visual design | Review actual live-IME captures and settings previews across width, orientation, theme and large labels; no clipped essential actions, moving utility keys or unexplained mode state |
| Accessibility | TalkBack, Switch Access and external-input workflows with participating users; gesture alternatives, focus order and useful announcements without unexpected private-content speech |
| Performance | Record build/OS/device/language, cold and warm startup, dispatch p50/p95, frame stalls, peak/idle RAM, battery and sustained heat; initial ordinary-dispatch target p95 ≤50 ms on named midrange hardware |
| Privacy/security | Review data flow, manifest, imports, diagnostics and storage; verify no passive input retention, stale callback delivery or hidden network/capture path |
| Resources/updates | Typing remains usable without optional models; malformed import rollback; signed upgrade preserves preferences and models; reset and deletion are separate actions |

Compare with a participant's familiar keyboard using the same phone, tasks,
language and stated practice period. Measure correction harm and recovery as well
as speed; a higher suggestion acceptance rate is not proof of better writing.
Benchmarks must use synthetic/public fixtures or consented local sessions, never
everyday keystroke telemetry. Emulator checks are regression evidence, not measured
phone comfort or accessibility acceptance.

Community evidence and prioritization are recorded below as scenarios, not market
share estimates. The existing [research report](mobile-keyboard-research.md) and
[reported needs](mobile-keyboard-hybrid.md#evidence-from-reported-needs) remain
supporting inputs; their historical issue status is not current defect status.

## Community evidence and resulting priorities

These original discussions were reviewed September 12, 2026. They are a purposive
sample across privacy communities, general Android users and project trackers,
not a survey. Reports establish requested tasks and perceived friction; they do
not independently verify defects or security claims. Prioritize repeated task
friction and severity, then validate it with users, rather than ranking features
by thread votes.

| Direct evidence and date | Need | Design/acceptance consequence |
| --- | --- | --- |
| [FUTO #2038](https://github.com/futo-org/android-keyboard/pull/2038), May–June 2026 | Restore a wrong correction after beginning the next word | Keep repair available within bounded session state. [0.1.29.1](https://github.com/futo-org/android-keyboard/releases/tag/0.1.29.1) already remembers recent alternatives: this is a reference capability, not an unresolved competitor gap |
| [HeliBoard #2513](https://github.com/HeliBorg/HeliBoard/issues/2513), May 25, 2026 | Arabic bottom-row letters feel misplaced because of Backspace width | Review geometry per language; test familiar layouts and touch-error locations before adding utility width |
| [HeliBoard #2467](https://github.com/HeliBorg/HeliBoard/discussions/2467), April 22, 2026 | Readable secondary hints, fewer accidental number-row taps and useful deletion units | Independent hint/label sizing and preview; distinguish grapheme, word and URL-segment deletion |
| [Unexpected Keyboard #1358](https://github.com/Julow/Unexpected-Keyboard/issues/1358), July 5, 2026 | User objects to new Internet permission | Preserve permission continuity and explain resource acquisition. The report does not prove that input was collected |
| [r/Android swipe update discussion](https://www.reddit.com/r/Android/comments/1ue0fzq/futo_keyboard_swipe_update/), June–July 2026 | Mixed experiences with swipe, contractions, capitals, language switching and dictionary setup | Test mixed tap/swipe repair by language; clearly show resource readiness. Positive and negative comments both matter |
| [r/fossdroid keyboard discussion](https://www.reddit.com/r/fossdroid/comments/1w0rdaj/a_good_android_keyboard_i_wanna_share/), August 28–31, 2026 | Text expansion and familiar appearance attract interest; weak word suggestions discourage use | Deliberately created snippets and polished design are valuable; neither compensates for unreliable everyday words |
| [r/degoogle keyboard requirements](https://www.reddit.com/r/degoogle/comments/1w1380l/which_keyboard_should_i_switch_to/), August 28, 2026 | Offline/no-retention typing plus multiple languages, layout control, emoticons and paste tools | Privacy and rich UX belong together. Explicit snippets, local emoji and paste can serve this need without automatic history |
| [r/degoogle AZERTY layout report](https://www.reddit.com/r/degoogle/comments/1usyvbm/futo_keyboard_layout_problem/), July 10–11, 2026 | Familiar typing disrupted by a dedicated apostrophe shifting a letter | Offer reviewed familiar variants and practice. The author describes muscle memory, not an implementation defect |
| [r/GalaxyFold comfort discussion](https://www.reddit.com/r/GalaxyFold/comments/1vcssql/make_your_keyboard_comfortable_not_ai/), August 1, 2026 | Discoverable one-hand resizing/alignment; other participants prefer wider keys | Width, height and alignment have different purposes; test posture and orientation rather than assuming one small layout fits everyone |
| [r/androidapps gesture request](https://www.reddit.com/r/androidapps/comments/1i93abg/keyboard_with_swipe_right_for_space/), January 24, 2025 | Optional space/delete/undo gestures and reliable repair in search fields | Keep visible equivalents and named editor tests. The reported repair issue was inconsistent and is not a confirmed current defect |
| [HeliBoard #2068](https://github.com/HeliBorg/HeliBoard/issues/2068), November 4, 2025 | Repeated form filling loses the chosen tool panel | Preserve a safe UI mode while rebinding insertions to each editor. [3.6-beta1](https://github.com/HeliBorg/HeliBoard/discussions/2100) addresses upstream panel continuity; this does not justify retaining clipboard content |
| [GrapheneOS keyboard discussion](https://discuss.grapheneos.org/d/29613-hello-g-board-bye-futo), December 2025–August 2026 | Privacy-minded users still require good typing/voice accuracy; experiences vary by language/accent | Compare completed tasks on named devices/languages. [Later replies](https://discuss.grapheneos.org/d/29613-hello-g-board-bye-futo/53) praise newer swipe behavior, so early complaints cannot describe every current release |

This pass found no new verifiable original X post to add. Previously documented X
examples remain in the historical research; they are not independent confirmations
of these findings. Screen-reader and split-keyboard users are underrepresented in
this sample. Recruit their participation before describing those workflows as
validated. No community messages were sent.

The resulting order is reliable entry and recovery, comfortable and discoverable
design, honest language support, safe productivity tools, then measured prediction
and swipe. Ergonomic and visual work proceeds alongside foundation work; it is
not deferred until every language feature exists. The milestone dependencies in
the active plan express engineering prerequisites, not the value of each user need.
