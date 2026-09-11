# Community needs for an Utterleaf keyboard

The strongest product opportunity is a trustworthy everyday keyboard that preserves people's intended words and makes mistakes cheap to repair. Offline speech and terminal tools can distinguish Utterleaf, but they cannot compensate for poor touch accuracy, intrusive correction, inaccessible controls or confusing setup. The recommended hybrid is LatinIME's keyboard foundation, a familiar compact interaction design, and Utterleaf's local speech and deliberate editing tools. Security and privacy are release requirements, not selectable modes of product quality.

This is a research and planning proposal for review, not implementation approval or a statement of released capabilities. Evidence was reviewed September 10, 2026. Android is the primary scope; iOS has separate platform constraints. Keep this report local and uncommitted until publication is explicitly requested.

## Evidence strength and limitations

Community discussions identify unmet needs and useful failure examples; they do not establish market share or universal preference. This report uses nine selected firsthand discussion/issue sources, complemented by product documentation, original text-entry research and security/platform guidance. The sample is purposive, English-accessible and skewed toward enthusiasts, privacy communities and people reporting problems. Votes are not treated as population estimates. No new survey, user interview or comparative device benchmark has been conducted.

Historical reports remain valuable as regression scenarios, but are not proof that another keyboard still has a reported defect. Product documentation establishes available or advertised mechanisms, not comparative quality or an independent security audit. Priorities below are analytical recommendations combining that evidence with Utterleaf's product constraints. They are not a ranked poll of all keyboard users.

## What people actually ask for

| Firsthand evidence | Need revealed | Implication for Utterleaf |
| --- | --- | --- |
| A November 2024 privacy discussion describes difficulty replacing a mainstream keyboard without losing correction, swipe or speech; replies disagree about the best alternative.[^1] | Privacy should not require accepting everyday typing failures. | Evaluate complete tasks, including correction and repair, instead of comparing feature counts. |
| A September 2026 privacy discussion asks for local input without recording messages; respondents value offline voice/swipe but mention adjustment to symbol layouts.[^2] | Trust and familiar muscle memory matter together. | Explain data handling plainly and keep ordinary keys predictable. Claims about vendors in comments are not security evidence. |
| FUTO issue #1227, April 2025, reports repeatedly hitting B instead of Space while typing one-handed.[^3] | A polished layout can still be uncomfortable for a particular hand/device. | Test bottom-row geometry and offer understandable sizing controls; copying exact dimensions is insufficient. |
| HeliBoard discussion #550, March 2024 with 2025 follow-ups, describes German/English typing and difficulty discovering multilingual settings and required dictionaries.[^4] | Mixed-language input and understandable setup are linked. | Distinguish layout availability, dictionary installation and speech-model availability. Avoid hiding configuration behind an apparent toggle label. |
| HeliBoard discussion #885, June 2024, debates editing keys, stable Space/Delete positions and the complexity of configuring functional layouts.[^5] | Power users want efficient editing without repeatedly leaving the keyboard. | Provide a usable Edit/Terminal layout out of the box; custom layout editing should not be required for basic shortcuts. |
| An r/Blind discussion from January 2025 describes touch-and-lift latency and the desire for a different typing interaction.[^6] | Accessibility is about efficient interaction, not merely spoken labels. | Test real TalkBack typing modes and timing. Do not assume a requested iOS interaction is available unchanged on Android. |
| A low-vision developer's April 2022 account describes difficulty seeing keyboard keys and wanting sizing and contrast choices.[^7] | Low vision and complete blindness have different needs. | Provide readable key labels, contrast choices and useful sizing; TalkBack is not the sole accessibility answer. |
| Accessible Android's 2025 report describes difficulty navigating from Gboard to a host app's Send/Submit control.[^8] | Completing the task includes leaving the keyboard. | Include focus exit, host controls and return-to-editing in accessibility acceptance. The report refers to older TalkBack behavior. |
| An August 2026 Android-app discussion praises adjustable correction and voice recognition while describing difficulty with local names.[^9] | Correction preferences and language varieties differ. | Separate correction from suggestions; test names, accents and regional vocabulary, not just common US-English phrases. |

These accounts support a direction, not a promise that one configuration will suit everybody. Additional evidence is still needed from motor-impaired users, switch-access users, less technical users, non-Latin-script communities and people using inexpensive phones.

## Typing quality and correction

