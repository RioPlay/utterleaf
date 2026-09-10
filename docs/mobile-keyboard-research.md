# What makes a mobile keyboard good

A good mobile keyboard lets people express exactly what they mean, repair mistakes easily, and continue working without thinking about the keyboard. It must also deserve access to highly sensitive input. For Utterleaf, the product order should be **security, privacy, dependable typing and accessibility, then optional convenience**. A faster benchmark cannot compensate for inserting text into the wrong field, changing a person's meaning, or excluding their access method.

This report examines Android and iPhone keyboards, empirical text-entry research, official accessibility guidance, and documented product behavior. It translates that evidence into requirements for Utterleaf. The product and implementation review is dated September 9, 2026; older studies are identified explicitly. Recommendations and proposed acceptance criteria are analytical judgments, not claims of measured Utterleaf performance or feature popularity.

## Principal findings

The strongest conclusion is that keyboard quality is a complete interaction loop: aiming, entering, understanding feedback, noticing mistakes, correcting them, and continuing. Word prediction, swipe input and speech can reduce effort, but their value depends on recognition quality, attention cost, language, task and access method. Counting features or counting saved taps is insufficient.[^1][^2][^4][^5]

Utterleaf should aim for a familiar everyday keyboard with an optional, clearly separated power layout. That is a better fit for its goals than placing every capability on the default screen. The everyday surface should prioritize letters, punctuation, Space, Delete, the appropriate Enter action, language switching and voice. Editing and terminal tools should remain discoverable without competing with these actions.

The largest current gaps are not mascot placement or additional themes. They are independently verified editing behavior, accessible typing, alternate characters, correction and language support. The existing Android alpha05 has a useful foundation, but its status strip is not a prediction engine, and its terminal key dispatcher is not proof of compatibility with every terminal. The [capability plan](android-keyboard-capabilities.md) records that distinction.

## Evidence and its limits

There is useful research on mechanisms, but no credible basis here for a universal ranking of keyboards or a claim that a particular percentage of all users wants a feature. Official product documentation establishes advertised behavior, not comparative quality. Screenshots establish visual arrangements, not touch accuracy, privacy enforcement or accessibility.

| Evidence | Finding relevant to design | Important limit |
| --- | --- | --- |
| Palin and colleagues, MobileHCI 2019: 37,370 mobile transcription participants | Mean entry speed was 36.2 words per minute with 2.3% uncorrected errors. Autocorrect use associated with faster entry; explicit prediction use associated with slower entry. | Self-selected volunteers, English copying, varied devices and self-reported techniques. Associations are not causal effects; these averages are not release targets.[^1] |
| Quinn and Zhai, CHI 2016: 17 experienced mobile typists | More assertive suggestions saved taps and were preferred, but reduced average entry performance in the experiment. | Old iPod hardware and deliberately ignored incorrect taps isolated completion interaction. This does not show that modern autocorrect is harmful.[^2] |
| Bi, Li and Zhai, CHI 2013: finger targeting experiments | Finger-touch uncertainty matters alongside movement difficulty. The keyboard experiment analyzed 11 participants. | Controlled index-finger tasks and masked feedback do not establish an ideal modern thumb-keyboard size.[^3] |
| Vertanen and colleagues, CHI 2015: experimental sentence decoding | Sentence-based decoding reduced character errors in the experiment; intermediate visual feedback did not significantly change entry or error rates. | Historical comparison, small convenience sample and server-based research decoding do not establish current offline phone performance.[^4] |
| Zhai and Kristensson, CACM 2012: gesture-keyboard research synthesis | Gesture entry combines recognition, language information and learned movement. | Practice, vocabulary and task strongly affect results; rehearsed ceiling speeds are not everyday composition speeds.[^5] |

These findings support contemporary, matched comparisons with a person's familiar keyboard. They also support measuring preference and effort separately from speed. Someone using switch scanning, dealing with fatigue, or spelling an unfamiliar name may rationally value fewer physical actions or more explicit control over the fastest average result.

## Everyday typing and correction

### Accurate, predictable input

