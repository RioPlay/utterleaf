# Dictation regression investigation

## Findings

The installed Windows CPU release requested GPU in its config, but recent logs
showed `small.en` loading on CPU/int8 after acceleration was unavailable. The
development environment on the same RTX 3090 machine has the NVIDIA libraries
and selects CUDA. A device preference cannot install missing runtime libraries.
The speech backend remains faster-whisper/CTranslate2; this is a device fallback,
not evidence of a different speech model.

A local 10.335-second synthetic English sample, small.en, default beam size 5:

| Device | Load | First decode | Warm decodes |
| --- | --- | --- | --- |
| CPU/int8 | 1.091 s | 1.923 s | 1.626 s, 1.594 s |
| RTX 3090/float16 | 0.677 s | 0.779 s | 0.270 s, 0.272 s |

Reproduce with `python scripts/benchmark_dictation.py sample.wav`. Input must be
16 kHz mono PCM16. Uses cached models only, prints no transcript, and refuses to
present CPU fallback as a GPU result. These are inference timings on one synthetic
sample, not end-to-end latency, human accuracy, or percentile measurements.

## Implemented fixes

- Comma-separated list items preserve multiword phrases and internal conjunctions.
- Explicit `bullet point … next bullet point …` boundaries support unambiguous
  phrases. `end list` returns to prose. Ordinary text with cleanup off stays literal.
- Recording indicator shows remaining minutes/seconds, including alongside live
  previews, with a final-ten-seconds warning. Stale ticks cannot replace a newer status.
- Local logs separate decode, formatting, and delivery durations without audio,
  transcript, or field contents. Decode includes preparation/model access; delivery
  includes the pre-paste field check and clipboard handling, not proof of insertion.
- Typing and Speaking mascots now appear on Vocabulary and Voice commands pages.
  Other expressions already accompany normal microphone-check states.

## Next priorities

1. Ship and test an optional Windows NVIDIA runtime package or CUDA build, with
   the actual active device and fallback reason visible. Keep the small CPU download.
2. Extend verified edit adapters to browser/rich-text fields. The recent native-Edit-only
   adapter made follow-up commands less convenient in those apps: revised text is
   copied for manual replacement. Do not claim that inline list fixes restore this.
3. Add a user-reported dictation corpus and editor matrix for list structure,
   corrections, names, punctuation, and cross-take commands. Avoid guessing that
   every short phrase is several one-word items.
4. Benchmark beam 1 versus 5 and distilled models for both human accuracy and latency
   before changing defaults. GPU inference with CPU capture/formatting is the first
   target; duplicate CPU/GPU decoding adds work without demonstrated latency benefit.
5. Evaluate optional local semantic formatting only against meaning-preservation and
   latency tests. Rule-based cleanup cannot reliably interpret every natural request.

Current backend guidance: [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
documents CUDA/cuDNN requirements and GPU/CPU execution; [CTranslate2 performance
tips](https://opennmt.net/CTranslate2/performance.html) explain precision and decoding
tradeoffs. Bulk-transcription throughput benchmarks do not establish interactive
dictation latency.