A 2019 study of 37,370 volunteers found an average 36.2 words per minute and 2.3% uncorrected errors in a mobile transcription task. Autocorrection use correlated with faster entry; manually selecting predicted words correlated with slower entry. This was an observational, self-selected study, not proof that suggestions cause slower typing or that those historical averages should be Utterleaf's targets.[^10]

The practical recommendation is to optimize time to correct intended text. A suggestion that saves keystrokes but requires constant visual checking can still be a poor trade. Keep normal key feedback independent of inference. Provide a literal candidate, conservative automatic correction and immediate correction undo. After a person rejects a replacement, avoid repeatedly imposing the same replacement during that edit.

Correction, suggestions and learning are distinct. Local inference may process a bounded amount of current composition/context without storing a typing history. That necessary transient processing must be described honestly; do not promise that the keyboard never sees text. Explicit dictionary entries can persist because the person deliberately saves them. Passive learning from general typing remains excluded under the current product policy, including an opt-in version unless that policy is explicitly reconsidered.

Test ordinary prose alongside names, mixed languages, URLs, email addresses, code, repeated letters, apostrophes, punctuation, emoji sequences and RTL text. Preserve literal input in password and terminal contexts. A language selector must not imply support for composition, prediction or speech that has not been implemented and tested.

Swipe typing is a strong recurring request in the privacy sample, but its quality cannot be inferred from inheriting LatinIME. HeliBoard's current documentation illustrates the dependency problem: its glide option requires a separate closed-source library. That is a product mechanism, not proof the library is safe or suitable for Utterleaf.[^11] Evaluate a reviewed, license-compatible offline decoder rather than accepting arbitrary native libraries as user-installed plugins. Android's dynamic-code-loading guidance describes integrity and code-execution risks that make this an engineering gate.[^12]

## Comfort, navigation and presentation

FUTO's documented interaction vocabulary includes Space cursor movement, Backspace selection/deletion, slide-to-symbol entry, a text editor, voice, and keyboard modes.[^13][^14] These are useful design references. The recommended Utterleaf surface is its own implementation and identity within the LatinIME base, with stable staggered rows, visible secondary characters, a broad Space key and a small action area. Do not equate a feature list with physical usability.

The proposed default is one compact suggestion/action strip, rather than multiple permanent tool rows. Keep a microphone and a discoverable actions entry reachable. Edit and Terminal open deliberate temporary panels; preserve a clear route back to letters and stable placement of frequently used controls. Allow a small set of pinned actions, but avoid making configuration a prerequisite for ordinary editing. Whether suggestions and shortcuts share a strip needs a prototype test for discoverability and accidental taps.

Gestures need explicit ownership. Space movement should not simultaneously switch language. Shift plus Space can select text, while a visible language action handles switching. Backspace drag should show the affected selection before release; leaving the gesture should cancel safely. Hold-slide-release accents and punctuation need feedback about the currently selected item. Provide non-gesture alternatives and configurable timing rather than assuming every user can perform a precise hold or slide.

Use a dark default as requested, alongside light/high-contrast choices. Dark mode is a preference, not an accessibility guarantee. Adjustable height, bottom padding, key-label readability, optional number rows and one-handed mode are useful; arbitrary decoration and constant animation are lower priorities. Put Utterlings in setup, help and success states where they clarify or welcome, keeping them out of the active text-entry area when they consume space or distract.

## Power features without everyday clutter

Hacker's Keyboard's historical guide describes Ctrl/Alt modifiers, Fn navigation/function keys and layout/height controls. It also warns that applications may ignore special keys and that a full layout can make phone keys too small.[^15] The useful lesson is a separate comfortable power layout with visible modifier state, not a permanently compressed desktop keyboard.

Provide forward Delete, Esc, Tab, arrows, Home/End, Page Up/Down and function keys where supported. Distinguish held, one-shot and locked modifier states, and clear them on relevant lifecycle transitions. Ctrl+Backspace, selection chords and terminal interrupt/control sequences require editor-specific tests. Never use an unverified fallback chord for a destructive action.

Android recommends text/composition APIs for normal input and discourages ordinary text entry through synthetic key events; it also documents the asynchronous focus risks of key dispatch.[^16] Therefore, copy/undo/select-all buttons should use appropriate editor actions where supported, while Terminal intentionally uses key semantics. A successful dispatch does not prove the intended application changed the intended text. Keep the existing generation guards, and document unsupported behavior rather than pretending universal desktop compatibility.

## Accessibility as a complete workflow