The first requirement is literal correctness: the intended character arrives once, in order, in the intended editor. The keyboard must preserve selection, handle lifecycle changes, and distinguish text entry from commands. Android exposes separate text, composition and editor-action mechanisms; raw key events are not a universal substitute for ordinary text insertion.[^14][^15]

For Utterleaf, this means testing ordinary messages alongside URLs, email addresses, numbers, passwords, code, accented names, repeated letters and punctuation. A correction system that performs well on common English sentences can still damage a domain name or remove a negation. These cases belong in acceptance testing before a smart feature becomes a default.

Feedback should be immediate and restrained. A pressed state makes contact visible; optional haptics can reinforce it. Feedback must not wait for a language model. Sound, vibration and key previews need independent controls, and sensitive fields should not expose characters through enlarged previews or inappropriate announcements. Avoid ambient animations and moving controls during typing.

### Correction must preserve agency

Suggestions and automatic replacement are separate features and should have separate settings. Suggestions offer alternatives; autocorrection changes text. Users need to know when a replacement happened and have an immediate, understandable way to restore the original. Rejecting a correction should not trigger the same replacement repeatedly in the same edit.

The proposed initial correction policy is conservative: operate only within a valid composing range, preserve literal entry for code and terminal modes, and suppress learning in sensitive contexts. User-added vocabulary should be explicit, inspectable and erasable. Any later automatic learning should be off by default and have clear retention and deletion behavior.

Prediction must earn its attention and screen space. The research distinguishes fewer taps from faster completion; looking up, reading options and returning to the keys has a cost.[^2] Test the same tasks with prediction enabled and disabled. Report harmful replacements, repair effort and user preference rather than presenting suggestion acceptance as proof of improvement.

### Editing is a primary feature

Cursor positioning, selection, deletion and correction deserve the same attention as entering new words. Provide visible editing controls as alternatives to spacebar swipes and other gestures. Keep common punctuation in stable locations across letter and symbol layers. Secondary hints can improve discovery, but should not make primary labels harder to read.

Unicode handling requires explicit tests: deleting an emoji sequence, moving around a combining accent and replacing selected text are different from manipulating simple ASCII. Undo should have a defined contract with the host editor. If an action is unsupported, a refusal is safer than blindly sending another operation that may delete or submit unrelated text.

## Layout, customization and visual quality

Familiar geometry is a sensible starting point for reducing relearning when changing keyboards. FUTO's letter and symbol arrangements illustrate a useful hierarchy: stable typing rows, recognizable utility positions, secondary symbols, and compact upper controls. That is a product reference for independent design, not evidence that copying its appearance would reproduce its behavior.[^16]

Utterleaf should keep a calm default and offer a few purposeful adjustments: independent height and label size, optional number row, reachable left/right alignment, restrained themes, feedback controls and accessible timing. More specialized split, floating and terminal layouts can follow demonstrated demand and device testing. Reset controls should restore a known layout without unexpectedly removing models or vocabulary.

General Android accessibility guidance recommends approximately 48 by 48 dp touch targets. This is useful for settings and ordinary toolbar controls, but ten nonoverlapping 48 dp keys cannot fit across a 320 dp viewport. Increasing key height alone does not fix narrow columns. Document the dense keyboard compromise, measure actual hit areas, offer alternatives, and test errors; do not invent an accessibility exemption or overlap hit regions ambiguously.[^6]

WCAG's web target-size criterion uses CSS pixels and includes specific conditions and exceptions. It is useful supporting guidance, but CSS pixels, Android dp and physical measurements should not be treated as interchangeable certification units for a native keyboard.[^13] Visual keycaps and effective touch areas should be reviewed separately.

Professional visual quality comes from consistency: readable labels, stable baselines, clear active modifiers, appropriate contrast, coherent spacing, and enough room to see the text being edited. Dark mode can remain Utterleaf's default, with a well-tested light option. Branding belongs in setup, empty states and help; the typing surface should not animate mascots or reserve a large decorative area while someone is composing.

## Accessibility as a release requirement

Accessibility is not one large-key setting. Blind users, people with low vision, motor impairments, fatigue, cognitive differences and speech impairments use different combinations of input and feedback. A gesture that helps one person may exclude another. Provide equivalent selectable actions for essential holds, swipes and chords.

