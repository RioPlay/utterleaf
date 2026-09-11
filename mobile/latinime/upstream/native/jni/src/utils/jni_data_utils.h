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

// Utterleaf modification: validate ngram and Unicode header inputs before native copies.
#ifndef LATINIME_JNI_DATA_UTILS_H
#define LATINIME_JNI_DATA_UTILS_H

#include <vector>

#include "defines.h"
#include "dictionary/header/header_read_write_utils.h"
#include "dictionary/interface/dictionary_header_structure_policy.h"
#include "dictionary/property/ngram_context.h"
#include "dictionary/property/word_property.h"
#include "jni.h"
#include "utils/char_utils.h"

namespace latinime {

class JniDataUtils {
 public:
    // Utterleaf: serialized words cannot contain the array terminator or padding.
    // U+0000 and surrogate values retain the upstream code-point representation.
    static bool isValidWordCodePoints(const int *codePoints, const int length,
            const bool allowLeadingBos = true) {
        for (int i = 0; i < length; ++i) {
            const int c = codePoints[i];
            if (c < 0 || c == 0x1F || (c > 0x10FFFF
                    && !(allowLeadingBos && i == 0
                            && c == CODE_POINT_BEGINNING_OF_SENTENCE))) return false;
        }
        return true;
    }

    static void jintarrayToVector(JNIEnv *env, jintArray array, std::vector<int> *const outVector) {
        if (!array) {
            outVector->clear();
            return;
        }
        const jsize arrayLength = env->GetArrayLength(array);
        outVector->resize(arrayLength);
        env->GetIntArrayRegion(array, 0 /* start */, arrayLength, outVector->data());
    }

    // Disk header reader capacities, inclusive; count is an Utterleaf resource policy.
    static constexpr int MAX_HEADER_KEY_CODE_POINTS = 256;
    static constexpr int MAX_HEADER_VALUE_CODE_POINTS = 2048;
    static constexpr int MAX_HEADER_ATTRIBUTE_COUNT = 256;
    static bool readHeaderString(JNIEnv *env, jstring text, const int maxCodePoints,
            std::vector<int> *outCodePoints);
    // Standard UTF-8 for POSIX paths, matching Java File (not JNI modified UTF-8).
    static bool readFilePath(JNIEnv *env, jstring path, std::vector<char> *outPath);
    static DictionaryHeaderStructurePolicy::AttributeMap constructAttributeMap(JNIEnv *env,
            jobjectArray attributeKeyStringArray, jobjectArray attributeValueStringArray);

    static void outputCodePoints(JNIEnv *env, jintArray intArrayToOutputCodePoints, const int start,
            const int maxLength, const int *const codePoints, const int codePointCount,
            const bool needsNullTermination) {
        const int codePointBufSize = std::min(maxLength, codePointCount);
        int outputCodePonts[codePointBufSize];
        int outputCodePointCount = 0;
        for (int i = 0; i < codePointBufSize; ++i) {
            const int codePoint = codePoints[i];
            int codePointToOutput = codePoint;
            if (!CharUtils::isInUnicodeSpace(codePoint)) {
                if (codePoint == CODE_POINT_BEGINNING_OF_SENTENCE) {
                    // Just skip Beginning-of-Sentence marker.
                    continue;
                }
                codePointToOutput = CODE_POINT_REPLACEMENT_CHARACTER;
            } else if (codePoint >= 0x01 && codePoint <= 0x1F) {
                // Control code.
                codePointToOutput = CODE_POINT_REPLACEMENT_CHARACTER;
            }
            outputCodePonts[outputCodePointCount++] = codePointToOutput;
        }
        env->SetIntArrayRegion(intArrayToOutputCodePoints, start, outputCodePointCount,
                outputCodePonts);
        if (needsNullTermination && outputCodePointCount < maxLength) {
            env->SetIntArrayRegion(intArrayToOutputCodePoints, start + outputCodePointCount,
                    1 /* len */, &CODE_POINT_NULL);
        }
    }

    static bool isValidNgramContext(JNIEnv *env, jobjectArray prevWordCodePointArrays,
            jbooleanArray isBeginningOfSentenceArray, const size_t prevWordCount) {
        if (env->ExceptionCheck() || prevWordCount > MAX_PREV_WORD_COUNT_FOR_N_GRAM
                || !prevWordCodePointArrays || !isBeginningOfSentenceArray) return false;
        if (env->GetArrayLength(prevWordCodePointArrays) < static_cast<jsize>(prevWordCount)
                || env->GetArrayLength(isBeginningOfSentenceArray)
                        < static_cast<jsize>(prevWordCount)) return false;
        for (size_t i = 0; i < prevWordCount; ++i) {
            jintArray word = static_cast<jintArray>(env->GetObjectArrayElement(
                    prevWordCodePointArrays, i));
            if (env->ExceptionCheck()) return false;
            // Null rows represent unavailable previous words in the Java context contract.
            if (!word) continue;
            const jsize length = env->GetArrayLength(word);
            env->DeleteLocalRef(word);
            if (env->ExceptionCheck() || length > MAX_WORD_LENGTH) return false;
        }
        return true;
    }

