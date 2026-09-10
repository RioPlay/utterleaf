# Desktop update plan

[Desktop roadmap](desktop-roadmap.md) · [Android updates](mobile-obtainium.md)

**Planned, not implemented. This is not a v0.4.1 feature.** Checking GitHub for a
new version is a small, separable feature. Reliably replacing a running application
requires authenticated releases, recovery, and platform-specific testing.

## First experience

- **Check for updates** is manual by default. Offer an explicit opt-in for daily
  or weekly checks, based on elapsed time rather than counting launches.
- After launch, check only when due, in background work with a short timeout.
  Never block startup, recording, or offline use. Cache the last result locally,
  respect rate limits, and back off after failures; repeated launches must not
  cause repeated requests. The existing offline/network policy remains authoritative.
- Show installed/new version and a plain-text summary with an explicit release-page
  link. Initially, checking never downloads or installs an application update.
  No forced restart, modal interruption during dictation, or untrusted remote UI.
- Send no dictation, vocabulary, configuration, device identifiers, or diagnostics.
  GitHub still receives ordinary connection information such as an IP address;
  public release checks need no account or embedded access token.

## Release identity and trust

Use only the fixed `RioPlay/utterleaf` repository. Parse supported desktop version
tags and exact platform/architecture asset names; reject ambiguous, missing, draft
or unwanted prerelease matches. Android `android-v…` releases and APKs are a separate
channel, never desktop updates. Do not assume the repository-wide latest release
belongs to desktop. The [official GitHub Releases API](https://docs.github.com/en/rest/releases/releases?apiVersion=latest)
provides published-release and asset metadata, including download URLs; it is a
discovery source, not an independent publisher trust root.

HTTPS protects transport and hashes detect corrupted bytes. A checksum published
beside a compromised artifact does not authenticate its publisher. Before offering
verified in-app downloads or self-replacement, establish authenticated signed
metadata, pinned initial trust, protected signing roles, expiration/version checks,
and a tested key-rotation/recovery process. Bind signatures to version, channel,
platform, asset size and digest. Reject expired, replayed, substituted or wrongly
signed targets; do not silently fall back to unsigned metadata.

Evaluate a maintained [The Update Framework (TUF)](https://theupdateframework.io/docs/overview/)
implementation and its key-management requirements instead of inventing a signing
protocol. TUF addresses update-system compromise, rollback and freeze attacks;
adoption still requires a reviewed publisher workflow and client integration.
Native platform signing/notarization is an additional distribution gate.

## Delivery phases and acceptance

| Phase | Deliverable | Required evidence |
| --- | --- | --- |
| 1 — next | Manual check UI, then opt-in daily/weekly checks | Offline launch is unaffected; timeouts/rate limits/malformed responses fail quietly with an actionable manual status. Test version/channel/architecture selection, cached results, clock changes, repeated launches and disabled-network settings. No download, install or telemetry side effect. |
| 2 — after trust review | Explicit authenticated download into private staging | Verify trusted metadata and the complete target before use. Test expired/forged/replayed metadata, rotated/revoked keys, wrong channel/architecture, interrupted downloads and disk exhaustion. No auto-install on download completion. |
| 3 — Windows first | Explicit “Restart and apply” with recoverable staged replacement | Native tests cover running-file locks, multiple instances, cancellation, power/process interruption, writable/portable/read-only installations, denied elevation and failed health checks. Stop active capture before the confirmed restart; never discard a take silently. |
| 4 — separate platform gates | macOS and Linux delivery adapters | Validate signing/notarization or package-manager ownership, filesystem permissions, application layout, restart and rollback natively. A passing Windows updater does not establish these platforms. |

## Replacement and recovery boundaries

Download/extract with explicit limits on compressed bytes, expanded bytes, file
count and paths. Reject traversal, absolute paths, symlinks/reparse-point escapes,
duplicate destinations and malformed archives before touching the live app.
Do not execute archive scripts or accept arbitrary download/application locations.
Review allowed HTTPS redirect hosts for GitHub asset delivery; reject downgrade
to HTTP. Staging and the helper must be private and protected from other writers.

A Windows helper lives outside the versioned application directory so Windows
file locks do not require overwriting the running executable. It waits for the
intended instance to exit, applies only the verified staged version, then performs
a bounded launch/readiness check without starting microphone capture. Keep the
last verified build until that succeeds. On failure, restore that known build and
report recovery; this narrow transactional rollback must not permit arbitrary
downgrades or bypass signed-metadata policy.

Preserve configuration, vocabulary, models and the user's optional FFmpeg choice.
Review any schema migration for rollback compatibility before replacement. Never
replace unrelated user files or download models/FFmpeg as a hidden update step.
For portable, read-only or administrator-managed installs, provide verified release
download and replacement instructions when in-place updating is unavailable;
do not silently elevate or fight an operating-system package manager.

Android continues to use its separate signed APK/Obtainium flow. Actual Obtainium
and physical update acceptance remain separate from this desktop plan.