Android guidance calls for meaningful control descriptions and adequate touch targets.[^17] Apply it directly to toolbar/settings actions. A ten-column phone keyboard cannot simply make every key 48 dp wide without changing its layout; assess dense-key geometry with actual users and offer useful size/layout alternatives rather than silently overlapping targets.

The acceptance task is: enable the keyboard, find a field, type and correct a phrase, select an accent, start and cancel speech, review a transcript, insert it, reach the host app's next control and return. Test exploration without accidental insertion, focus order, selected/disabled states, slider value announcements and cancellation of popups. Long-press options must remain usable with supported screen-reader interactions.

Historical complaints need contemporary retesting. Google's TalkBack 16.2 documentation adds split-tap behavior and describes a two-finger double-tap voice shortcut specifically while using Gboard.[^18] Do not claim that shortcut automatically works in Utterleaf, or that a 2025 report proves the same limitation today. Support the platform accessibility system rather than asking people to disable it. Preserve access to other enabled input methods, including braille keyboards.

Motor accessibility remains an evidence gap in this sample. Proposed needs to validate include adjustable hold/repeat thresholds, haptics that can be disabled, visible alternatives to gestures, sufficient separation for destructive actions and left/right one-handed layouts. Do not impose a fast-typing benchmark on people whose priority is reduced fatigue or fewer physical actions.

## Security and privacy requirements

Citizen Lab's April 2024 investigation found keystroke-transmission vulnerabilities in cloud-based pinyin keyboard apps from eight of nine examined vendors. The report recommended considering fully on-device input and keeping software updated.[^19] This is strong evidence for reducing a particular cloud attack surface; it is not a claim that all keyboards, all products from those vendors or their current versions are vulnerable.

Utterleaf's threat model should cover disclosure of text/audio, malicious or malformed imported data, unauthorized actions across editor sessions, compromised updates and accidental persistence. A compromised OS or receiving application remains outside what an IME can fully defend against. Open source, a signed APK, hashes and no Internet permission each address different questions; none establishes complete security alone.

| Boundary | Proposed requirement | Evidence required before release |
| --- | --- | --- |
| Network and IPC | No keyboard Internet permission, cloud inference, telemetry, contact/account access or background dictionary updates. External model acquisition must be explicit and carry no input content. | Inspect merged manifest/dependencies and exported components; exercise intentional IPC paths and observe controlled network behavior. Packet silence in one test is not proof of no possible path. |
| Text and clipboard | No persisted typing history, clipboard monitoring or history. Read only bounded editor context needed for an active feature; explicit Copy/Paste remain available. | Check storage, logs, caches and backups using synthetic canaries; verify no cross-field candidate/context reuse. |
| Sensitive fields | Respect password, no-learning and relevant editor flags; fail conservatively where field capability is uncertain. No voice or personalized suggestions in password fields. | Password, numeric-password, no-learning, custom-editor and focus-transition cases; metadata is not infallible secret detection. |
| Voice | Explicit capture, visible state, cancel, bounded memory and no retained audio/transcript after its intended lifetime. No silent cloud fallback. | Permission denial/revocation, mic conflicts, interruptions, lock/focus changes, cancellation and late-result rejection. |
| Imports and native code | Reviewed assets, bounded parsers and atomic installation; no executable keyboard add-ons. A trusted hash establishes identity, not parser safety. | Malformed/truncated/oversized input, allocation limits, native sanitizers/fuzzing and failure rollback. Review provenance separately from runtime robustness. |
| Releases | Pinned dependencies, retained notices, protected signing, update identity continuity and independent review of security-critical changes. | Manifest/artifact verification, dependency inventory, build provenance and upgrade tests. Do not claim reproducibility before comparing independent builds. |

Android's no-personalized-learning flag is a request not to update personalized data, not a guarantee that all entered text is harmless when the flag is absent.[^20] Use that signal as one part of the policy. GrapheneOS's network controls are useful OS protections, but its documentation is not a basis for promising equivalent controls on every stock Android phone.[^21] Utterleaf must audit its own communication paths.

Keep secure-window protection, but describe its scope precisely. Android documents screenshot/non-secure-display protection and limitations of FLAG_SECURE.[^22] It does not secure text after insertion into another app or replace safe accessibility behavior. Do not add a production bypass merely to capture marketing screenshots; use synthetic debug fixtures. Any future overlay restrictions need separate accessibility testing.