Google describes Gboard's TalkBack interaction as exploring letters by touch and lifting to choose them, with some utility actions requiring double-tapping. It explicitly warns that other keyboards may not be compatible. Native buttons with descriptions therefore do not establish equivalent keyboard usability.[^7]

Apple documents multiple VoiceOver typing modes, including standard, touch and Direct Touch typing, as well as insertion-point navigation.[^9] An iOS implementation needs its own acceptance evidence; successful Android accessibility testing cannot establish it. Both platforms require checking focus and announcements when the keyboard changes modes, opens a picker, or reports a voice error.

| Access need | Proposed Utterleaf behavior | Required evidence |
| --- | --- | --- |
| Screen-reader typing | Meaningful key names and modifier states; discoverable symbols; correct activation; accessible keyboard switch | Complete enter, repair, submit and switch-away workflows with TalkBack; separately with VoiceOver if iOS ships.[^7][^8][^9] |
| Switch scanning | Stable actionable order; no hidden focusable controls; selectable alternatives to gestures | Repeated letters, deletion, correction and submission through scanning. Count scan effort separately from touch speed.[^8][^10] |
| Tremor or limited dexterity | Adjustable size and timing; deliberate delete repeat; gesture cancellation; avoid mandatory holds | Tests under representative touch accommodations, including legitimate repeated letters and release during deletion.[^11] |
| Low vision | Independent label scaling, clear contrast and state indicators, useful layout choices | Smallest supported width and largest labels in both themes and orientations; no clipped essential controls |
| Braille users | Easy switching to system braille input and back without losing editor state | Test actual switching; do not advertise a braille implementation or physical-display support without separate evidence.[^12] |
| Speech limitations or noisy surroundings | Full ordinary typing without microphone permission or a speech model | Complete setup and everyday editing with voice unavailable |

Utterleaf's current repeat guard warrants particular scrutiny. A fixed interval can suppress an accidental duplicate but also reject intentional repeated letters. Make the tradeoff clear and evaluate it with the people it is intended to help. Developer simulation and automated accessibility checks are necessary technical checks; they do not replace participation by experienced assistive-technology users.[^8][^11]

## Languages, prediction and gesture input

A language label should describe a real capability. Layout, accented characters, dictionary, autocorrection, prediction, script composition and speech recognition are separate dimensions. Offering a character map is not equivalent to supporting Japanese conversion, an Indic composing sequence or fluent mixed-language input. Publish those dimensions separately rather than showing one undifferentiated supported-language count.

For Utterleaf, first complete an explicit alphabetic language set with reviewed layouts and alternate characters. Then add correction and dictionaries with documented provenance. Complex scripts require a suitable composition engine and native-speaker review. Test language switching mid-sentence, names outside dictionaries, mixed RTL/LTR text and punctuation conventions before broad claims.

Gesture typing is a valuable optional input method, but it requires more than drawing a trail. Recognition, vocabulary coverage, candidate recovery and practice determine whether it reduces effort.[^5] Keep tap typing available, distinguish word gestures from navigation gestures, and provide recovery for names and out-of-vocabulary words. Offline implementation also needs measured memory, latency and battery costs on supported hardware.

Local models are not automatically suitable models. Evaluate their license, origin, update process, format validation, resource bounds and harmful correction behavior. A large model that stalls the keyboard or exhausts memory is a poor default even if its offline accuracy is higher. Optional resources should never prevent basic typing from starting.

## Security and privacy

A keyboard handles text that may be sensitive even when an app has not marked a field as a password. Security design should cover malicious or buggy editors, stale sessions, imported models and layouts, dependencies, updates, diagnostics and exported components. Treat editor-provided metadata and imported files as untrusted; minimize context access and avoid retaining text unnecessarily.

Utterleaf's Android manifest currently has no Internet permission and disables app backup. These are useful architectural controls, not a complete security assessment. They do not validate native parsers, ensure an exported activity is safe, or prevent an intentionally opened external browser or share action from communicating. Verify release artifacts as well as source configuration. See the [mobile security design](mobile-security.md).

