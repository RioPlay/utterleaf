# What people want from offline dictation

Research date: September 8, 2026. This is a qualitative review of public user
requests, first-person experiences, and project issue reports. It is not a
representative survey or a ranking of competing products. Search results in
this category contain many developer promotions; product marketing, unsupported
accuracy numbers, and accusations about competitors are not treated as facts.

## Findings and their implications for Utterleaf

| Need | Evidence | Product implication |
| --- | --- | --- |
| Minimal physical effort | A Linux user describes multi-key shortcuts and repeated manual copy/paste steps as barriers when they cannot readily use their hands. They specifically ask for a single-key shortcut. [First-person accessibility report](https://www.reddit.com/r/linuxmint/comments/1qzy156/speech_to_text_software_solved/) | Preserve one-key toggle operation; make it easy to discover. Recovery should also be callable from a desktop shortcut. Manual recovery is a safety fallback, not an adequate replacement for reliable direct delivery. |
| Useful speed on existing hardware | The same user reports that several local options were impractical on an older computer, and that a different model improved the speed/accuracy balance. This is one person's experience, not a model benchmark. [Hardware experience](https://www.reddit.com/r/linuxmint/comments/1qzy156/speech_to_text_software_solved/) | Benchmark available engines on ordinary CPU laptops, including cold start and short utterances. Do not select the default from accuracy alone or assume a GPU. |
| Correct delivery and honest feedback | Handy issue #502 reports old clipboard content appearing instead of dictated text. A separate issue reports a history-copy success indication despite clipboard failure. [Delivery report](https://github.com/cjpais/Handy/issues/502), [copy feedback report](https://github.com/cjpais/Handy/issues/2010) | Treat insertion and clipboard behavior as core product quality. Keep a small recovery path and test success/failure reporting. A recovery button does not resolve the underlying clipboard timing problem. |
| Control over rewriting | A writer reports wanting their dictated language preserved rather than reshaped. The source is a wearable transcription discussion, so applying this preference to desktop dictation is an inference. [Writer's feedback](https://www.reddit.com/r/OmiAI/comments/1qkh3mr/2_questions_is_there_any_way_to_get_the/) | Offer explicit unchanged-model-output behavior. Turning off filler removal alone is insufficient if grammar, commands, vocabulary, or sentence joining still modify the result. |
| Privacy that covers the whole workflow | A user asks whether audio ever leaves the device and specifically requests no automatic audio/transcript storage. They distinguish this from a cloud service's privacy-mode label. [Privacy request](https://www.reddit.com/r/vibecodingcommunity/comments/1ufq3y2/best_ondevice_voice_dictation_app_for_maciphone/) | Keep transcription and cleanup local; explain downloads and retention separately. Avoid quietly adding a permanent history in the name of recovery. |
| Accessible, dependable desktop integration | Current Handy reports include overlay overflow above 100% accessibility text size, microphone capture failures, GPU crashes, and Wayland helper mismatches. These reports identify test scenarios, not failure rates or a verdict on the product. [Primary issue tracker](https://github.com/cjpais/Handy/issues) | Add reference-device and editor matrices, display scaling checks, and hardware fallback checks before expanding features. |
| Silence should stay silent | whisper.cpp has a report of generated text during silence. It involves another inference stack and a particular model, so it does not establish that Utterleaf has the same defect. [Primary engine report](https://github.com/ggml-org/whisper.cpp/issues/1724) | Evaluate quiet speech, background noise, and silence separately. Avoid fixing false positives with aggressive filters that delete softly spoken words. |

## Implemented from this research

1. **Explicit text fidelity.** Vocabulary now has a **Clean up dictated text**
   switch. Off means no Utterleaf command interpretation, vocabulary replacement,
   grammar cleanup, or added sentence punctuation/capitalization. Preview, live
   delivery, config persistence, and the text CLI honor it. The label explains
   that keeping model output does not guarantee perfect recognition.

2. **Short-lived recovery.** The tray has **Copy last dictation (2 min)** and
   **Forget last dictation**. One latest output is kept in memory, replaced by the
   next, and cleared on expiry, Forget, or quit. Expiry also clears the old edit
   context. Failed delivery remains recoverable without decoding again. Failed
   copying reports failure and leaves the slot available for retry. Nothing in
   this feature writes audio or text to a history file. Deliberate copying puts
   text on the system clipboard, which has its own retention behavior.

3. **Accessible recovery commands.** `--copy-last` and `--forget-last` can be
   bound to desktop shortcuts and work with a running no-tray instance. Existing
   F8 plus toggle mode remains the simple one-key recording setup.

4. **Shortcut validation.** Unsupported function keys now produce a useful
   validation error. Esc cannot be assigned as the recording key because the
   listener reserves it for cancellation. Previously that setting could save
   successfully even though it could never start recording.

## Next priorities

1. **Delivery reliability:** verify actual results in browser, native, rich-text,
   terminal, and elevated fields. Preserve rich clipboard formats and investigate
   restoration timing; keep recovery until every supported path has evidence.
2. **Measured model choice:** compare recognition quality and p50/p95 latency on
   named CPU reference devices. Include names, numbers, multilingual text,
   negation, silence, and quiet speech. Model popularity is not sufficient
   evidence to replace the engine or change the default.
3. **Uncomplicated setup:** clear model status, interrupted-download recovery,
   microphone permissions and device changes, keyboard-only setup, and packaging.
4. **Accessibility:** a real screen-reader and high-DPI review, plus fewer actions
   required for common tasks. Use those results to decide whether the desktop
   shell needs replacing while retaining the speech pipeline.

The research supports improving the dictation loop first. It does not establish
demand for a bundled chat assistant, engagement statistics, meeting workspace,
cloud account, or permanent recording library in Utterleaf.

## Validation and limits

The complete test set passes with **289 passed, 1 skipped** when Tk tests run
first. The skip is a Windows privilege limitation in a Linux symlink test. New
coverage includes literal command phrases in transcript mode, preview fidelity,
config round-tripping, stale recovery timers, expiry, forgetting, failed copy,
failed-delivery recovery, and shortcut validation.

The default test order exposed a Tk resource-initialization problem in this
Windows environment: six UI tests skip with a `combobox.tcl` load error. They
pass in isolation and when run first in the same complete suite. This remains
a test-isolation investigation; it is not evidence of an application packaging
fix. Settings run in their own process in the application.

Updated real Tk screenshots were reviewed for the Vocabulary, Help, and Engine
pages. No live microphone recording, external-app typing, or end-to-end accuracy
benchmark was performed during this research pass.
