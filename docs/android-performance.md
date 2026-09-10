# Android responsiveness and acceleration

Status: initial source audit, 10 September 2026. This is a measurement and
implementation plan, not a claim of hardware acceleration or completed device QA.

## Findings and priorities

| Priority | Evidence | Next acceptance check |
| --- | --- | --- |
| First | `VoiceSession` can finish capture at its limit without a Stop tap. The old text-only callback left `VoicePanel` in capture mode during inference. | Typed capture status now drives the processing controls. Run the new emulator regression for automatic completion and stale callbacks before merging. |
| First | `bridge.cpp` loads and frees a Whisper context for every take. Model loading is part of every post-recording wait. | Measure model load separately from decode with public test audio. Compare cold and repeated takes before deciding whether a bounded model cache is worthwhile. |
| Next | Native inference uses four CPU threads and explicitly disables GPU. | Benchmark thread counts on physical devices, including thermal throttling and keyboard responsiveness during a take. More threads are not automatically faster. |
| Next | Capture reserves 120 seconds of float audio, then copies the used portion into another array and into native storage. | Measure peak memory for short and long takes. Evaluate bounded buffer growth without adding allocation jitter or weakening cleanup. |
| Next | Model selection and readiness use small private-file metadata checks; imports perform full verification on a worker. | Measure slow-storage UI stalls before moving more work off the main thread. Preserve atomic selection and the shared work lease. |

The scoped Aden search was checked against `VoiceSession`, `VoicePanel`,
`NativeEngine`, and the native bridge. This is not a whole-repository dead-code
audit. JNI names, manifest components and framework callbacks are entry points
even when a heuristic graph reports no callers.

## Hardware paths

The current release is CPU-only. The pinned
[whisper.cpp source](https://github.com/ggml-org/whisper.cpp/blob/2eeeba56e9edd762b4b38467bab96c2517163158/README.md#vulkan-gpu-support)
includes Vulkan support. A separate Android Vulkan build experiment is the first
GPU candidate because it can retain the existing reviewed GGML model format.
Android packaging, driver compatibility, fallback and actual device performance
remain unverified. Do not merely flip `use_gpu` in the shipping CPU build.

[Google's May 2026 Tensor SDK Beta announcement](https://developers.googleblog.com/google-tensor-sdk-beta-with-litert/)
lists the Pixel 10 family as supported. It does not establish Pixel 8 Pro support.
Older documentation saying all Pixel support is “coming soon” is outdated.
[LiteRT's current NPU path](https://developers.google.com/edge/litert/next/npu)
requires compatible models and vendor runtimes. Existing GGML imports cannot be
passed directly to that runtime. Treat conversion, operator coverage, model
integrity, redistribution and standalone delivery as separate gates; preserve
operation without a Google account or mandatory Play services.

## Measurement contract

- Use public, fixed audio fixtures. Record only timings, model identifier, backend,
  build and device details; never record real users' speech or typed text.
- Separate mic opening, model loading, inference, result delivery and insertion.
  Compare cold start and repeated takes of short, medium and near-limit duration.
- Measure median and tail latency, peak memory, sustained heat/battery behavior,
  transcription correctness, cancellation latency and UI frame responsiveness.
- Test CPU baseline and candidate accelerator on physical Pixel, Snapdragon and
  MediaTek devices before claiming broad support. Emulator timings are not phone
  benchmarks. Unsupported acceleration must leave a working CPU path.
- Any cache must separate model weights from per-take decoder state, invalidate on
  replacement/deletion, handle memory pressure and have an explicit eviction
  policy. Never retain transcripts or capture buffers as a speed optimization.

## State and resource review

Exercise permission denied, missing model, lease busy, mic opening failure, no
samples, short/silent take, explicit Stop, automatic limit, processing failure,
cancel, hide/detach, result review, edit, insertion rejection and preview expiry.
Verify no stale result or status can affect the next take, no microphone remains
owned after cancellation, and no delayed key repeat survives a panel reset.

Prefer explicit state and resource ownership over compact but opaque code. Remove
unused code only after checking source references, native/framework entry points
and appropriate tests. Do not equate fewer lines with lower latency or security.
