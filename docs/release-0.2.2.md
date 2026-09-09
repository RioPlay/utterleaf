# Release 0.2.2 preparation

> Archived release record. Use the [latest downloads](https://github.com/RioPlay/utterleaf/releases/latest)
> and [installation guide](installation.md) for the current app.

## Final pre-flight verification (2026-09-07)

- PASS: version 0.2.2 in pyproject.toml. LICENSE matches https://www.apache.org/licenses/LICENSE-2.0.txt after whitespace normalization (blank-line layout differs; no text differences). NOTICE identifies Utterleaf and Copyright 2026 RioPlay and points to third-party notices. Candidate LICENSE and NOTICE are byte-identical to the repository copies.
- PASS: live project MIT reference removed from the comment in packaging/utterleaf.spec. Historical references and third-party MIT license entries are intentional. Candidate THIRD-PARTY-NOTICES.md states Apache-2.0 and the deliberate FFmpeg exclusion policy.
- PASS: full suite 202 passed, 1 symlink privilege skip (203 collected). The first quiet run had three additional transient skips; the diagnostic rerun passed those tests. Targeted test_polish.py, test_indicator.py and test_startup.py: 81 passed, 1 symlink skip. Verified theres/wheres, first-person list prose, desktop percent escaping, close/join/restart tests; inspected per-thread Win32 class naming and UnregisterClassW in finally.
- PASS: tests/smoke_release.py against artifacts/release-0.2.2-candidate/Utterleaf passed GUI-subsystem checks, help, polish, offline doctor, list formatting and owned settings-window lifecycle. dist/Utterleaf/utterleaf-cli.exe --doctor passed with APPDATA isolated under artifacts/preflight-doctor-profile; RTX 3090 selected via CTranslate2. All three candidate executable SHA256SUMS.txt entries matched. Candidate recursive filename scan found zero ffmpeg/x264/x265/avcodec matches.
- PASS: candidate contains 37 notice entries/license directories. This is inventory evidence, not proof that every required full license is delivered.
- FLAG: six LICENSE-DECLARED.txt fallbacks remain in the renamed candidate. Exact findings below; collection success does not close them.
- FLAG: LGPL exact-source references and replacement procedure are documented below, but source correspondence and delivery alongside the binary still require verification before publishing.
- FLAG: NVIDIA redistribution statement is not verified for all shipped files; cuDNN EULA mismatch and NVRTC alternate DLL require resolution below.
- PASS: local editable package installed as utterleaf 0.2.2 with no new dependencies. Historical mindict-0.1.0.dist-info remains in the venv; it is not the release package.
- FLAG: hosted CI has not run. Static review details below.

Renamed the app, package/imports, CLI and GUI launchers, platform startup entries, config/log/IPC locations, build environment variable, spec, workflow, documentation and screenshot to Utterleaf before the first commit. Rebuilt the CUDA distribution using UTTERLEAF_BUNDLE_CUDA=1 and regenerated notices/checksums. The candidate is artifacts/release-0.2.2-candidate/Utterleaf. The older running artifacts/release-0.2.2/Mindict and previous Mindict candidate were preserved. The workspace directory remains Mindict so the active workspace and running release paths remain valid. Utterleaf uses a fresh profile; old settings/model caches and startup registrations are not automatically migrated.

### Full-license fallback findings

All installed paths below are relative to `.venv/Lib/site-packages/`; candidate notice paths are relative to `artifacts/release-0.2.2-candidate/Utterleaf/`.

| Installed package | Better full-text evidence | Candidate finding / remaining action |
| --- | --- | --- |
| ctranslate2 4.8.1 | No license/copying/notice file found in dist-info or package tree; metadata declares MIT. | licenses/ctranslate2/LICENSE-DECLARED.txt only. Obtain exact-version upstream copyright/license and bundled-native-library notices. |
| flatbuffers 25.12.19 | No full text in its own dist-info/package. onnxruntime/ThirdPartyNotices.txt line 2563 has google/flatbuffers followed by full Apache-2.0 text. | That ONNX notice is absent from candidate. Verify applicability to the separately installed FlatBuffers version and ship its required license/notices; the embedded notice is not version evidence. |
| onnxruntime 1.28.0 | onnxruntime/LICENSE (1094 bytes) and onnxruntime/ThirdPartyNotices.txt (331175 bytes). | Neither is harvested into candidate; licenses/onnxruntime/LICENSE-DECLARED.txt only. Collect both package-local files. |
| protobuf 7.35.1 | protobuf-7.35.1.dist-info/LICENSE (1732 bytes), full Google BSD text and generated-code notice. | Collector misses old-style root license without License-File metadata. Candidate only has declaration. |
| pywin32-ctypes 0.2.3 | pywin32_ctypes-0.2.3.dist-info/LICENSE.txt (1644 bytes), full Enthought BSD text. | Same root-license harvesting gap; candidate only has declaration. |
| tokenizers 0.23.1 | No full text in dist-info/package; classifier identifies Apache Software License. | Declaration says only '(see package metadata)'. Obtain exact-version upstream license and applicable Rust dependency notices. |

This pass records exact sources as requested instead of changing collection/build output. All six remain binary-publication flags until required texts are included and verified.

### LGPLv3 corresponding source and replacement

Installed versions are pynput 1.8.2 and pystray 0.19.5. Both are used in the frozen application and covered by LGPLv3. Candidate `licenses/pynput/COPYING.LGPL` and `licenses/pystray/COPYING.LGPL` contain LGPLv3; `licenses/pystray/COPYING` supplies GPLv3 for the combined distribution. Section 4 requires appropriate notices, license copies, and a permitted recombination/relinking route; see https://www.gnu.org/licenses/lgpl.html and the shipped texts. Modification of these LGPL library portions and reverse engineering to debug those modifications must remain permitted.

Exact upstream source references checked:

- pynput 1.8.2: https://files.pythonhosted.org/packages/86/c6/e2d415610cfbc78308bee44218a46124aaa3301b1df08814df819b2254a1/pynput-1.8.2.tar.gz ; PyPI-reported SHA256 `f493c87157cd3861b4468f7f896857051762f44ed26f1b641e7cc5840a457087` (https://pypi.org/pypi/pynput/1.8.2/json). Archive contents/hash have not been independently downloaded/compared. Installed pbr.json reports git_version 2d6ab69 and is_release false, so establish source correspondence rather than assuming the version label suffices.
- pystray 0.19.5: https://github.com/moses-palmer/pystray/tree/v0.19.5 ; annotated tag resolves to commit `1907f8681d6d421517c63d94f425f9cdd74d0034`. Immutable source archive: https://github.com/moses-palmer/pystray/archive/1907f8681d6d421517c63d94f425f9cdd74d0034.zip . PyPI 0.19.5 lists only a wheel, no sdist. Compare lib/pystray in this source with the installed library before claiming correspondence.

Replacement/rebuild procedure for recipients (perform in a separate source checkout, not over a running installation):

1. Obtain the Utterleaf release source at its eventual v0.2.2 commit and the exact library sources above. Retain full license texts and any changes to the library sources. The release must provide corresponding application code/build scripts and verified library source access alongside the binary; generic repository links alone are insufficient.
2. Install Python 3.14 for Windows x64, create `.venv` using `py -3.14 -m venv .venv`, then run `.\.venv\Scripts\python.exe -m pip install -e ".[dev]" pyinstaller`. For the CUDA build use `".[dev,cuda]"` and explicitly install `nvidia-cuda-nvrtc-cu12==12.9.86` as the spec requires it; preserve the verified dependency versions in release build records. The current project ranges are not a reproducibility lock.
3. Unpack sources under `vendor/pynput` and `vendor/pystray`, modify the interface-compatible library code, then install those local trees with `.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation ./vendor/pynput ./vendor/pystray`. Upstream build prerequisites must be present. Verify the installed code is the modified code before freezing.
4. Run `.\.venv\Scripts\python.exe -m pytest -q`. Set `$env:UTTERLEAF_BUNDLE_CUDA='1'` only for the CUDA edition, then run `.\packaging\build.ps1`. This rebuilds the frozen Python archive with the replacement libraries and regenerates notices/checksums. Copying a .py file beside an existing exe is not a verified replacement method.
5. Run `.\.venv\Scripts\python.exe tests\smoke_release.py dist\Utterleaf`, then use the entire newly built `dist/Utterleaf` directory as a separate installation. No original signing key is required for this unsigned build. Keep application data isolated while checking the replacement.

FLAG: this procedure has been reviewed against the spec/build script but a modified-library rebuild has not been exercised. Before binary publication, verify source equivalence, archive/hash the corresponding sources and build inputs, test recombination, and deliver this information with the release (LGPL section 4(d)(0) route). This document is not a claim that the existing binary already satisfies all delivery obligations.

### NVIDIA component-by-component evidence

Each candidate `licenses/<package>/License.txt` is byte-identical to that installed package's EULA. cuBLAS, CUDA Runtime and NVRTC contain the older 2018 SDK agreement/CUDA supplement; cuDNN contains the January 2020 agreement/supplement. The current online CUDA EULA (https://docs.nvidia.com/cuda/eula/index.html) is newer and was not substituted for the actual wheel terms.

| Package/version | Shipped DLLs and actual EULA mapping | Status |
| --- | --- | --- |
| nvidia-cublas-cu12 12.9.2.10 | cublas64_12.dll, cublasLt64_12.dll, nvblas64_12.dll. CUDA Attachment A section 2.6 names cublas.dll/cublasLt.dll (line 637), nvblas.dll (660). | Component families listed; mapping version-suffixed filenames is an inference, conditional on distribution requirements. |
| nvidia-cuda-runtime-cu12 12.9.79 | cudart64_12.dll. Attachment A names cudart.dll (594). | Runtime family listed; same version-name inference and conditions. |
| nvidia-cuda-nvrtc-cu12 12.9.86 | nvrtc64_120_0.dll, nvrtc-builtins64_129.dll, nvrtc64_120_0.alt.dll. Attachment A names nvrtc.dll/nvrtc-builtins.dll (809). | Standard families listed; alternate .alt.dll not expressly identified. FLAG: establish coverage or exclude it after dependency verification. |
| nvidia-cudnn-cu12 9.24.0.43 | cudnn64_9.dll plus cudnn_adv64_9, cudnn_cnn64_9, cudnn_engines_precompiled64_9, cudnn_engines_runtime_compiled64_9, cudnn_engines_tensor_ir64_9, cudnn_ext64_9, cudnn_graph64_9, cudnn_heuristic64_9, cudnn_ops64_9 DLLs. | FLAG: supplement section 2 (line 148) names cudnn64_7.dll, .so/.h and cudnn.lib; it does not establish permission for this cuDNN 9 Windows set. Obtain applicable terms/clarification before CUDA publication. |

SDK distribution requirements are in section 1.1.2 for the three CUDA packages and 1.2 for cuDNN: material application functionality, application-only SDK access, consistent downstream terms, protection of NVIDIA rights, and compliance/enforcement obligations. Utterleaf supplies material dictation functionality and app-local DLLs, but these facts alone do not establish all downstream contractual conditions. No NVIDIA sample modifications were identified. Retain proprietary notices; do not apply Apache/LGPL permissions to NVIDIA DLLs. The generator's blanket 'redistributable ... per its EULA' sentence remains unsubstantiated for this candidate and must be qualified/resolved before publication. Publisher decision: obtain applicable coverage and distribution terms, or release without bundled NVIDIA components after a separately verified build.

### Hosted workflow review

Reviewed staged .github/workflows/build.yml against packaging/build.ps1, packaging/utterleaf.spec and pyproject.toml. Windows creates the required .venv, installs dev/PyInstaller, tests, invokes the build (which checks native exit codes and collects notices), runs frozen help, and uploads the CPU zip. No CUDA opt-in is set; no release publishing is implemented. Linux uses Ubuntu system Python (3.12, not 3.14) with matching Tk/Xvfb; macOS requests Homebrew Python/Tk 3.14 and PortAudio. These are source-test jobs, not macOS/Linux packaged releases.

FLAG: hosted jobs have never executed. Device doctor is continue-on-error and therefore not a release gate; Windows runs only --help as its mandatory frozen smoke, not tests/smoke_release.py. Package versions are unpinned, so future hosted dependency closure/wheels may differ from this local candidate. The collector fails on missing curated packages/license-file declarations, but it does not detect every newly added transitive dependency or eliminate incomplete fallback texts. CUDA extras omit explicit NVRTC although the CUDA spec requires it; the replacement instructions above account for this. No claim of hosted success or deterministic rebuild is made.

## GitHub surface

Description: Local push-to-talk dictation for Windows. Hold Ctrl+Win, speak, and paste clean text into any app.

Topics: dictation, speech-to-text, whisper, faster-whisper, push-to-talk, offline, privacy, windows, python

## Publish flow (after first-commit approval)

1. Resolve the compliance flags above before publishing binaries. Create an empty public GitHub repository without generated README/license/gitignore. Commit the staged tree with `git commit -m "Prepare Utterleaf 0.2.2 for public release"`, add the chosen repository URL as origin, and push main.
2. Signing is a manual pre-publish step. If signing is chosen, sign the intended executables before making the zip, verify signatures, and regenerate their SHA256SUMS.txt because signing changes hashes. The existing checksums can be uploaded as-is only for the unchanged unsigned executables verified here.
3. For the unchanged unsigned build, run from the repo root:

```powershell
Compress-Archive -Path artifacts\release-0.2.2-candidate\Utterleaf -DestinationPath artifacts\release-0.2.2-candidate\Utterleaf-0.2.2-windows-x64-cuda.zip
Copy-Item artifacts\release-0.2.2-candidate\Utterleaf\SHA256SUMS.txt artifacts\release-0.2.2-candidate\SHA256SUMS.txt
Get-FileHash artifacts\release-0.2.2-candidate\Utterleaf-0.2.2-windows-x64-cuda.zip -Algorithm SHA256 | ForEach-Object { "$($_.Hash.ToLower())  Utterleaf-0.2.2-windows-x64-cuda.zip" } | Set-Content -Encoding ascii artifacts\release-0.2.2-candidate\Utterleaf-0.2.2-windows-x64-cuda.zip.sha256
```

4. Tag the approved release commit with `git tag -a v0.2.2 -m "Utterleaf 0.2.2"` and `git push origin v0.2.2`. CI tests source installs on Windows, macOS, and Linux and produces a separate Windows CPU artifact; it does not publish a release or replace the verified local CUDA build.
5. Create a draft GitHub Release for v0.2.2. Upload the CUDA zip, SHA256SUMS.txt as-is, and the separate zip checksum. SHA256SUMS.txt hashes the three extracted executables, not the zip. Include any source/compliance materials required when resolving the flags. Verify extraction and checksums, then publish the draft.

## Draft release notes

Utterleaf 0.2.2 brings local push-to-talk dictation to Windows. Hold Ctrl+Win, speak, and release to paste clean text into the focused app.

- Fixed Windows pill corner clipping and long captions in the macOS/Linux Tk indicator.
- Fixed contractions and sentence spacing, including consecutive long recordings and dictation into Codex.
- Improved Linux paste selection and macOS/Linux startup paths.
- Removed PyAV/FFmpeg and its GPL codec payload from the Windows bundle.
- Added automatic third-party notices and license collection to builds.

Download and extract the entire Windows x64 CUDA zip, then run Utterleaf/utterleaf.exe. NVIDIA acceleration is optional; CPU processing is available. The first run downloads the speech model, after which dictation stays local. Use utterleaf-cli.exe --doctor for diagnostics or --download-model to fetch the model in advance.

This build is unsigned and Windows SmartScreen may show a warning. SHA256SUMS.txt verifies the extracted executables; the separate .zip.sha256 file verifies the download. Third-party notices and license texts are included in the archive.
