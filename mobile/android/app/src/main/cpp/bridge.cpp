#include <jni.h>
#include <atomic>
#include <algorithm>
#include <memory>
#include <string>
#include <vector>
#include "whisper.h"

// A process-wide Java lease serializes inference and model replacement.
static std::atomic<bool> cancelled{false};
static bool abort_decode(void *) { return cancelled.load(); }
static void quiet_log(enum ggml_log_level, const char *, void *) {}
extern "C" JNIEXPORT void JNICALL
Java_org_utterleaf_voice_NativeEngine_reset(JNIEnv *, jobject) { cancelled.store(false); }
extern "C" JNIEXPORT void JNICALL
Java_org_utterleaf_voice_NativeEngine_cancel(JNIEnv *, jobject) { cancelled.store(true); }

extern "C" JNIEXPORT jbyteArray JNICALL
Java_org_utterleaf_voice_NativeEngine_decode(JNIEnv *env, jobject, jstring model, jfloatArray input) {
    try {
        const auto count = env->GetArrayLength(input);
        if (count <= 0 || count > 16000 * 120 || cancelled.load()) return nullptr;
        const char *raw = env->GetStringUTFChars(model, nullptr);
        if (!raw) return nullptr;
        std::string path(raw);
        env->ReleaseStringUTFChars(model, raw);
        whisper_log_set(quiet_log, nullptr);
        auto cp = whisper_context_default_params();
        cp.use_gpu = false;
        std::unique_ptr<whisper_context, decltype(&whisper_free)> ctx(
            whisper_init_from_file_with_params(path.c_str(), cp), whisper_free);
        if (!ctx || cancelled.load()) return nullptr;
        std::vector<float> samples(count);
        env->GetFloatArrayRegion(input, 0, count, samples.data());
        if (env->ExceptionCheck()) return nullptr;
        auto p = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
        p.n_threads = 4;
        p.language = "en";
        p.translate = false;
        p.no_context = true;
        p.no_timestamps = true;
        p.print_realtime = p.print_progress = p.print_timestamps = p.print_special = false;
        p.abort_callback = abort_decode;
        p.abort_callback_user_data = nullptr;
        const int result = whisper_full(ctx.get(), p, samples.data(), count);
        std::fill(samples.begin(), samples.end(), 0.0f);
        if (result != 0 || cancelled.load()) return nullptr;
        std::string text;
        for (int i = 0; i < whisper_full_n_segments(ctx.get()); ++i)
            text += whisper_full_get_segment_text(ctx.get(), i);
        auto bytes = env->NewByteArray(static_cast<jsize>(text.size()));
        if (bytes) env->SetByteArrayRegion(bytes, 0, text.size(), reinterpret_cast<const jbyte *>(text.data()));
        std::fill(text.begin(), text.end(), '\0');
        return bytes;
    } catch (...) {
        env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), "Local speech engine could not process this take");
        return nullptr;
    }
}
