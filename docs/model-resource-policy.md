# Model, provider and optional component policy

[Desktop roadmap](desktop-roadmap.md) · [Mobile roadmap](mobile-roadmap.md) ·
[Development boundaries](development-boundaries.md) · [Production readiness](production-readiness.md)

Proposed extension contract, September 12, 2026. Local operation remains the
default. This document does not claim that arbitrary model import, custom hosted
providers, a new downloader or a complete dependency compliance audit is implemented.
Existing desktop model setup and Android's verified catalog keep their documented
behavior until a platform-specific change passes its acceptance gates.

Completed bounded review: [desktop Silero VAD identity and notices](desktop-vad-resource.md).
That specific resource decision does not establish a full application compliance audit.

## Distinct user choices

| Choice | Experience to provide | Data boundary |
| --- | --- | --- |
| Reviewed local model | Show purpose, languages, size, storage/RAM requirements, license/source and supported engine; Download or Import, progress, Cancel and verification result | Download obtains model data; subsequent inference remains local. No transcript/audio accompanies acquisition |
| Additional local model | Select a supported format and reviewed identity/manifest; validate before activating | "Bring your own" is not permission to execute repository Python, pickle payloads, native add-ons or `trust_remote_code` |
| User-selected speech API | Separate opt-in provider with explicit endpoint, model, authentication and a synthetic connection test | Audio leaves the device only for a deliberately started remote take; no silent local-to-remote fallback |
| User-selected text API | Separate opt-in formatting/recap action, output preview and accept/discard | Sends the chosen text only by default. An API without speech capability cannot directly transcribe audio; use local transcription first |
| Team deployment | Managed local resources and inspectable configuration with an offline policy | No employee typing analytics or transcript archive required; secrets and provider enablement have separate controls |

User-created hosted endpoints require encrypted transport for remote hosts,
credential storage through an appropriate OS secret store, bounded timeouts and
responses, cancellation, redacted diagnostics and no credential forwarding across
redirects. Any later loopback/local-server exception needs an explicit threat model.
Endpoint names such as "private" or "zero retention" are not verified privacy
properties; show the configured service and its declared policy without promising
control over a third party. Test connectivity with synthetic content, never the
last dictation. Reset and configuration export must not expose credentials.

Keep Android's offline IME permission boundary intact. A future hosted-provider
experiment requires a separate platform design, explicit data flow and permission
decision; the desktop option must not silently introduce Internet permission into
the Android core. No browser/intent trick should be used to disguise remote audio
or text processing as local operation.

## Licensing and provenance gates

Utterleaf's root source uses [Apache-2.0](../LICENSE). That does not automatically
cover dependencies, model weights, training data, dictionaries, fonts, codecs,
artwork or optional executables. Keep each resource's actual terms, revision and
redistribution decision separate. A source-visible project or downloadable weight
file is not automatically FOSS or approved for bundling.

For every proposed component, record:

| Record | Required content |
| --- | --- |
| Identity | Publisher, upstream URL, exact commit/version, file/format, expected size and digest |
| Rights | Exact license text/version, notices and attribution, redistribution/modification/use conditions, patent or other special terms where present |
| Decision | Bundle permitted; user acquisition permitted subject to stated terms; unsupported pending review; or rejected. Record reviewer/date and evidence rather than assuming a category |
| Compatibility | Application-license compatibility, linking/execution arrangement, source/NOTICE obligations and platform distribution restrictions |
| Security | Parser/runtime/dependency inventory, supported formats, privilege/data flow, vulnerabilities, resource bounds and malformed input handling |
| Delivery | Trusted source, pinned identity, gated-access terms, redirects/auth boundaries, interruption/rollback behavior and update/revocation process |

Moving acquisition behind a button is a delivery choice, not a finding that the
license permits the integration. The actual license and technical relationship
still require review; for example, the FSF distinguishes aggregation from
combined programs in its [GPL FAQ](https://www.gnu.org/licenses/gpl-faq.en.html).
Do not add a download route for a component whose permitted use/integration has
not been established. Unresolved rights stay unsupported until resolved.

Hugging Face model cards can record licenses and model limitations, but the exact
repository license and files must also be reviewed.
[Model-card documentation](https://huggingface.co/docs/hub/model-cards)
Gated repositories may require the user to request access and accept publisher
conditions. Utterleaf must not bypass those gates, accept terms silently, share
credentials or mirror restricted files as a workaround.
[Gated-model documentation](https://huggingface.co/docs/hub/models-gated)

## Acquisition and recovery

Show the source, size, intended engine, license/terms and storage requirement
before acquisition. Pin the file identity; do not turn a moving `main` branch or
untrusted user-supplied checksum into a claim of publisher authenticity. A hash
checks the expected bytes, not whether a parser/model is safe or legally usable.

Download to a temporary location, enforce size/time/disk limits, reject unsupported
formats and traversal/archive abuse, then verify and atomically activate. Cancel,
network failure, invalid credentials, wrong hash, low storage and failed activation
leave the previous working model intact. Never run a model repository's install
script. Model deletion is explicit and separate from restoring preferences.

Existing desktop **Download selected model** already supports an explicit action;
expand it only through this reviewed-resource flow. Android currently opens the
publisher in a browser and verifies the selected import. Direct in-app acquisition
is not implied by these future requirements.

## Production and documentation evidence

Each release needs an inventory of the actual packaged files and dependencies,
versioned notices, checksums/signing evidence and review of changed permissions.
Maintain a machine-readable SBOM when the dependency/release workflow is upgraded;
license scanners and vulnerability scanners support review but do not certify all
rights or security. A failed review blocks that component, not ordinary local typing.

Document the whole path with current screenshots: choose → acquire → verify → use
→ cancel/recover → update/delete. Show examples of local versus remote data flow,
supported models/formats, unavailable capabilities, offline deployment and error
recovery. Never display a provider as ready merely because a credential was saved.

Premium presentation requires consistent screens, clear progress and failure
states, readable documentation and tested task completion. Enterprise readiness
also requires signed/reproducible release evidence, vulnerability response,
controlled updates, accessibility and named-platform validation. These are gates
to satisfy, not labels to place on the current preview.
