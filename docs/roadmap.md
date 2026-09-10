# Utterleaf roadmap

<img src="assets/brand/utterling-thinking.png" width="88" alt="Utterling considering the next improvements" />

[Documentation](README.md) · [Development boundaries](development-boundaries.md) · [Execution plan](execution-plan.md)

Updated September 9, 2026. This is the planning hub, not a list of released features.
**Security first, privacy second, convenience third.** Accessibility and reliability
are requirements throughout development, not finishing touches.

## Choose a workstream

| Workstream | Product | Plan and current evidence |
| --- | --- | --- |
| Desktop | Quiet local dictation on Windows, macOS, and Linux | [Desktop roadmap](desktop-roadmap.md) · [Detailed feature plan](feature-plan.md) · [Platform testing](platform-testing.md) |
| Android | A complete, customizable keyboard with integrated local dictation | [Mobile roadmap](mobile-roadmap.md) · [Current Android preview](mobile.md) |
| iOS | A separately implemented keyboard and local speech experience within platform restrictions | [iOS feasibility and milestones](mobile-roadmap.md#ios-track) |
| Shared product direction | Security, privacy, accessibility principles, branding, and candidate ideas | [Ideas and decisions](ideas.md) · [Development boundaries](development-boundaries.md) |

Desktop and Android have independent release histories. The
[Android preview guide](mobile.md) identifies the current signed APK and its
validation evidence. Android remains a preview: physical-device, accessibility,
performance and real Obtainium acceptance are still open. No iOS app is released.

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

The [production-readiness plan](production-readiness.md) sequences correctness,
physical-device benchmarks, supply-chain hardening and stable-release acceptance.
Its proposed budgets are not measured results or completed roadmap items.

- Explicit microphone activation and clear stop/cancel controls; no passive capture.
- Local inference; no accounts, telemetry, automatic transcript archives, or hidden uploads.
- Minimum permissions, verified model import, dependency review, and protected signing keys.
- Accessible setup, editing, feedback, and recovery; never require one particular sense or gesture.
- Predictable settings, safe reset, and no loss of security preferences for convenience.
- Each platform retains its own compatibility matrix. One device passing does not mean all phones work.

Detailed implementation status belongs in the platform plans, avoiding duplicate
backlogs with conflicting completion claims.
