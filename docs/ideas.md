# Ideas and product decisions

[Roadmap hub](roadmap.md) · [Desktop](desktop-roadmap.md) · [Mobile](mobile-roadmap.md)

Updated September 9, 2026. This is the intake and decision record. Implementation
status and acceptance criteria live in the linked platform plan, not in a second backlog.

| Idea / need | Decision | Plan |
| --- | --- | --- |
| Complete mobile keyboard with local dictation | Accepted direction; replaces the voice-companion-only product goal | [Mobile M1–M6](mobile-roadmap.md#android-milestones) |
| Accessible sizing, contrast, touch timing and multimodal feedback | Required product capability | [Mobile accessibility](mobile-roadmap.md#accessibility-acceptance-matrix) |
| Long speech without an arbitrary hold cutoff | Accepted, requires bounded processing and clear cancellation | [Desktop feature plan](feature-plan.md) · [Mobile M4](mobile-roadmap.md#android-milestones) |
| Local file transcription and subtitle export | Planned desktop scope; mobile feasibility is an idea, not a committed port | [Desktop feature plan](feature-plan.md) |
| Video/system-audio captions, meetings, speaker labels and translation | Planned desktop investigation with explicit capture/retention; evaluate mobile separately | [Desktop feature plan](feature-plan.md) |
| Swipe typing | Candidate mobile feature; engine and data licensing, security, accuracy and device cost need review | [Mobile roadmap](mobile-roadmap.md) |
| Local vocabulary and selective settings backup | Accepted with explicit selection and no transcript/secret export | [Desktop roadmap](desktop-roadmap.md) · [Mobile M5](mobile-roadmap.md#android-milestones) |
| FUTO-like keyboard concept | Learn from usability; choose a compatible foundation and Utterleaf's own design | [Mobile M1](mobile-roadmap.md#android-milestones) |
| A different desktop UI framework | Evaluate against demonstrated usability/accessibility/startup limits; no rewrite solely for appearance | [Desktop polish](desktop-roadmap.md#4-accessibility-and-desktop-polish) |

## Boundaries

Cloud accounts, ad SDKs, telemetry, passive listening, automatic permanent transcript
archives, clipboard surveillance and arbitrary executable keyboard plugins are outside
the current product direction. A useful feature does not justify weakening input security.

For each new idea, record the user problem, affected platforms, intended benefit,
permission/data implications, licensing, maintenance cost and evidence needed.
Promotion to a roadmap is an explicit product decision, not a promise that every
desktop feature will appear on phones or vice versa.