Recommended boundaries are concrete: no typed text or audio in logs; no automatic clipboard collection; no hidden learning; bounded composing context; cancellation of pending work when the editor changes; and no late commit to another field. Signed application updates should preserve a stable identity. Model and layout imports need size limits, format checks, integrity verification, atomic replacement and recovery from failure.

Convenience features should have individual data-flow descriptions. Typing, voice, cloud rewriting, clipboard sync and diagnostic sharing are separate paths even when one product contains all of them. A blanket label such as private, offline or AI-enabled is insufficient to describe these differences. The product comparison below uses documented behavior, not an independent security audit.

## Product references

The table identifies useful documented concepts rather than ranking current binaries. A feature not listed is not necessarily absent. Android-specific features should not be assumed to exist in the corresponding iOS app.

| Reference | Useful documented concepts | Boundary for Utterleaf |
| --- | --- | --- |
| FUTO Keyboard | Resizing, optional number/arrows rows, symbol hints, correction controls, gestures and configurable voice input | Adopt independent interaction requirements and test them. Its privacy policy describes no network permission but also optional external crash-report email and browser-mediated actions.[^16][^17][^18] |
| Gboard | Integrated advanced dictation, punctuation, voice editing and concurrent touch correction on eligible devices | Useful workflow reference, with device/language limits. Local dictation does not imply every editing feature is local.[^19] |
| Microsoft SwiftKey | Local personalization controls and separate account-based services | Distinguish local language data from optional backup/sync and cloud clipboard; provide separate deletion and retention controls.[^20][^21] |
| HeliBoard | Multilingual dictionaries, custom layouts, function/symbol layouts, split and one-handed modes | Its README states no Internet permission; optional glide uses a separately supplied closed-source library. A native add-on is a separate trust and provenance decision.[^22] |
| Hacker's Keyboard | Full modifiers, arrows, compose and Fn-accessed navigation/function controls | The user guide is historical, last edited in 2018. It is a useful power-layout reference, not present-day Android compatibility evidence.[^23] |

Several privacy distinctions deserve explicit treatment. FUTO's June 2024 policy says optional crash-report email can include typing or dictionary data. This illustrates why even user-initiated diagnostics need a readable content preview.[^17] Microsoft's FAQ says passwords may be learned when entered in an ordinary field or when the host fails to identify the field correctly; field metadata cannot identify all secrets.[^20]

Google's advanced-voice documentation distinguishes cloud-backed “Fix it” and detailed edits from newer device-local voice writing tools on eligible Pixel 9-and-later hardware, excluding 9a. For detailed edits, it describes sending the command transcript and full field text, without audio. These are different features and should not be collapsed into one local-or-cloud claim.[^19] Its learning documentation separately discusses federated learning, local personalization and optional audio donation.[^24]

SwiftKey's cloud-clipboard documentation describes account-based transfers and an expiring latest cloud clip. Encryption in transit should not be described as end-to-end encryption without further evidence.[^21] Android's sensitive-clipboard flag suppresses a content preview; it is not encryption or a guarantee that clipboard contents are inaccessible.[^25]

Two public issue reports illustrate acceptance scenarios without establishing prevalence: FUTO #584 reported unwanted correction of romanized Hindi vocabulary and profanity in version 0.1.23.2; HeliBoard #1439 reported Android 15 navigation obscuring keyboard content. Both are historical, closed reports. Their useful lessons are to test personal-dictionary authority and real system insets, not to claim the products still have those defects.[^28][^29]

## Voice, setup and troubleshooting

For a speech-oriented keyboard, a microphone button is only the entry point. A complete workflow explains whether voice is ready, which engine and language will be used, what is being captured, how to stop, and how to repair the result. Keyboard activation, microphone permission and model readiness should be separate states. Ordinary typing must remain available when the model is missing or permission is denied.

Utterleaf should show a recommended compatible model first, with download size and clear speed/quality tradeoffs. Additional choices belong under a concise comparison. Installed, missing, incomplete and unsupported resources need distinct labels and exact recovery actions. A failed import should preserve the previous working model; a successful import should be followed by an optional local test. Current alpha05 provides reviewed tiny.en/base.en/small.en imports, but small.en's actual inference and physical-device performance remain unverified.

