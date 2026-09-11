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

// Utterleaf modification: bound Unicode header/path input and stop output on JNI exceptions.
#include "utils/jni_data_utils.h"

#include <climits>

#include "utils/int_array_view.h"

namespace latinime {

const int JniDataUtils::CODE_POINT_REPLACEMENT_CHARACTER = 0xFFFD;
const int JniDataUtils::CODE_POINT_NULL = 0;

bool JniDataUtils::readFilePath(JNIEnv *env, jstring path, std::vector<char> *outPath) {
    if (env->ExceptionCheck()) return false;
    const auto reject = [&]() {
        if (!env->ExceptionCheck()) {
            jclass error = env->FindClass("java/lang/IllegalArgumentException");
            if (!env->ExceptionCheck()) {
                env->ThrowNew(error, "Invalid or oversized dictionary path");
                env->DeleteLocalRef(error);
            }
        }
        return false;
    };
    if (!path) return reject();
    const jsize length = env->GetStringLength(path);
    if (env->ExceptionCheck()) return false;
    if (length <= 0 || length >= PATH_MAX) return reject();
    jchar characters[PATH_MAX];
    env->GetStringRegion(path, 0, length, characters);
    if (env->ExceptionCheck()) return false;
    outPath->clear();
    outPath->reserve(PATH_MAX);
    for (jsize i = 0; i < length; ++i) {
        int codePoint = characters[i];
        if (codePoint >= 0xD800 && codePoint <= 0xDBFF) {
            if (++i >= length || characters[i] < 0xDC00 || characters[i] > 0xDFFF) return reject();
            codePoint = 0x10000 + ((codePoint - 0xD800) << 10) + characters[i] - 0xDC00;
        } else if (codePoint >= 0xDC00 && codePoint <= 0xDFFF) {
            return reject();
        }
        if (codePoint == 0) return reject();
        const int bytes = codePoint < 0x80 ? 1 : codePoint < 0x800 ? 2 : codePoint < 0x10000 ? 3 : 4;
        if (outPath->size() + bytes >= PATH_MAX) return reject();
        if (bytes == 1) outPath->push_back(static_cast<char>(codePoint));
        else {
            const int prefix = bytes == 2 ? 0xC0 : bytes == 3 ? 0xE0 : 0xF0;
            outPath->push_back(static_cast<char>(prefix | (codePoint >> (6 * (bytes - 1)))));
            for (int remaining = bytes - 2; remaining >= 0; --remaining) {
                outPath->push_back(static_cast<char>(0x80 | ((codePoint >> (6 * remaining)) & 0x3F)));
            }
        }
    }
    outPath->push_back('\0');
    return true;
}

static bool rejectHeaderInput(JNIEnv *env) {
    if (!env->ExceptionCheck()) {
        jclass error = env->FindClass("java/lang/IllegalArgumentException");
        if (!env->ExceptionCheck()) {
            env->ThrowNew(error, "Invalid or oversized dictionary header metadata");
            env->DeleteLocalRef(error);
        }
    }
    return false;
}

bool JniDataUtils::readHeaderString(JNIEnv *env, jstring text, const int maxCodePoints,
        std::vector<int> *outCodePoints) {
    if (env->ExceptionCheck()) return false;
    if (!text || maxCodePoints < 0 || maxCodePoints > MAX_HEADER_VALUE_CODE_POINTS) {
        return rejectHeaderInput(env);
    }
    const jsize length = env->GetStringLength(text);
    if (env->ExceptionCheck()) return false;
    if (length > 2 * maxCodePoints) return rejectHeaderInput(env);
    jchar characters[2 * MAX_HEADER_VALUE_CODE_POINTS];
    if (length > 0) env->GetStringRegion(text, 0, length, characters);
    if (env->ExceptionCheck()) return false;
    outCodePoints->clear();
    outCodePoints->reserve(std::min(length, maxCodePoints));
    for (jsize i = 0; i < length; ++i) {
        int codePoint = characters[i];
        if (codePoint >= 0xD800 && codePoint <= 0xDBFF) {
            if (++i >= length || characters[i] < 0xDC00 || characters[i] > 0xDFFF) {
                return rejectHeaderInput(env);
            }
            codePoint = 0x10000 + ((codePoint - 0xD800) << 10) + characters[i] - 0xDC00;
        } else if (codePoint >= 0xDC00 && codePoint <= 0xDFFF) {
            return rejectHeaderInput(env);
        }
        // Java header consumers use null-terminated arrays; embedded NUL cannot round-trip.
        if (codePoint == 0 || codePoint == 0x1F
                || outCodePoints->size() >= static_cast<size_t>(maxCodePoints)) {
            return rejectHeaderInput(env);
        }
        outCodePoints->push_back(codePoint);
    }
    return true;
}

DictionaryHeaderStructurePolicy::AttributeMap JniDataUtils::constructAttributeMap(JNIEnv *env,
        jobjectArray keys, jobjectArray values) {
    DictionaryHeaderStructurePolicy::AttributeMap attributes;
    if (env->ExceptionCheck()) return attributes;
    if (!keys || !values) { rejectHeaderInput(env); return attributes; }
    const jsize count = env->GetArrayLength(keys);
    if (env->ExceptionCheck()) return attributes;
    const jsize valueCount = env->GetArrayLength(values);
    if (env->ExceptionCheck()) return attributes;
    if (count != valueCount || count > MAX_HEADER_ATTRIBUTE_COUNT) {
        rejectHeaderInput(env); return attributes;
    }
    if (env->PushLocalFrame(8) < 0) return attributes;
    const auto read = [&]() {
        for (jsize i = 0; i < count; ++i) {
            jstring key = static_cast<jstring>(env->GetObjectArrayElement(keys, i));
            if (env->ExceptionCheck()) return;
            jstring value = static_cast<jstring>(env->GetObjectArrayElement(values, i));
            if (env->ExceptionCheck()) return;
            std::vector<int> keyPoints, valuePoints;
            if (!readHeaderString(env, key, MAX_HEADER_KEY_CODE_POINTS, &keyPoints)
                    || !readHeaderString(env, value, MAX_HEADER_VALUE_CODE_POINTS, &valuePoints)) return;
            attributes[std::move(keyPoints)] = std::move(valuePoints);
            env->DeleteLocalRef(key);
            env->DeleteLocalRef(value);
        }
    };
    read();
    env->PopLocalFrame(nullptr);
    return attributes;
}

/* static */ void JniDataUtils::outputWordProperty(JNIEnv *const env,
        const WordProperty &wordProperty, jintArray outCodePoints, jbooleanArray outFlags,
        jintArray outProbabilityInfo, jobject outNgramPrevWordsArray,
        jobject outNgramPrevWordIsBeginningOfSentenceArray, jobject outNgramTargets,
        jobject outNgramProbabilities, jobject outShortcutTargets,
        jobject outShortcutProbabilities) {
    if (env->ExceptionCheck() || env->PushLocalFrame(32) < 0) return;
    // PopLocalFrame is permitted with a pending exception; preserve the original throwable.
    const auto output = [&]() {
        const CodePointArrayView codePoints = wordProperty.getCodePoints();
        JniDataUtils::outputCodePoints(env, outCodePoints, 0 /* start */,
                MAX_WORD_LENGTH /* maxLength */, codePoints.data(), codePoints.size(),
                false /* needsNullTermination */);
        if (env->ExceptionCheck()) return;
        const UnigramProperty &unigramProperty = wordProperty.getUnigramProperty();
        const std::vector<NgramProperty> &ngrams = wordProperty.getNgramProperties();
        jboolean flags[] = {unigramProperty.isNotAWord(), unigramProperty.isPossiblyOffensive(),
                !ngrams.empty(), unigramProperty.hasShortcuts(),
                unigramProperty.representsBeginningOfSentence()};
        env->SetBooleanArrayRegion(outFlags, 0 /* start */, NELEMS(flags), flags);
        if (env->ExceptionCheck()) return;
        const HistoricalInfo &historicalInfo = unigramProperty.getHistoricalInfo();
        int probabilityInfo[] = {unigramProperty.getProbability(), historicalInfo.getTimestamp(),
                historicalInfo.getLevel(), historicalInfo.getCount()};
        env->SetIntArrayRegion(outProbabilityInfo, 0 /* start */, NELEMS(probabilityInfo),
                probabilityInfo);
        if (env->ExceptionCheck()) return;

        jclass integerClass = env->FindClass("java/lang/Integer");
        if (env->ExceptionCheck()) return;
        jmethodID intToIntegerConstructorId = env->GetMethodID(integerClass, "<init>", "(I)V");
        if (env->ExceptionCheck()) return;
        jclass arrayListClass = env->FindClass("java/util/ArrayList");
        if (env->ExceptionCheck()) return;
        jmethodID addMethodId = env->GetMethodID(arrayListClass, "add", "(Ljava/lang/Object;)Z");
        if (env->ExceptionCheck()) return;

        // Output ngrams.
        jclass intArrayClass = env->FindClass("[I");
        if (env->ExceptionCheck()) return;
        for (const auto &ngramProperty : ngrams) {
            const NgramContext *const ngramContext = ngramProperty.getNgramContext();
            jobjectArray prevWordWordCodePointsArray = env->NewObjectArray(
                    ngramContext->getPrevWordCount(), intArrayClass, nullptr);
            if (env->ExceptionCheck()) return;
            jbooleanArray prevWordIsBeginningOfSentenceArray =
                    env->NewBooleanArray(ngramContext->getPrevWordCount());
            if (env->ExceptionCheck()) return;
            for (size_t i = 0; i < ngramContext->getPrevWordCount(); ++i) {
                const CodePointArrayView codePoints = ngramContext->getNthPrevWordCodePoints(i + 1);
                jintArray prevWordCodePoints = env->NewIntArray(codePoints.size());
                if (env->ExceptionCheck()) return;
                JniDataUtils::outputCodePoints(env, prevWordCodePoints, 0 /* start */,
                        codePoints.size(), codePoints.data(), codePoints.size(),
                        false /* needsNullTermination */);
                if (env->ExceptionCheck()) return;
                env->SetObjectArrayElement(prevWordWordCodePointsArray, i, prevWordCodePoints);
                if (env->ExceptionCheck()) return;
                env->DeleteLocalRef(prevWordCodePoints);
                JniDataUtils::putBooleanToArray(env, prevWordIsBeginningOfSentenceArray, i,
                        ngramContext->isNthPrevWordBeginningOfSentence(i + 1));
                if (env->ExceptionCheck()) return;
            }
            env->CallBooleanMethod(outNgramPrevWordsArray, addMethodId, prevWordWordCodePointsArray);
            if (env->ExceptionCheck()) return;
            env->CallBooleanMethod(outNgramPrevWordIsBeginningOfSentenceArray, addMethodId,
                    prevWordIsBeginningOfSentenceArray);
            if (env->ExceptionCheck()) return;
            env->DeleteLocalRef(prevWordWordCodePointsArray);
            env->DeleteLocalRef(prevWordIsBeginningOfSentenceArray);

            const std::vector<int> *const targetWordCodePoints = ngramProperty.getTargetCodePoints();
            jintArray targetWordCodePointArray = env->NewIntArray(targetWordCodePoints->size());
            if (env->ExceptionCheck()) return;
            JniDataUtils::outputCodePoints(env, targetWordCodePointArray, 0 /* start */,
                    targetWordCodePoints->size(), targetWordCodePoints->data(),
                    targetWordCodePoints->size(), false /* needsNullTermination */);
            if (env->ExceptionCheck()) return;
            env->CallBooleanMethod(outNgramTargets, addMethodId, targetWordCodePointArray);
            if (env->ExceptionCheck()) return;
            env->DeleteLocalRef(targetWordCodePointArray);

            const HistoricalInfo &ngramHistoricalInfo = ngramProperty.getHistoricalInfo();
            int bigramProbabilityInfo[] = {ngramProperty.getProbability(),
                    ngramHistoricalInfo.getTimestamp(), ngramHistoricalInfo.getLevel(),
                    ngramHistoricalInfo.getCount()};
            jintArray bigramProbabilityInfoArray = env->NewIntArray(NELEMS(bigramProbabilityInfo));
            if (env->ExceptionCheck()) return;
            env->SetIntArrayRegion(bigramProbabilityInfoArray, 0 /* start */,
                    NELEMS(bigramProbabilityInfo), bigramProbabilityInfo);
            if (env->ExceptionCheck()) return;
            env->CallBooleanMethod(outNgramProbabilities, addMethodId, bigramProbabilityInfoArray);
            if (env->ExceptionCheck()) return;
            env->DeleteLocalRef(bigramProbabilityInfoArray);
        }

        // Output shortcuts.
        for (const auto &shortcut : unigramProperty.getShortcuts()) {
            const std::vector<int> *const targetCodePoints = shortcut.getTargetCodePoints();
            jintArray shortcutTargetCodePointArray = env->NewIntArray(targetCodePoints->size());
            if (env->ExceptionCheck()) return;
            JniDataUtils::outputCodePoints(env, shortcutTargetCodePointArray, 0 /* start */,
                    targetCodePoints->size(), targetCodePoints->data(), targetCodePoints->size(),
                    false /* needsNullTermination */);
            if (env->ExceptionCheck()) return;
            env->CallBooleanMethod(outShortcutTargets, addMethodId, shortcutTargetCodePointArray);
            if (env->ExceptionCheck()) return;
            env->DeleteLocalRef(shortcutTargetCodePointArray);
            jobject integerProbability = env->NewObject(integerClass, intToIntegerConstructorId,
                    shortcut.getProbability());
            if (env->ExceptionCheck()) return;
            env->CallBooleanMethod(outShortcutProbabilities, addMethodId, integerProbability);
            if (env->ExceptionCheck()) return;
            env->DeleteLocalRef(integerProbability);
        }
        env->DeleteLocalRef(integerClass);
        env->DeleteLocalRef(arrayListClass);
    };
    output();
    env->PopLocalFrame(nullptr);
}

} // namespace latinime
