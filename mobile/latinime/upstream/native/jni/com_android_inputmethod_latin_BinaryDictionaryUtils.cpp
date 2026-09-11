/*
 * Copyright (C) 2014 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// Utterleaf modification: validate and bound dictionary metadata and score inputs.
#define LOG_TAG "LatinIME: jni: BinaryDictionaryUtils"

#include "com_android_inputmethod_latin_BinaryDictionaryUtils.h"
#include <memory>
#include <new>
#include "suggest/policyimpl/utils/edit_distance.h"

#include "defines.h"
#include "dictionary/utils/dict_file_writing_utils.h"
#include "jni.h"
#include "jni_common.h"
#include "utils/autocorrection_threshold_utils.h"
#include "utils/char_utils.h"
#include "utils/jni_data_utils.h"
#include "utils/time_keeper.h"

namespace latinime {

static jboolean latinime_BinaryDictionaryUtils_createEmptyDictFile(JNIEnv *env, jclass clazz,
        jstring filePath, jlong dictVersion, jstring locale, jobjectArray attributeKeyStringArray,
        jobjectArray attributeValueStringArray) {
    // Utterleaf: malformed metadata must never reach file creation.
    if (env->ExceptionCheck()) return false;
    std::vector<char> pathStorage;
    if (!JniDataUtils::readFilePath(env, filePath, &pathStorage)) return false;
    const char *const filePathChars = pathStorage.data();

    std::vector<int> localeCodePoints;
    if (!JniDataUtils::readHeaderString(env, locale,
            JniDataUtils::MAX_HEADER_VALUE_CODE_POINTS, &localeCodePoints)) return false;
    DictionaryHeaderStructurePolicy::AttributeMap attributeMap =
            JniDataUtils::constructAttributeMap(env, attributeKeyStringArray,
                    attributeValueStringArray);
    if (env->ExceptionCheck()) return false;
    return DictFileWritingUtils::createEmptyDictFile(filePathChars, static_cast<int>(dictVersion),
            localeCodePoints, &attributeMap);
}

static jfloat latinime_BinaryDictionaryUtils_calcNormalizedScore(JNIEnv *env, jclass clazz,
        jintArray before, jintArray after, jint score) {
    if (env->ExceptionCheck() || !before || !after || score <= 0) return 0.0f;
    const jsize beforeLength = env->GetArrayLength(before);
    if (env->ExceptionCheck()) return 0.0f;
    const jsize afterLength = env->GetArrayLength(after);
    if (env->ExceptionCheck() || beforeLength == 0 || afterLength == 0
            || !EditDistance::supportsLengths(beforeLength, afterLength)) return 0.0f;
    std::unique_ptr<int[]> beforeCodePoints(new (std::nothrow) int[beforeLength]);
    std::unique_ptr<int[]> afterCodePoints(new (std::nothrow) int[afterLength]);
    if (!beforeCodePoints || !afterCodePoints) return 0.0f;
    env->GetIntArrayRegion(before, 0, beforeLength, beforeCodePoints.get());
    if (env->ExceptionCheck()) return 0.0f;
    env->GetIntArrayRegion(after, 0, afterLength, afterCodePoints.get());
    if (env->ExceptionCheck()) return 0.0f;
    // String.codePoints semantics include U+0000 and unpaired UTF-16 surrogates. Reject only
    // values outside that range; negative values would index before CharUtils' base table.
    for (int i = 0; i < beforeLength; ++i) {
        if (beforeCodePoints[i] < 0 || beforeCodePoints[i] > 0x10FFFF) return 0.0f;
    }
    for (int i = 0; i < afterLength; ++i) {
        if (afterCodePoints[i] < 0 || afterCodePoints[i] > 0x10FFFF) return 0.0f;
    }
    return AutocorrectionThresholdUtils::calcNormalizedScore(beforeCodePoints.get(), beforeLength,
            afterCodePoints.get(), afterLength, score);
}

static int latinime_BinaryDictionaryUtils_setCurrentTimeForTest(JNIEnv *env, jclass clazz,
        jint currentTime) {
    if (currentTime >= 0) {
        TimeKeeper::startTestModeWithForceCurrentTime(currentTime);
    } else {
        TimeKeeper::stopTestMode();
    }
    TimeKeeper::setCurrentTime();
    return TimeKeeper::peekCurrentTime();
}

static const JNINativeMethod sMethods[] = {
    {
        const_cast<char *>("createEmptyDictFileNative"),
        const_cast<char *>(
                "(Ljava/lang/String;JLjava/lang/String;[Ljava/lang/String;[Ljava/lang/String;)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionaryUtils_createEmptyDictFile)
    },
    {
        const_cast<char *>("calcNormalizedScoreNative"),
        const_cast<char *>("([I[II)F"),
        reinterpret_cast<void *>(latinime_BinaryDictionaryUtils_calcNormalizedScore)
    },
    {
        const_cast<char *>("setCurrentTimeForTestNative"),
        const_cast<char *>("(I)I"),
        reinterpret_cast<void *>(latinime_BinaryDictionaryUtils_setCurrentTimeForTest)
    }
};

int register_BinaryDictionaryUtils(JNIEnv *env) {
    const char *const kClassPathName = "com/android/inputmethod/latin/utils/BinaryDictionaryUtils";
    return registerNativeMethods(env, kClassPathName, sMethods, NELEMS(sMethods));
}
} // namespace latinime