During recording, use visible recording/processing states, Stop and Cancel, and elapsed or remaining time whenever a limit applies. A limit should explain a real resource constraint and offer a safe continuation path. Speech output should be editable, and insertion should remain bound to the original valid editor session. Do not turn an ordinary spoken phrase into an irreversible send, terminal submission or unrelated deletion.

Troubleshooting should name the failed step and offer one relevant action: choose another verified model, import a missing resource, review microphone permission, or retry after an interruption. Avoid generic failure dialogs or a page of installation commands when the app can identify the problem. Any support export should default to input-free diagnostics and allow review before sharing.

These are proposed Utterleaf requirements. A popular keyboard's voice command list does not establish that the same commands are safe defaults for Utterleaf, especially in unknown or raw terminal fields.

## Android and iOS boundaries

Android provides a system input-method framework, but receiving editors still differ in their supported operations. Build ordinary text, composition and special-key compatibility separately. Offer switching to another input method without making Utterleaf a trap, and publish actual OS and architecture support rather than promising every phone.[^14][^15]

Current Apple UIKit documentation confirms that secure text and phone/name-phone pad fields use the system keyboard, and host applications can reject custom keyboards. It also requires a switching mechanism. Therefore an iOS Utterleaf keyboard cannot be promised as a universal replacement.[^26]

Apple's archived 2017 extension guide states that custom keyboard extensions cannot access the microphone. The current interface guide's `hasDictationKey` discussion concerns system-button presentation and does not establish microphone permission. A 2026 iOS voice architecture needs current SDK and physical-device validation of capture, containing-app handoff, permissions and extension lifecycle before a seamless in-keyboard speech promise is made.[^26][^27]

Keep mobile and desktop implementation plans separate. Share product principles, terminology, test cases and carefully reviewed portable components where appropriate; do not transplant desktop automation or microphone assumptions into a mobile keyboard. iOS should have its own feasibility and acceptance milestone, not an Android parity checkbox.

## Utterleaf baseline and implementation order