Use OWASP MASVS to structure storage, platform, code and privacy verification, with explicit findings and evidence rather than a badge-like claim of compliance.[^23] Signing continuity is important for trustworthy updates, but Android signing documentation does not make a signed application intrinsically safe.[^24]

## Conflicting requests and proposed decisions

| Conflict | Recommended decision |
| --- | --- |
| Better personalization versus no passive collection | Static/local models plus explicit dictionary entries; no automatic retained learning in this plan. State the quality tradeoff honestly. |
| Persistent clipboard convenience versus sensitive-data retention | Explicit clipboard actions only. Consider manually authored snippets separately, never automatic clipboard capture. |
| Every power key visible versus comfortable phone typing | Daily/Edit/Terminal layers with optional rows; do not shrink the default keys to fit everything. |
| Tiny footprint versus large voice/prediction models | Useful basic typing without speech models; explicit verified optional assets and clear storage/performance information. |
| One-button downloads versus an offline keyboard core | First make external download/import instructions clear and verified. A separate acquisition component would require its own approval and security design. |
| Fast voice insertion versus accidental submission | Insertion must never imply sending a message or executing a terminal command. Keep review available; pause-based auto-insert remains deferred. |
| Extreme customization versus predictable support | Offer bounded, understandable options with practice/reset; no arbitrary scripts or executable plugins. |
| Universal phone/language support versus honest compatibility | Publish tested OS/device/language capabilities. GPU/NPU acceleration and non-Latin composition need independent feasibility work. |

Some users genuinely want cloud tools or long-lived history. Utterleaf should not attempt to satisfy those requests by weakening its policy. The best hybrid is a coherent set of features, not the union of every competitor's menu.

## User control where preferences differ

Product direction: disagreements about interaction and comfort should become
explicit local preferences wherever the alternatives can be supported safely.
Use toggles for binary choices, selectors for mutually exclusive modes, and
sliders for dimensions/timing. Do not make people choose a whole personality or
preset just to change one behavior. The following defaults are proposals for
review, not implementation decisions already approved.

| Preference | Choices to support | Proposed default and verification |
| --- | --- | --- |
| Correction | Off / conservative / stronger; suggestions independently enabled | Conservative with suggestions; verify undo, rejected corrections and literal contexts under every mode |
| Space gesture | Cursor movement / language switching / disabled | Cursor movement; only one owns the gesture, with a visible alternative for language switching |
| Selection and deletion gestures | Independently enabled; adjustable sensitivity and hold/repeat timing | Enable only after reliable preview/cancel behavior is established; verify disabled gestures have no side effects |
| Key geometry | Height, bottom spacing, optional number row; supported one-handed alignment | Comfortable standard layout with live practice and immediate reset; verify small screens, orientation and font scaling |
| Long-press content | Accent/punctuation arrangements from supported layouts; visible secondary-label toggle | Language-appropriate alternatives and visible hints; verify reachability and release/cancel behavior |
| Feedback and appearance | Independent sound/haptics/previews, dark/light/high contrast, system theme following | Dark as requested; no sound; haptics/previews require comfort and sensitive-field validation |
| Toolbar | Pin/reorder supported actions, show/hide optional rows, quick access to related settings | Compact layout; preserve an accessible route to actions and Reset even if everything optional is hidden |
| Voice activation | Tap-to-record or hold-to-record; explicit release-to-insert preference where supported | Tap with editable review as the cautious proposal; hold/release available after cancellation and editor-transition checks |
| Voice model | Choose among installed verified models with understandable size/speed/quality information | A suitable supported model; changing it never silently downloads assets or interrupts an active take |
| Editing/terminal layout | Daily/Edit/Terminal; supported optional power rows and modifier behavior | Daily; explicitly selected terminal semantics with visible modifier state and clear reset |

Every preference needs a documented meaning, stable local persistence, predictable
interaction with other options, and a clear Reset to defaults. Where a screen has
Apply/Cancel, Cancel must discard the preview; immediately applied quick toggles
must make that behavior clear and offer an easy reversal. Reset preferences must
not erase models or explicit dictionary entries. Data deletion is a separate,
clearly labeled action.

Group controls by Typing, Layout and comfort, Gestures, Voice, and Editing/Terminal.
Keep common adjustments in quick settings and link to the full section. Explain
why an option is unavailable instead of silently overriding it. Test conflicting
combinations, settings migration and reset as well as each toggle in isolation.

