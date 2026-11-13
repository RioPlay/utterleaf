# Windows dictation delivery repair and RC4 candidate

## Contract

- **Goal:** prepare a reviewable Windows preview candidate with corrected clipboard delivery, Settings lock recovery and T3 Code prose spacing.
- **Area:** Windows clipboard/injection path and tests, Settings instance recovery and tests, exact T3 executable classification and tests, preview metadata and this plan.
- **Constraints:** keep clipboard containment, cancellation, target and ownership checks. Do not retry possibly dispatched text or collect clipboard/dictation content. Keep user preferences, vocabulary and models. Add no dependencies. Keep Android and other desktop binaries outside this candidate. Preserve immutable stable v0.4.5 and published RC2.
- **Acceptance:** the exact preview tag and both Python version declarations agree at `0.4.6rc4`; Windows preview workflow checks the exact tag and revision; focused and full CI pass; preview notes disclose unsigned CPU-only Windows scope and known native runtime advisories; publication, if separately authorized, is a prerelease with `latest=false`.
- **Verification:** focused regression tests and full desktop pytest in CI, canonical Windows CPU package build, frozen CLI and clipboard worker checks, native notice and archive checks, and exact-tag CI. Local evidence below is prior to hosted CI for the candidate.
- **Non-goals:** stable release, signing, publishing, cross-platform release claims, live OBS, automatic retry, model or preference changes, and broad hardware/editor/accessibility certification.
- **Stop:** hand off the reviewable candidate after metadata and docs agree. Record hosted CI and publication separately when available. Actual post-install T3 Code dictation remains user acceptance.

## Candidate source and evidence

The candidate is based on the Windows repair branch descended from `aa284ca`; the desktop security update was merged to main as `87012a56bb376656fe976476f909a9df2bf72cea`, preserving that ancestry. RC4 metadata and these Windows repairs are still pending review, CI and publication. RC2 and stable v0.4.5 remain immutable.

Local checks recorded for the repaired source passed 1,698 tests with 14 expected skips. Focused regression tests cover clipboard receipt publication, changed clipboard ownership, Settings lock contention and recovery, and T3 two-take spacing. The frozen Windows build and native notice checks passed. The installed helper accepted controlled synthetic text in a native field; installed files passed SHA-256 read-back. User preferences and downloaded models were retained. These local results are evidence for that checked source and package, not hosted CI for the final RC4 candidate.

Independent review caught an overly broad executable parser that could classify Linux terminal titles as Windows app identities. The parser was narrowed to exact T3 aliases and regression coverage was added; the final suite passed after the correction. A separate audio-level diagnosis did not produce a production code change and is outside this preview claim.

## Remaining evidence and limits

- Hosted CI must pass on the final candidate revision, including exact-tag Windows preview build and artifact checks.
- The installed T3 Code two-take retry is still unverified. Controlled native field checks are not a substitute for that user journey.
- The preview is unsigned, Windows x64 CPU-only, and does not provide macOS, Linux or Android updates.
- Expat 2.9.0 and SQLite 3.50.4 remain in the bundled runtime with known upstream advisories. Python package scans do not establish that every bundled native component is free of advisories. Do not describe the build as fully secure.
- Live OBS, physical microphone endurance, broad editor support, accessibility and performance across hardware remain outside the verified evidence.

The Windows preview workflow builds and uploads candidate artifacts from a
`desktop-v*` tag; it does not publish a GitHub release. Publication follows
exact-artifact verification and must preserve stable `latest` selection with
prerelease status and `latest=false`.