    static NgramContext constructNgramContext(JNIEnv *env, jobjectArray prevWordCodePointArrays,
            jbooleanArray isBeginningOfSentenceArray, const size_t prevWordCount,
            bool *validCodePoints = nullptr) {
        if (validCodePoints) *validCodePoints = true;
        if (!isValidNgramContext(env, prevWordCodePointArrays,
                isBeginningOfSentenceArray, prevWordCount)) {
            if (!env->ExceptionCheck()) {
                jclass exceptionClass = env->FindClass("java/lang/IllegalArgumentException");
                if (exceptionClass) {
                    env->ThrowNew(exceptionClass, "Invalid native ngram context shape");
                    env->DeleteLocalRef(exceptionClass);
                }
            }
            return NgramContext();
        }
        int prevWordCodePoints[MAX_PREV_WORD_COUNT_FOR_N_GRAM][MAX_WORD_LENGTH] = {};
        int prevWordCodePointCount[MAX_PREV_WORD_COUNT_FOR_N_GRAM] = {};
        bool isBeginningOfSentence[MAX_PREV_WORD_COUNT_FOR_N_GRAM] = {};
        for (size_t i = 0; i < prevWordCount; ++i) {
            prevWordCodePointCount[i] = 0;
            isBeginningOfSentence[i] = false;
            jintArray prevWord = (jintArray)env->GetObjectArrayElement(prevWordCodePointArrays, i);
            if (env->ExceptionCheck()) return NgramContext();
            if (!prevWord) {
                continue;
            }
            jsize prevWordLength = env->GetArrayLength(prevWord);
            if (prevWordLength > MAX_WORD_LENGTH) {
                env->DeleteLocalRef(prevWord);
                if (!env->ExceptionCheck()) {
                    jclass exceptionClass = env->FindClass("java/lang/IllegalArgumentException");
                    if (exceptionClass) {
                        env->ThrowNew(exceptionClass, "Invalid native ngram word length");
                        env->DeleteLocalRef(exceptionClass);
                    }
                }
                return NgramContext();
            }
            env->GetIntArrayRegion(prevWord, 0, prevWordLength, prevWordCodePoints[i]);
            env->DeleteLocalRef(prevWord);
            if (env->ExceptionCheck()) return NgramContext();
            if (!isValidWordCodePoints(prevWordCodePoints[i], prevWordLength)) {
                // Suggestion requests can contain arbitrary host text: report unavailable
                // without throwing into the worker, and never decode a fallback context.
                if (validCodePoints) {
                    *validCodePoints = false;
                    return NgramContext();
                }
                jclass exceptionClass = env->FindClass("java/lang/IllegalArgumentException");
                if (exceptionClass) {
                    env->ThrowNew(exceptionClass, "Invalid native ngram word code points");
                    env->DeleteLocalRef(exceptionClass);
                }
                return NgramContext();
            }
            prevWordCodePointCount[i] = prevWordLength;
            jboolean isBeginningOfSentenceBoolean = JNI_FALSE;
            env->GetBooleanArrayRegion(isBeginningOfSentenceArray, i, 1 /* len */,
                    &isBeginningOfSentenceBoolean);
            if (env->ExceptionCheck()) return NgramContext();
            isBeginningOfSentence[i] = isBeginningOfSentenceBoolean == JNI_TRUE;
        }
        return NgramContext(prevWordCodePoints, prevWordCodePointCount, isBeginningOfSentence,
                prevWordCount);
    }

    static void putBooleanToArray(JNIEnv *env, jbooleanArray array, const int index,
            const jboolean value) {
        env->SetBooleanArrayRegion(array, index, 1 /* len */, &value);
    }

    static void putIntToArray(JNIEnv *env, jintArray array, const int index, const int value) {
        env->SetIntArrayRegion(array, index, 1 /* len */, &value);
    }

    static void putFloatToArray(JNIEnv *env, jfloatArray array, const int index,
            const float value) {
        env->SetFloatArrayRegion(array, index, 1 /* len */, &value);
    }

    static void outputWordProperty(JNIEnv *const env, const WordProperty &wordProperty,
            jintArray outCodePoints, jbooleanArray outFlags, jintArray outProbabilityInfo,
            jobject outNgramPrevWordsArray, jobject outNgramPrevWordIsBeginningOfSentenceArray,
            jobject outNgramTargets, jobject outNgramProbabilities, jobject outShortcutTargets,
            jobject outShortcutProbabilities);

 private:
    DISALLOW_IMPLICIT_CONSTRUCTORS(JniDataUtils);

    static const int CODE_POINT_REPLACEMENT_CHARACTER;
    static const int CODE_POINT_NULL;
};
} // namespace latinime
#endif // LATINIME_JNI_DATA_UTILS_H