Privacy/security guarantees remain invariant: no toggle for telemetry, ambient
recording, passive typing collection, clipboard history, unverified executable
loading or cross-field action reuse. Requests that change those guarantees need a
separate explicit policy decision; this customization direction does not authorize
them. An inaccessible or unimplemented alternative must not be presented as a
working choice.

## Prioritized proposal

| Priority | Scope | Completion evidence |
| --- | --- | --- |
| P0: trustworthy foundation | Standalone pinned LatinIME build, licensing inventory, minimal capabilities, lifecycle guards and reliable literal typing | Build/native checks plus permission, sensitive-field, cancellation and editor-boundary tests |
| P0: usable base | Comfortable layout, accents, punctuation, repeat/cursor/selection behavior, correction undo and accessible controls | Real-device task completion with no critical data-loss, wrong-field or accessibility blockers |
| P1: everyday completeness | Local correction/suggestions, explicit dictionaries, supported multilingual configuration, emoji, sizing/practice and compact quick actions | Language-specific quality checks and successful setup without developer assistance |
| P1: Utterleaf strengths | Reachable local speech, editable review, clear model state, Edit/Terminal tools | One-handed voice and actual editor/terminal tests; no stale callbacks or implicit Send |
| P2: evaluated extensions | Reviewed offline swipe, split/floating layouts, richer local snippets and hardware acceleration | Separate quality, security, licensing, performance and accessibility evidence |
| Excluded | Telemetry, advertising/search feeds, passive learning/history, cloud rewrite defaults, arbitrary native add-ons | Not part of the proposed keyboard |

P2 means a separate dependency/validation gate, not that swipe or tablet comfort is unimportant. For swipe-dependent users, a keyboard without dependable swipe is not a complete replacement. Do not market universal replacement until the relevant use cases pass.

## How to validate that the hybrid is better

Run a formative comparison with consenting participants representing two-thumb typing, one-handed use, bilingual input, TalkBack, low vision, motor access needs and terminal work. Compare each person's familiar keyboard with the candidate on the same device, counterbalance order and allow practice. A small pilot identifies friction; it does not establish population-level superiority. No outreach or data collection is authorized by this document.

Use supplied synthetic text rather than private conversations. Include a message with deliberate typos and correction rejection; an accented name and mixed-language sentence; a URL and emoji; selection/copy/paste/undo; terminal navigation and Ctrl combinations; dictation with a name correction; model setup; and settings cancellation/reset. Include interruption during each destructive or asynchronous operation.

Record task success, remaining errors, correction time, accidental actions, discoverability, reach discomfort and reported effort. Measure keyboard display latency and touch-feedback latency at median and tail percentiles, inference turnaround, peak memory and thermal/battery effects on representative devices. Establish numerical performance thresholds from a baseline pilot before implementation targets are finalized; do not invent universal industry numbers.

Block migration on observed wrong-field insertion, unintended Send/terminal execution, data loss, sensitive-data persistence or inaccessible required controls. A finite passing suite establishes evidence only for tested conditions. Keep physical accessibility acceptance separate from emulator results. Optional locally stored test diagnostics should contain synthetic fixtures and aggregate timings, never routine user typing.

## Changes recommended to the migration plan

Keep the LatinIME foundation decision. Preserve its coherent input/composition architecture while removing incompatible data paths; replacing its touch engine with another custom button grid would defeat the reason for migration. Use FUTO's documented comfort and quick interactions as references, Hacker's Keyboard's explicit power-key model as a reference, and the community's failure cases as tests. These references grant no permission to copy another project's assets or differently licensed code.

Move correction/recovery, language setup and full-workflow accessibility into the earliest design review. Add separate approval gates for bounded transient context, dictionary acquisition and swipe decoding. Prepare the Daily/Edit/Terminal/Voice prototypes and a settings map for review before implementing them. Keep Android and desktop changes separate.

iOS remains a separate plan: Apple's documentation describes a restricted custom-keyboard environment, including microphone restrictions, system handling of secure fields and the ability of host apps to reject custom keyboards.[^25][^26] Shared product principles do not establish Android feature parity on iOS.

## Sources

Community sources are firsthand reports of preferences or difficulties, not verified current product defects. Undated documentation below was accessed September 10, 2026.

