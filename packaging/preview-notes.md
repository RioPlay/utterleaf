# Utterleaf 0.4.6 RC5

**Draft release notes for an unpublished Windows desktop candidate.** Stable
v0.4.5 remains the default release. RC5 has no tag or public download.
The published [Windows RC4 preview](https://github.com/RioPlay/utterleaf/releases/tag/desktop-v0.4.6-rc.4)
is the historical latest preview; its release evidence and artifact remain
separate from this draft.

## Changes prepared for RC5

- **Explicit Vocabulary corrections:** enter a term and its correction in the
  Vocabulary form. A valid pair is staged in the existing dictionary draft and
  saved only when Save is selected. The form does not learn passively or read
  editor or clipboard contents. Cancel and Reset keep their existing behavior.
- **Desktop Settings visuals and recovery:** the candidate carries the prepared
  layered visual updates and recovery work from the desktop modernization stream.
- **Retained RC4 security and delivery fixes:** patched Python dependency floors
  and hash-checked Windows inputs; clipboard ownership checks after synthesized
  formats are published; bounded Settings lock recovery; and exact T3 Code prose
  spacing. The [published RC4 record](https://github.com/RioPlay/utterleaf/releases/tag/desktop-v0.4.6-rc.4)
  describes the released Windows build and its original evidence.

## Package and acceptance status

Targeted headless source checks passed. The local Windows CPU archive and frozen
CLI checks are prepared. Four frozen CLI cases passed, covering `--help`,
offline polish with expected prose and list output, and rejection of invalid
`--polish` input with exit code 2. The archive contains 620 entries whose
hashes match the tested package. It was built from source commit
`0175d5735a30db5ee902651b3519bd1a3fb63d2c` as
`dist/Utterleaf-windows-x64-cpu.zip`. Its SHA-256 is
`7c1ef41c654a38326b05feba8b5d10cd67a52fcd8dc392d0737ada5961090968` and its
size is 114,996,239 bytes. The full native closure and licenses for 48 packages
are included; speech weights, CUDA, FFmpeg and ASIO are absent. See the
[RC5 readiness plan](../docs/plans/active/desktop-0.4.6-rc5-release-readiness.md)
for verification evidence.

The archive is local, unsigned, unpublished and not installed. Actual Tk focus,
undo, Save, Cancel and pointer behavior, Windows UI Automation and screen-reader
support, microphone, editor and device behavior, mixed DPI, and other desktop
platforms have not been verified for RC5. Final CI and native GUI/device gates
remain open.

If the local RC5 archive is used for review, extract the complete Windows x64
CPU archive to a new folder and open `Utterleaf/utterleaf.exe`, keeping
`_internal` beside the executables. Python is included; speech-model weights and
optional CUDA libraries are separate, and FFmpeg and PyAV native codecs are not
included. This is not a public download or an installed-app acceptance result.

Android work is paused until a suitable build and validation pipeline is agreed.

## Preview limits

The carried Windows runtime still contains Expat 2.9.0, and SQLite remains
3.50.4. Known upstream advisories for these native components remain; their
presence does not establish exploitability in Utterleaf. This candidate is not
described as fully secure or free of known vulnerabilities. See the
[dependency security notes](https://github.com/RioPlay/utterleaf/blob/main/docs/plans/active/desktop-dependency-security.md)
for scope and details.

Continuous recording uses temporary, unencrypted local audio files, approximately
220 to 660 MiB per hour depending on input rate. They are removed on completion
or cancellation; this is not secure erasure. Free disk space and system resources
limit session length, and transcript text grows with the recording.

The two-minute text recovery and review window remains separate from recording
length. Verified review insertion and caret-aware corrections require a
supported native Windows Edit field. Browsers and other unsupported review
targets use Copy. Ordinary dictation paste remains guarded at the window level.
Check the target field before retrying any delivery reported as uncertain.

Live OBS transcription is not available. Headless checks do not establish real
microphone performance, broad editor coverage, accessibility, or performance on
additional hardware. The final T3 Code two-take retry after installation remains
to be confirmed.
