# Utterleaf roadmap

<img src="assets/brand/utterling-thinking.png" width="88" alt="Utterling considering the next improvements" />

[Documentation](README.md) · [Development boundaries](development-boundaries.md) · [Execution plan](execution-plan.md)

Updated September 9, 2026. This is the planning hub, not a list of released features.
**Security first, privacy second, convenience third.** Accessibility and reliability
are requirements throughout development, not finishing touches.

## Choose a workstream

| Workstream | Product | Plan and current evidence |
| --- | --- | --- |
| Desktop | Quiet local dictation on Windows, macOS, and Linux | [Desktop roadmap](desktop-roadmap.md) ? [Detailed feature plan](feature-plan.md) ? [Platform testing](platform-testing.md) |
| Android | A complete, customizable keyboard with integrated local dictation | [Mobile roadmap](mobile-roadmap.md) ? [Current Android preview](mobile.md) |
| iOS | A separately implemented keyboard and local speech experience within platform restrictions | [iOS feasibility and milestones](mobile-roadmap.md#ios-track) |
| Shared product direction | Security, privacy, accessibility principles, branding, and candidate ideas | [Ideas and decisions](ideas.md) ? [Development boundaries](development-boundaries.md) |

Desktop v0.4.0 and [Android 0.1.0-alpha04](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha04)
have independent release histories. Android alpha04 includes an **English typing
keyboard with local dictation**, preferences, preview extension, Obtainium setup
and corrected Shift/Caps behavior, published as a signed APK. It is an early
foundation; physical device, accessibility
and real Obtainium update acceptance remain open. Earlier voice-companion feedback
from a Pixel 8 Pro does not certify this keyboard. No iOS app is released.

Android's [passed CI run](https://github.com/RioPlay/utterleaf/actions/runs/34427672686)
covers 4 JVM, 11 emulator and 3 release-contract tests; the [mobile guide](mobile.md#android-validation--september-9-2026)
distinguishes live-IME editing checks from direct-panel Shift/Caps checks and open
selection-replacement acceptance.

The [successful Android signing/publishing run](https://github.com/RioPlay/utterleaf/actions/runs/34428171272)
also verified an emulator upgrade from signed alpha03 to alpha04 and same-version
reinstallation with the unchanged certificate. Physical and real Obtainium update
checks remain open.

The [execution plan](execution-plan.md) assigns ordered work packages, file ownership,
security gates and external validation requirements across these workstreams.

## How work moves forward

1. Capture a problem and proposed benefit in [Ideas](ideas.md).
2. Review permissions, data flow, licensing, accessibility, and maintenance cost.
3. Put accepted work in the relevant platform roadmap with a completion gate.
4. Implement and test within that platform's source and build boundaries.
5. Mark work verified only with evidence; mark it released only with an installable
   artifact, version, and release notes. A green build alone is not release availability.

Status vocabulary: **Idea**, **Planned**, **In progress**, **Implemented / unverified**,
**Verified**, and **Released**. Do not describe a proposal or local prototype as shipped.

## Shared requirements

- Explicit microphone activation and clear stop/cancel controls; no passive capture.
- Local inference; no accounts, telemetry, automatic transcript archives, or hidden uploads.
- Minimum permissions, verified model import, dependency review, and protected signing keys.
- Accessible setup, editing, feedback, and recovery; never require one particular sense or gesture.
- Predictable settings, safe reset, and no loss of security preferences for convenience.
- Each platform retains its own compatibility matrix. One device passing does not mean all phones work.

Detailed implementation status belongs in the platform plans, avoiding duplicate
backlogs with conflicting completion claims.