[^1]: r/privacy. [FOSS Keyboard options for Android?](https://www.reddit.com/r/privacy/comments/1gustrw/foss_keyboard_options_for_android/), November 19, 2024.
[^2]: r/privacy. [Is there any android keyboard that doesn't copy the words you write or record your messages?](https://www.reddit.com/r/privacy/comments/1w9bpav/is_there_any_android_keyboard_that_doesnt_copy/), September 6, 2026.
[^3]: mrusme, FUTO issue tracker. [Option to increase Spacebar distance/lower Spacebar height #1227](https://github.com/futo-org/android-keyboard/issues/1227), April 8, 2025.
[^4]: HeliBoard community and maintainer. [Multilingual typing #550](https://github.com/HeliBorg/HeliBoard/discussions/550), March 10, 2024, with follow-ups through March 2025.
[^5]: HeliBoard community. [Proof of concept for a D-pad #885](https://github.com/HeliBorg/HeliBoard/discussions/885), June 2024 discussion.
[^6]: r/Blind. [Android talkback and direct touch typing](https://www.reddit.com/r/Blind/comments/1htczgy/android_talkback_and_direct_touch_typing/), January 2025.
[^7]: benbrook78, r/Blind. [Android Keyboard for Low Vision](https://www.reddit.com/r/Blind/comments/u3eqts/android_keyboard_for_low_vision/), April 2022. Author also promotes their own keyboard; used only as a firsthand access-needs account.
[^8]: Accessible Android. [TalkBack navigates between keyboard items instead of moving focus out of the Gboard window when swiping](https://accessibleandroid.com/bugs/talkback-navigates-between-keyboard-items-instead-of-moving-focus-out-of-the-gboard-window-when-swiping/), 2025 report referring to TalkBack through 15.2.
[^9]: r/androidapps. [Any good keyboard for Android](https://www.reddit.com/r/androidapps/comments/1v39j0m/any_good_keyboard_for_android/), August 2026 discussion.
[^10]: Palin, Feit, Kim, Kristensson and Oulasvirta. [How do People Type on Mobile Devices? Observations from a Study with 37,000 Volunteers](https://userinterfaces.aalto.fi/typing37k/), MobileHCI 2019.
[^11]: HeliBorg. [HeliBoard README, Features](https://github.com/HeliBorg/HeliBoard#features), current documentation.
[^12]: Android Developers. [Dynamic Code Loading](https://developer.android.com/privacy-and-security/risks/dynamic-code-loading).
[^13]: FUTO Keyboard documentation. [Gestures](https://docs.keyboard.futo.tech/gestures).
[^14]: FUTO Keyboard documentation. [Currently Supported Actions](https://docs.keyboard.futo.tech/actions/supportedactions).
[^15]: Hacker's Keyboard. [UsersGuide](https://github.com/klausw/hackerskeyboard/wiki/UsersGuide), historical Gingerbread-era guide; not current app-compatibility evidence.
[^16]: Android Developers. [InputConnection](https://developer.android.com/reference/android/view/inputmethod/InputConnection), particularly sendKeyEvent and composition APIs.
[^17]: Android Developers. [Make apps more accessible](https://developer.android.com/guide/topics/ui/accessibility/apps).
[^18]: Google Android Accessibility Help. [What's new with TalkBack 16.2](https://support.google.com/accessibility/android/answer/16800105?hl=en).
[^19]: Knockel, Wang and Reichert, Citizen Lab. [The Not-So-Silent Type: Vulnerabilities Across Keyboard Apps Reveal Keystrokes to Network Eavesdroppers](https://citizenlab.ca/research/vulnerabilities-across-keyboard-apps-reveal-keystrokes-to-network-eavesdroppers/), April 23, 2024.
[^20]: Android Developers. [EditorInfo: IME_FLAG_NO_PERSONALIZED_LEARNING](https://developer.android.com/reference/android/view/inputmethod/EditorInfo#IME_FLAG_NO_PERSONALIZED_LEARNING).
[^21]: GrapheneOS. [Features overview: Network permission toggle](https://grapheneos.org/features#network-permission-toggle).
[^22]: Android Developers. [Secure sensitive activities](https://developer.android.com/security/fraud-prevention/activities).
[^23]: OWASP. [Mobile Application Security Verification Standard](https://mas.owasp.org/MASVS/).
[^24]: Android Developers. [Sign your app](https://developer.android.com/studio/publish/app-signing).
[^25]: Apple Developer. [Configuring open access for a custom keyboard](https://developer.apple.com/documentation/uikit/configuring-open-access-for-a-custom-keyboard).
[^26]: Apple Developer. [Configuring a custom keyboard interface](https://developer.apple.com/documentation/uikit/configuring-a-custom-keyboard-interface).