The current reference is published Android alpha05, source revision `f74b862`, rather than an unbuilt mockup. It includes independent staggered English typing, symbols, Shift/Caps, basic cursor and deletion actions, optional numbers and terminal controls, offline speech review, and guided model import. Its language/status strip does not supply suggestions. Its existing emulator and native-inference checks are valuable but do not establish physical-phone accessibility, small.en performance, or general terminal compatibility. [Release and evidence](mobile.md#android-validation--september-9-2026)

<img src="assets/screenshots/android-keyboard-live.png" width="320" alt="Utterleaf alpha05 keyboard in a synthetic editor" />

*Actual alpha05 emulator capture in a synthetic editor. It documents appearance and integration at that point; it is not evidence of comparative typing quality or physical accessibility.*

The following order refines the [capability plan](android-keyboard-capabilities.md). These are proposed milestones, not newly implemented features.

| Order | Deliverable | Completion boundary |
| --- | --- | --- |
| 1 — trust and correctness | Editor-session safety, selected-text replacement, Unicode deletion, Enter behavior, repeat handling, cancel/recovery | No wrong-field edits, duplicate commits, secret retention or unrecoverable text loss in the supported test matrix |
| 2 — accessible everyday keyboard | TalkBack and switch workflows, readable geometry, stable symbols, alternate characters, independent sizing | Representative users can type, repair and leave the keyboard without ordinary touch assistance; publish tested configurations |
| 3 — useful editing and power mode | Selection/copy/cut/explicit paste; safe editor undo where supported; named terminal acceptance | Every displayed action has a documented effect and observed host-app result; unsupported actions fail clearly |
| 4 — language and correction | Reviewed layouts, accents, local vocabulary, conservative reversible correction | Native-speaker tasks and literal strings pass; corrections can be rejected; no implicit learning |
| 5 — prediction and swipe | Evaluated local engines, bounded resources, optional modes | Matched comparisons show worthwhile benefits for the intended users without unacceptable correction or resource regressions |
| 6 — broader ergonomics and iOS | One-handed/split/floating profiles where justified; separately validated iOS design | Each form factor and platform has its own working interaction and accessibility evidence |

Security and accessibility continue through every stage. Some editing, language-resource and design work can proceed in parallel after shared contracts are settled. Later features must not delay repairing basic entry. Avoid treating roadmap completion as a single binary event: a new language, engine or platform creates additional acceptance work.

## Evaluation and release gates

### A fair comparison

Compare Utterleaf with each participant's familiar keyboard on the same device and tasks. Give documented practice, vary test order, and include both copying and original composition. Include correction tasks, names, mixed punctuation, literal strings and sustained use. Recruit across relevant access methods, languages and hand postures rather than reporting only a pooled average.

Do not collect private everyday messages to run this study. Use synthetic prompts, participant-controlled examples and explicitly consented local observations. Report task-level outcomes and distributions without retaining raw text by default. A small pilot can find defects and refine tasks; it cannot establish population superiority.

| Measure | Why it matters | Reporting requirement |
| --- | --- | --- |
| Completion time and entry rate | Captures the full task rather than animation speed | Include repair time; state task and practice; avoid universal WPM targets |
| Remaining errors and correction effort | Fast text can still be wrong or exhausting to repair | Separate errors left behind from errors corrected and actions spent repairing them.[^30] |
| Harmful correction | Detects changes to names, negation, numbers or literal strings | Report the exact synthetic cases, restoration success and repeated unwanted replacements |
| Input latency and responsiveness | Exposes model work blocking ordinary typing | Cold/warm show time and touch-to-dispatch p50/p95 on named phones; measure visible feedback separately |
| Accessibility task completion | Reveals barriers hidden by ordinary touch tests | Record access method, service/OS version, assistance needed and focus failures |
| Memory, battery and heat | Determines whether optional intelligence remains practical | Fixed-duration, repeatable device tests with model/version/settings recorded |
| Trust and recovery | Captures security and installation failures | Wrong-field attempts, sensitive-data inspection, denied permissions, failed imports and upgrade retention |

Before testing, define acceptable regression margins and task priorities. A proposed engineering target already in the capability plan is p95 ordinary key dispatch at or below 50 ms on named midrange hardware; this is a project target, not a research-derived human threshold or an existing measured result. Treat text loss, wrong-field insertion, inaccessible escape paths and credential exposure as blocking failures regardless of average speed.

### Compatibility matrix

Android acceptance should include native EditText and Compose, browser plain and rich editors, messaging, password-manager interaction, and explicitly named terminal clients. Verify selection replacement, Enter versus Send/Next, multiline behavior, app switching, rotation, keyboard hiding, process restart, device lock and interrupted voice sessions. A true return value from an input API does not establish that a terminal performed the intended action.[^15]

Physical coverage should include a lower-resource supported phone as well as the Pixel 8 Pro, multiple screen sizes, navigation modes and at least one additional manufacturer's software. Emulator tests remain useful for deterministic lifecycle and import checks. They cannot establish microphone behavior, typing feel, thermal performance or real assistive-input usability.

Updates need their own acceptance: previous signed version to new version, settings and model preservation, interrupted installation handling, and actual Obtainium behavior. The existence of an APK or a green compilation job is not the same as a usable upgrade.

### Release checklist

Each checked item should link to a dated result with the build, device, OS, language, settings and host app. An untested item remains open; this checklist does not certify alpha05.

- [ ] Enter and repair synthetic messages, names, URLs, repeated letters and Unicode sequences without loss, duplicates or unwanted replacements.
- [ ] Change fields, selections and apps during pending composition or voice work; verify zero stale insertion and prompt capture cancellation.
- [ ] Complete typing, correction, symbol selection, submission and keyboard switching with the supported screen reader and switch input.
- [ ] Review every layer at supported widths, orientations, navigation modes and maximum label size; verify visible and effective key bounds.
- [ ] Exercise sensitive fields, no-learning requests, clipboard actions and diagnostics; inspect storage and logs for unintended input retention.
- [ ] Deny microphone permission, remove a model, interrupt an import and cancel recognition; confirm ordinary typing remains usable and recovery is understandable.
- [ ] Verify every advertised editing and terminal action in named host applications, including explicit unsupported cases.
- [ ] Record matched typing comparisons and physical latency, memory, battery and thermal results before enabling a new prediction or speech default.
- [ ] Install the published signed update through the supported distribution path and verify settings/model preservation.

## Decisions and remaining uncertainty

Utterleaf should compete on dependable local entry and respectful control. Prioritize editing, accessibility and conservative correction; keep power functionality optional; make speech setup understandable; and require evidence before promoting a smart feature to the default. A polished appearance supports that experience but cannot substitute for it.

The available evidence does not determine an ideal suggestion count, universal keyboard height, best decoding engine, or optimal speech model for every phone. It also does not establish current Utterleaf superiority. Those decisions require contemporary device testing and participants, especially for accessibility and non-English input. The report supplies the criteria and implementation order for that work, rather than claiming it has already been completed.

## Sources

Numbered references identify the original research and official documentation used. Living product documentation describes the reviewed behavior and may change; record exact app, OS and assistive-service versions in any subsequent acceptance result.

[^1]: Kseniia Palin, Anna Maria Feit, Sunjun Kim, Per Ola Kristensson and Antti Oulasvirta. *How do People Type on Mobile Devices? Observations from a Study with 37,000 Volunteers.* MobileHCI, 2019. [Original paper](https://aaltodoc.aalto.fi/server/api/core/bitstreams/33fed4e1-6fec-40b5-9352-c248345581f7/content). [DOI](https://doi.org/10.1145/3338286.3340120).
[^2]: Philip Quinn and Shumin Zhai. *A Cost–Benefit Study of Text Entry Suggestion Interaction.* CHI, 2016, pp. 83–88. [Google Research record](https://research.google/pubs/a-costbenefit-study-of-text-entry-suggestion-interaction/); original paper reproduced in Appendix B, PDF pp. 178–183 of [Quinn's thesis](https://ir.canterbury.ac.nz/bitstreams/83330701-f6da-4b5f-aa2d-56344bb81274/download). [DOI](https://doi.org/10.1145/2858036.2858305).
[^3]: Xiaojun Bi, Yang Li and Shumin Zhai. *FFitts Law: Modeling Finger Touch with Fitts' Law.* CHI, 2013, pp. 1363–1372. [Original paper](https://www3.cs.stonybrook.edu/~xiaojun/pdf/FFitts.pdf).
[^4]: Keith Vertanen, Haythem Memmi, Justin Emge, Shyam Reyal and Per Ola Kristensson. *VelociTap: Investigating Fast Mobile Text Entry using Sentence-Based Decoding of Touchscreen Keyboard Input.* CHI, 2015, pp. 659–668. [Original paper](https://www.keithv.com/pub/velocitap/velocitap.pdf).
[^5]: Shumin Zhai and Per Ola Kristensson. *The Word-Gesture Keyboard: Reimagining Keyboard Interaction.* Communications of the ACM 55(9), September 2012, pp. 91–101. [Original article](https://www.pokristensson.com/pubs/ZhaiKristenssonCACM2012.pdf).
[^6]: Google. *Touch target size.* Android Accessibility Help, undated living guidance. [Source](https://support.google.com/accessibility/android/answer/7101858?hl=en).
[^7]: Google. *Navigate your device with TalkBack*, “Edit text with Gboard.” Android Accessibility Help, undated living guidance. [Source](https://support.google.com/accessibility/android/answer/6006598?hl=en).
[^8]: Google. *Test your app's accessibility.* Android Developers, living guidance. [Source](https://developer.android.com/guide/topics/ui/accessibility/testing?hl=en).
[^9]: Apple. *Use the onscreen keyboard with VoiceOver on iPhone.* iPhone User Guide, living guidance. [Source](https://support.apple.com/en-gb/guide/iphone/iph3e2e3d1d/ios).
[^10]: Apple. *Set up and turn on Switch Control on iPhone.* iPhone User Guide, living guidance. [Source](https://support.apple.com/en-ie/guide/iphone/iph400b2f114/ios).
[^11]: Apple. *Adjust how iPhone responds to your touch.* iPhone User Guide, living guidance. [Source](https://support.apple.com/guide/iphone/adjust-how-iphone-responds-to-your-touch-iph77bcdd132/ios).
[^12]: Google. *Use the TalkBack braille keyboard.* Android Accessibility Help, living guidance. [Source](https://support.google.com/accessibility/android/answer/9728765?hl=en). Apple. *Type braille directly on your iPhone, iPad, or iPod touch.* March 18, 2025. [Source](https://support.apple.com/en-us/101637).
[^13]: W3C Web Accessibility Initiative. *Understanding SC 2.5.8: Target Size (Minimum), Level AA.* WCAG 2.2 understanding document, living guidance. [Source](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).
[^14]: Google. *Create an input method.* Android Developers, living documentation. [Source](https://developer.android.com/develop/ui/views/touch-and-input/creating-input-method).
[^15]: Google. *InputConnection.* Android API reference, living documentation. [Source](https://developer.android.com/reference/android/view/inputmethod/InputConnection).
[^16]: FUTO. *Keyboard & Typing.* Undated rolling Android documentation. [Source](https://docs.keyboard.futo.tech/settings/keyboardtyping).
[^17]: FUTO. *FUTO Keyboard Privacy Policy.* Updated June 19, 2024. [Source](https://keyboard.futo.tech/privacy).
[^18]: FUTO. *Voice Input.* Undated rolling Android documentation. [Source](https://docs.keyboard.futo.tech/settings/voiceinput).
[^19]: Google. *Use advanced voice typing features.* Gboard Help, living documentation with feature-specific eligibility. [Source](https://support.google.com/gboard/answer/11197787?hl=en).
[^20]: Microsoft. *Microsoft SwiftKey Keyboard: Privacy Questions and your Data.* Undated living support article. [Source](https://support.microsoft.com/en-us/swiftkey-keyboard/microsoft-swiftkey-keyboard-privacy-questions-and-your-data).
[^21]: Microsoft. *How to use Microsoft SwiftKey Keyboard to copy and paste text between SwiftKey and Windows.* Undated living support article. [Source](https://support.microsoft.com/en-us/swiftkey-keyboard/how-to-use-microsoft-swiftkey-keyboard-to-copy-and-paste-text-between-swiftkey-and-windows).
[^22]: HeliBoard maintainers. *HeliBoard README.* Rolling project documentation, reviewed September 9, 2026; no add-on or binary audit implied. [Source](https://github.com/HeliBorg/HeliBoard).
[^23]: Klaus Weidner and project wiki contributors. *Hacker's Keyboard UsersGuide.* Last edited November 20, 2018. [Source](https://github.com/klausw/hackerskeyboard/wiki/UsersGuide).
[^24]: Google. *Learn how Gboard gets better.* Gboard Help, living documentation. [Source](https://support.google.com/gboard/answer/12373137?hl=en).
[^25]: Google. *Copy and paste.* Android Developers, living documentation. [Source](https://developer.android.com/develop/ui/views/touch-and-input/copy-paste).
[^26]: Apple. *Configuring a custom keyboard interface.* Current UIKit documentation. [Source](https://developer.apple.com/documentation/uikit/configuring-a-custom-keyboard-interface); [official Markdown representation](https://developer.apple.com/documentation/uikit/configuring-a-custom-keyboard-interface.md).
[^27]: Apple. *App Extension Programming Guide: Custom Keyboard.* Archived guide, updated October 19, 2017. Historical evidence only. [Source](https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/CustomKeyboard.html).
[^28]: driftywinds. *Keyboard Ignores Personal Dictionary and Censors Profanity*, FUTO issue #584. October 2, 2024; reported version 0.1.23.2, closed at review. [Original report](https://github.com/futo-org/android-keyboard/issues/584).
[^29]: eranl. *Bottom of keyboard obscured on Android 15*, HeliBoard issue #1439. March 27, 2025; reported commit `a745c92`, closed at review. [Original report](https://github.com/HeliBorg/HeliBoard/issues/1439).
[^30]: R. William Soukoreff and I. Scott MacKenzie. *Metrics for Text Entry Research: An Evaluation of MSD and KSPC, and a New Unified Error Metric.* CHI, 2003, pp. 113–120, abstract. [Author-hosted record](https://www.yorku.ca/mack/chi03.html). [DOI](https://doi.org/10.1145/642611.642632).
