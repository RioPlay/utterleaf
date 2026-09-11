/*
 * Copyright (C) 2009 The Android Open Source Project
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

// Utterleaf modification: validate JNI suggestion/context/word bounds and bound request allocation.
#define LOG_TAG "LatinIME: jni: BinaryDictionary"

#include "com_android_inputmethod_latin_BinaryDictionary.h"

#include <climits>
#include <cstring> // for memset()
#include <vector>

#include "defines.h"
#include "dictionary/property/unigram_property.h"
#include "dictionary/property/ngram_context.h"
#include "dictionary/property/word_property.h"
#include "dictionary/structure/dictionary_structure_with_buffer_policy_factory.h"
#include "jni.h"
#include "jni_common.h"
#include "suggest/core/dictionary/dictionary.h"
#include "suggest/core/result/suggestion_results.h"
#include "suggest/core/suggest_options.h"
#include "utils/char_utils.h"
#include "utils/int_array_view.h"
#include "utils/jni_data_utils.h"
#include "utils/log_utils.h"
#include "utils/profiler.h"
#include "utils/time_keeper.h"

namespace latinime {

class ProximityInfo;

// Utterleaf resource policy, not an upstream recognition limit: reject oversized requests
// rather than truncate a gesture. Four copied coordinate/time/id arrays total at most 64 KiB.
// This does not bound the source gesture accumulator or establish physical swipe acceptance.
static constexpr int MAX_SUGGESTION_INPUT_POINTS = 4096;
static constexpr int SUGGESTION_OPTIONS_COUNT = 5; // NativeSuggestOptions.OPTIONS_SIZE

static bool hasArrayLength(JNIEnv *env, jarray array, const jsize length) {
    return array && env->GetArrayLength(array) == length;
}

static bool hasArrayCapacity(JNIEnv *env, jarray array, const jsize length) {
    return array && env->GetArrayLength(array) >= length;
}

// Stored words support 48 code points, unlike the tap decoder's strict <48 limit.
// Exact-match queries additionally allow two input code points per stored code point for
// supported digraph expansion. Never truncate or size stack storage from JNI.
template <size_t capacity>
static bool readWord(JNIEnv *env, jintArray word, int (&codePoints)[capacity],
        jsize *length, const bool allowEmpty = false, const bool allowLeadingBos = true) {
    if (env->ExceptionCheck() || !word) return false;
    *length = env->GetArrayLength(word);
    if (env->ExceptionCheck() || static_cast<size_t>(*length) > capacity
            || (*length == 0 && !allowEmpty)) return false;
    if (*length > 0) env->GetIntArrayRegion(word, 0, *length, codePoints);
    return !env->ExceptionCheck()
            && JniDataUtils::isValidWordCodePoints(codePoints, *length, allowLeadingBos);
}

static bool canMarkBeginningOfSentence(const int *codePoints, const jsize length) {
    return length < MAX_WORD_LENGTH || codePoints[0] == CODE_POINT_BEGINNING_OF_SENTENCE;
}

// Utterleaf: a failed admitted write may have changed private GC state. All JNI data
// operations reject unavailable owners before accessing the policy; close remains available.
static Dictionary *getAvailableDictionary(jlong handle) {
    Dictionary *dictionary = reinterpret_cast<Dictionary *>(handle);
    return dictionary && dictionary->isStorageAvailable() ? dictionary : nullptr;
}

static jlong latinime_BinaryDictionary_open(JNIEnv *env, jclass clazz, jstring sourceDir,
        jlong dictOffset, jlong dictSize, jboolean isUpdatable) {
#ifdef UTTERLEAF_STORAGE_TESTING
    if (gStorageFailNextNativeOpen) { gStorageFailNextNativeOpen = false; return 0; }
#endif
    PROF_INIT;
    PROF_TIMER_START(66);
    if (env->ExceptionCheck() || dictOffset < 0 || dictOffset > INT_MAX
            || dictSize < 0 || dictSize > INT_MAX) return 0;
    std::vector<char> pathStorage;
    if (!JniDataUtils::readFilePath(env, sourceDir, &pathStorage)) return 0;
    const char *const sourceDirChars = pathStorage.data();
    StorageReadLock readLock(sourceDirChars);
    if (!readLock.valid()) return 0;
    auto generation = readLock.generation();
    DictionaryStructureWithBufferPolicy::StructurePolicyPtr dictionaryStructureWithBufferPolicy(
            DictionaryStructureWithBufferPolicyFactory::newPolicyForExistingDictFile(
                    sourceDirChars, static_cast<int>(dictOffset), static_cast<int>(dictSize),
                    isUpdatable == JNI_TRUE));
    if (!dictionaryStructureWithBufferPolicy) {
        return 0;
    }

    Dictionary *const dictionary =
            new Dictionary(env, std::move(dictionaryStructureWithBufferPolicy));
    dictionary->setStorageGeneration(std::move(generation));
    PROF_TIMER_END(66);
    return reinterpret_cast<jlong>(dictionary);
}

static jlong latinime_BinaryDictionary_createOnMemory(JNIEnv *env, jclass clazz,
        jlong formatVersion, jstring locale, jobjectArray attributeKeyStringArray,
        jobjectArray attributeValueStringArray) {
    if (env->ExceptionCheck()) return 0;
    std::vector<int> localeCodePoints;
    if (!JniDataUtils::readHeaderString(env, locale,
            JniDataUtils::MAX_HEADER_VALUE_CODE_POINTS, &localeCodePoints)) return 0;
    DictionaryHeaderStructurePolicy::AttributeMap attributeMap =
            JniDataUtils::constructAttributeMap(env, attributeKeyStringArray,
                    attributeValueStringArray);
    if (env->ExceptionCheck()) return 0;
    DictionaryStructureWithBufferPolicy::StructurePolicyPtr dictionaryStructureWithBufferPolicy =
            DictionaryStructureWithBufferPolicyFactory::newPolicyForOnMemoryDict(
                    formatVersion, localeCodePoints, &attributeMap);
    if (!dictionaryStructureWithBufferPolicy) {
        return 0;
    }
    Dictionary *const dictionary =
            new Dictionary(env, std::move(dictionaryStructureWithBufferPolicy));
    return reinterpret_cast<jlong>(dictionary);
}

static bool latinime_BinaryDictionary_flush(JNIEnv *env, jclass clazz, jlong dict,
        jstring filePath) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) return false;
    std::vector<char> pathStorage;
    if (!JniDataUtils::readFilePath(env, filePath, &pathStorage)) return false;
    const char *const filePathChars = pathStorage.data();
    return dictionary->flush(filePathChars);
}

static bool latinime_BinaryDictionary_needsToRunGC(JNIEnv *env, jclass clazz,
        jlong dict, jboolean mindsBlockByGC) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) return false;
    return dictionary->needsToRunGC(mindsBlockByGC == JNI_TRUE);
}

static bool latinime_BinaryDictionary_flushWithGC(JNIEnv *env, jclass clazz, jlong dict,
        jstring filePath) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) return false;
    std::vector<char> pathStorage;
    if (!JniDataUtils::readFilePath(env, filePath, &pathStorage)) return false;
    const char *const filePathChars = pathStorage.data();
    return dictionary->flushWithGC(filePathChars);
}

static void latinime_BinaryDictionary_close(JNIEnv *env, jclass clazz, jlong dict) {
    Dictionary *dictionary = reinterpret_cast<Dictionary *>(dict);
    if (!dictionary) return;
    delete dictionary;
}

static void latinime_BinaryDictionary_getHeaderInfo(JNIEnv *env, jclass clazz, jlong dict,
        jintArray outHeaderSize, jintArray outFormatVersion, jobject outAttributeKeys,
        jobject outAttributeValues) {
    if (env->ExceptionCheck() || !hasArrayLength(env, outHeaderSize, 1)
            || !hasArrayLength(env, outFormatVersion, 1)) return;
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) return;
    if (env->PushLocalFrame(16) < 0) return;
    const auto output = [&]() {
        jclass arrayListClass = env->FindClass("java/util/ArrayList");
        if (env->ExceptionCheck()) return;
        if (!outAttributeKeys || !outAttributeValues
                || !env->IsInstanceOf(outAttributeKeys, arrayListClass)
                || !env->IsInstanceOf(outAttributeValues, arrayListClass)) return;
        const DictionaryHeaderStructurePolicy *const headerPolicy =
                dictionary->getDictionaryStructurePolicy()->getHeaderStructurePolicy();
        // ArrayList callbacks may reenter Java and flush/reopen this dictionary. Own all
        // header data before the first callback; never retain an iterator into the live policy.
        const auto attributes = *headerPolicy->getAttributeMap();
        const int headerSize = headerPolicy->getSize();
        const int formatVersion = headerPolicy->getFormatVersionNumber();
        for (const auto &attribute : attributes) {
            if (attribute.first.size() > JniDataUtils::MAX_HEADER_KEY_CODE_POINTS
                    || attribute.second.size() > JniDataUtils::MAX_HEADER_VALUE_CODE_POINTS) return;
        }
        JniDataUtils::putIntToArray(env, outHeaderSize, 0 /* index */, headerSize);
        if (env->ExceptionCheck()) return;
        JniDataUtils::putIntToArray(env, outFormatVersion, 0 /* index */,
                formatVersion);
        if (env->ExceptionCheck()) return;
        // Output attribute map
        jmethodID addMethodId = env->GetMethodID(arrayListClass, "add", "(Ljava/lang/Object;)Z");
        if (env->ExceptionCheck()) return;
        const DictionaryHeaderStructurePolicy::AttributeMap *const attributeMap =
                &attributes;
        for (DictionaryHeaderStructurePolicy::AttributeMap::const_iterator it = attributeMap->begin();
                it != attributeMap->end(); ++it) {
            // Output key
            jintArray keyCodePointArray = env->NewIntArray(it->first.size());
            if (env->ExceptionCheck()) return;
            JniDataUtils::outputCodePoints(env, keyCodePointArray, 0 /* start */,
                    it->first.size(), it->first.data(), it->first.size(),
                    false /* needsNullTermination */);
            if (env->ExceptionCheck()) return;
            env->CallBooleanMethod(outAttributeKeys, addMethodId, keyCodePointArray);
            if (env->ExceptionCheck()) return;
            env->DeleteLocalRef(keyCodePointArray);
            // Output value
            jintArray valueCodePointArray = env->NewIntArray(it->second.size());
            if (env->ExceptionCheck()) return;
            JniDataUtils::outputCodePoints(env, valueCodePointArray, 0 /* start */,
                    it->second.size(), it->second.data(), it->second.size(),
                    false /* needsNullTermination */);
            if (env->ExceptionCheck()) return;
            env->CallBooleanMethod(outAttributeValues, addMethodId, valueCodePointArray);
            if (env->ExceptionCheck()) return;
            env->DeleteLocalRef(valueCodePointArray);
        }
        env->DeleteLocalRef(arrayListClass);
        return;
    };
    output();
    env->PopLocalFrame(nullptr);
}

static int latinime_BinaryDictionary_getFormatVersion(JNIEnv *env, jclass clazz, jlong dict) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) return 0;
    const DictionaryHeaderStructurePolicy *const headerPolicy =
            dictionary->getDictionaryStructurePolicy()->getHeaderStructurePolicy();
    return headerPolicy->getFormatVersionNumber();
}

static void latinime_BinaryDictionary_getSuggestions(JNIEnv *env, jclass clazz, jlong dict,
        jlong proximityInfo, jlong dicTraverseSession, jintArray xCoordinatesArray,
        jintArray yCoordinatesArray, jintArray timesArray, jintArray pointerIdsArray,
        jintArray inputCodePointsArray, jint inputSize, jintArray suggestOptions,
        jobjectArray prevWordCodePointArrays, jbooleanArray isBeginningOfSentenceArray,
        jint prevWordCount, jintArray outSuggestionCount, jintArray outCodePointsArray,
        jintArray outScoresArray, jintArray outSpaceIndicesArray, jintArray outTypesArray,
        jintArray outAutoCommitFirstWordConfidenceArray,
        jfloatArray inOutWeightOfLangModelVsSpatialModel) {
    if (env->ExceptionCheck()) return;
    // Count is authoritative; reset it only after establishing a safely writable array.
    if (!hasArrayLength(env, outSuggestionCount, 1)) return;
    JniDataUtils::putIntToArray(env, outSuggestionCount, 0 /* index */, 0);
    if (env->ExceptionCheck()) return;
    if (!hasArrayLength(env, outCodePointsArray, MAX_WORD_LENGTH * MAX_RESULTS)
            || !hasArrayLength(env, outScoresArray, MAX_RESULTS)
            || !hasArrayLength(env, outSpaceIndicesArray, MAX_RESULTS)
            || !hasArrayLength(env, outTypesArray, MAX_RESULTS)
            || !hasArrayLength(env, outAutoCommitFirstWordConfidenceArray, 1)
            || !hasArrayLength(env, inOutWeightOfLangModelVsSpatialModel, 1)
            || inputSize < 0 || inputSize > MAX_SUGGESTION_INPUT_POINTS
            || !hasArrayCapacity(env, xCoordinatesArray, inputSize)
            || !hasArrayCapacity(env, yCoordinatesArray, inputSize)
            || !hasArrayCapacity(env, timesArray, inputSize)
            || !hasArrayCapacity(env, pointerIdsArray, inputSize)
            || !hasArrayLength(env, inputCodePointsArray, MAX_WORD_LENGTH)
            || !hasArrayLength(env, suggestOptions, SUGGESTION_OPTIONS_COUNT)
            || prevWordCount < 0
            || !JniDataUtils::isValidNgramContext(env, prevWordCodePointArrays,
                    isBeginningOfSentenceArray, static_cast<size_t>(prevWordCount))) return;
    if (env->ExceptionCheck()) return;
    int options[SUGGESTION_OPTIONS_COUNT];
    env->GetIntArrayRegion(suggestOptions, 0, SUGGESTION_OPTIONS_COUNT, options);
    if (env->ExceptionCheck()) return;
    SuggestOptions givenSuggestOptions(options, SUGGESTION_OPTIONS_COUNT);
    // ProximityInfoState requires tap inputSize < MAX_WORD_LENGTH. Gesture zero is
    // not prediction: its touch sampler assumes at least one input coordinate.
    if (givenSuggestOptions.isGesture() ? inputSize == 0 : inputSize >= MAX_WORD_LENGTH) return;
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) {
        return;
    }
    ProximityInfo *pInfo = reinterpret_cast<ProximityInfo *>(proximityInfo);
    DicTraverseSession *traverseSession =
            reinterpret_cast<DicTraverseSession *>(dicTraverseSession);
    if (!traverseSession || (!pInfo && (givenSuggestOptions.isGesture() || inputSize > 0))) {
        return;
    }
    // Input values
    std::vector<int> xCoordinates(inputSize);
    std::vector<int> yCoordinates(inputSize);
    std::vector<int> times(inputSize);
    std::vector<int> pointerIds(inputSize);
    int inputCodePoints[MAX_WORD_LENGTH];
    if (inputSize > 0) {
        env->GetIntArrayRegion(xCoordinatesArray, 0, inputSize, xCoordinates.data());
        if (env->ExceptionCheck()) return;
        env->GetIntArrayRegion(yCoordinatesArray, 0, inputSize, yCoordinates.data());
        if (env->ExceptionCheck()) return;
        env->GetIntArrayRegion(timesArray, 0, inputSize, times.data());
        if (env->ExceptionCheck()) return;
        env->GetIntArrayRegion(pointerIdsArray, 0, inputSize, pointerIds.data());
        if (env->ExceptionCheck()) return;
    }
    env->GetIntArrayRegion(inputCodePointsArray, 0, MAX_WORD_LENGTH, inputCodePoints);
    if (env->ExceptionCheck()) return;
    float weightOfLangModelVsSpatialModel;
    env->GetFloatArrayRegion(inOutWeightOfLangModelVsSpatialModel, 0, 1 /* len */,
            &weightOfLangModelVsSpatialModel);
    if (env->ExceptionCheck()) return;
    SuggestionResults suggestionResults(MAX_RESULTS);
    bool validContextCodePoints = true;
    const NgramContext ngramContext = JniDataUtils::constructNgramContext(env,
            prevWordCodePointArrays, isBeginningOfSentenceArray, prevWordCount,
            &validContextCodePoints);
    if (env->ExceptionCheck() || !validContextCodePoints) return;
    if (givenSuggestOptions.isGesture() || inputSize > 0) {
        // TODO: Use SuggestionResults to return suggestions.
        dictionary->getSuggestions(pInfo, traverseSession, xCoordinates.data(), yCoordinates.data(),
                times.data(), pointerIds.data(), inputCodePoints, inputSize, &ngramContext,
                &givenSuggestOptions, weightOfLangModelVsSpatialModel, &suggestionResults);
    } else {
        dictionary->getPredictions(&ngramContext, &suggestionResults);
    }
    if (DEBUG_DICT) {
        suggestionResults.dumpSuggestions();
    }
    suggestionResults.outputSuggestions(env, outSuggestionCount, outCodePointsArray,
            outScoresArray, outSpaceIndicesArray, outTypesArray,
            outAutoCommitFirstWordConfidenceArray, inOutWeightOfLangModelVsSpatialModel);
}

static jint latinime_BinaryDictionary_getProbability(JNIEnv *env, jclass clazz, jlong dict,
        jintArray word) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) return NOT_A_PROBABILITY;
    jsize codePointCount = 0;
    int codePoints[MAX_WORD_LENGTH] = {};
    if (!readWord(env, word, codePoints, &codePointCount)) return NOT_A_PROBABILITY;
    return dictionary->getProbability(CodePointArrayView(codePoints, codePointCount));
}

static jint latinime_BinaryDictionary_getMaxProbabilityOfExactMatches(
        JNIEnv *env, jclass clazz, jlong dict, jintArray word) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) return NOT_A_PROBABILITY;
    jsize codePointCount = 0;
    int codePoints[2 * MAX_WORD_LENGTH] = {};
    if (!readWord(env, word, codePoints, &codePointCount)) return NOT_A_PROBABILITY;
    // Utterleaf: exact queries contain Unicode values, with only a leading internal BoS
    // marker permitted. Decoder padding sentinels have a separate contract.
    for (int i = 0; i < codePointCount; ++i) {
        const int codePoint = codePoints[i];
        if (codePoint < 0 || (codePoint > 0x10FFFF
                && !(i == 0 && codePoint == CODE_POINT_BEGINNING_OF_SENTENCE))) {
            return NOT_A_PROBABILITY;
        }
    }
    return dictionary->getMaxProbabilityOfExactMatches(
            CodePointArrayView(codePoints, codePointCount));
}

static jint latinime_BinaryDictionary_getNgramProbability(JNIEnv *env, jclass clazz,
        jlong dict, jobjectArray prevWordCodePointArrays, jbooleanArray isBeginningOfSentenceArray,
        jintArray word) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary || env->ExceptionCheck()) return NOT_A_PROBABILITY;
    jsize wordLength = 0;
    int wordCodePoints[MAX_WORD_LENGTH] = {};
    if (!readWord(env, word, wordCodePoints, &wordLength)) return NOT_A_PROBABILITY;
    const NgramContext ngramContext = JniDataUtils::constructNgramContext(env,
            prevWordCodePointArrays, isBeginningOfSentenceArray,
            prevWordCodePointArrays ? env->GetArrayLength(prevWordCodePointArrays) : 0);
    if (env->ExceptionCheck()) return NOT_A_PROBABILITY;
    return dictionary->getNgramProbability(&ngramContext,
            CodePointArrayView(wordCodePoints, wordLength));
}

// Method to iterate all words in the dictionary for makedict.
// If token is 0, this method newly starts iterating the dictionary. This method returns 0 when
// the dictionary does not have a next word.
static jint latinime_BinaryDictionary_getNextWord(JNIEnv *env, jclass clazz,
        jlong dict, jint token, jintArray outCodePoints, jbooleanArray outIsBeginningOfSentence) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) return 0;
    const jsize codePointBufSize = env->GetArrayLength(outCodePoints);
    if (codePointBufSize != MAX_WORD_LENGTH) {
        AKLOGE("Invalid outCodePointsLength: %d", codePointBufSize);
        ASSERT(false);
        return 0;
    }
    int wordCodePoints[codePointBufSize];
    int wordCodePointCount = 0;
    const int nextToken = dictionary->getNextWordAndNextToken(token, wordCodePoints,
            &wordCodePointCount);
    JniDataUtils::outputCodePoints(env, outCodePoints, 0 /* start */,
            MAX_WORD_LENGTH /* maxLength */, wordCodePoints, wordCodePointCount,
            false /* needsNullTermination */);
    bool isBeginningOfSentence = false;
    if (wordCodePointCount > 0 && wordCodePoints[0] == CODE_POINT_BEGINNING_OF_SENTENCE) {
        isBeginningOfSentence = true;
    }
    JniDataUtils::putBooleanToArray(env, outIsBeginningOfSentence, 0 /* index */,
            isBeginningOfSentence);
    return nextToken;
}

static void latinime_BinaryDictionary_getWordProperty(JNIEnv *env, jclass clazz,
        jlong dict, jintArray word, jboolean isBeginningOfSentence, jintArray outCodePoints,
        jbooleanArray outFlags, jintArray outProbabilityInfo, jobject outNgramPrevWordsArray,
        jobject outNgramPrevWordIsBeginningOfSentenceArray, jobject outNgramTargets,
        jobject outNgramProbabilityInfo, jobject outShortcutTargets,
        jobject outShortcutProbabilities) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) return;
    // Reject malformed caller-owned outputs before any property data is written.
    if (env->ExceptionCheck() || !hasArrayLength(env, outCodePoints, MAX_WORD_LENGTH)
            || !hasArrayLength(env, outFlags, 5) || !hasArrayLength(env, outProbabilityInfo, 4)) return;
    jclass arrayListClass = env->FindClass("java/util/ArrayList");
    if (env->ExceptionCheck()) return;
    const jobject listOutputs[] = {outNgramPrevWordsArray,
            outNgramPrevWordIsBeginningOfSentenceArray, outNgramTargets,
            outNgramProbabilityInfo, outShortcutTargets, outShortcutProbabilities};
    for (jobject list : listOutputs) {
        if (!list || !env->IsInstanceOf(list, arrayListClass)) {
            env->DeleteLocalRef(arrayListClass);
            return;
        }
    }
    env->DeleteLocalRef(arrayListClass);
    jsize wordLength = 0;
    int wordCodePoints[MAX_WORD_LENGTH] = {};
    if (!readWord(env, word, wordCodePoints, &wordLength, isBeginningOfSentence)) return;
    int codePointCount = wordLength;
    if (isBeginningOfSentence) {
        codePointCount = CharUtils::attachBeginningOfSentenceMarker(
                wordCodePoints, wordLength, MAX_WORD_LENGTH);
        if (codePointCount <= 0) {
            AKLOGE("Cannot attach Beginning-of-Sentence marker.");
            return;
        }
    }
    const WordProperty wordProperty = dictionary->getWordProperty(
            CodePointArrayView(wordCodePoints, codePointCount));
    JniDataUtils::outputWordProperty(env, wordProperty, outCodePoints, outFlags, outProbabilityInfo,
            outNgramPrevWordsArray, outNgramPrevWordIsBeginningOfSentenceArray,
            outNgramTargets, outNgramProbabilityInfo, outShortcutTargets, outShortcutProbabilities);
}

static bool latinime_BinaryDictionary_addUnigramEntry(JNIEnv *env, jclass clazz, jlong dict,
        jintArray word, jint probability, jintArray shortcutTarget, jint shortcutProbability,
        jboolean isBeginningOfSentence, jboolean isNotAWord, jboolean isPossiblyOffensive,
        jint timestamp) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) {
        return false;
    }
    jsize codePointCount = 0;
    int codePoints[MAX_WORD_LENGTH] = {};
    if (!readWord(env, word, codePoints, &codePointCount, isBeginningOfSentence)
            || (isBeginningOfSentence && !canMarkBeginningOfSentence(codePoints, codePointCount))) {
        return false;
    }
    std::vector<UnigramProperty::ShortcutProperty> shortcuts;
    {
        jsize shortcutLength = 0;
        int shortcutCodePoints[MAX_WORD_LENGTH] = {};
        if (shortcutTarget && !readWord(env, shortcutTarget, shortcutCodePoints,
                &shortcutLength, true /* allowEmpty */, false /* allowLeadingBos */)) return false;
        if (shortcutLength > 0) {
            shortcuts.emplace_back(std::vector<int>(shortcutCodePoints,
                    shortcutCodePoints + shortcutLength), shortcutProbability);
        }
    }
    // Use 1 for count to indicate the word has inputted.
    const UnigramProperty unigramProperty(isBeginningOfSentence, isNotAWord,
            isPossiblyOffensive, probability, HistoricalInfo(timestamp, 0 /* level */,
            1 /* count */), std::move(shortcuts));
    return dictionary->addUnigramEntry(CodePointArrayView(codePoints, codePointCount),
            &unigramProperty);
}

static bool latinime_BinaryDictionary_removeUnigramEntry(JNIEnv *env, jclass clazz, jlong dict,
        jintArray word) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) {
        return false;
    }
    jsize codePointCount = 0;
    int codePoints[MAX_WORD_LENGTH] = {};
    if (!readWord(env, word, codePoints, &codePointCount)) return false;
    return dictionary->removeUnigramEntry(CodePointArrayView(codePoints, codePointCount));
}

static bool latinime_BinaryDictionary_addNgramEntry(JNIEnv *env, jclass clazz, jlong dict,
        jobjectArray prevWordCodePointArrays, jbooleanArray isBeginningOfSentenceArray,
        jintArray word, jint probability, jint timestamp) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary || env->ExceptionCheck()) {
        return false;
    }
    const NgramContext ngramContext = JniDataUtils::constructNgramContext(env,
            prevWordCodePointArrays, isBeginningOfSentenceArray,
            prevWordCodePointArrays ? env->GetArrayLength(prevWordCodePointArrays) : 0);
    if (env->ExceptionCheck()) return false;
    jsize wordLength = 0;
    int wordCodePoints[MAX_WORD_LENGTH] = {};
    if (!readWord(env, word, wordCodePoints, &wordLength)) return false;
    // Use 1 for count to indicate the ngram has inputted.
    const NgramProperty ngramProperty(ngramContext,
            CodePointArrayView(wordCodePoints, wordLength).toVector(),
            probability, HistoricalInfo(timestamp, 0 /* level */, 1 /* count */));
    return dictionary->addNgramEntry(&ngramProperty);
}

static bool latinime_BinaryDictionary_removeNgramEntry(JNIEnv *env, jclass clazz, jlong dict,
        jobjectArray prevWordCodePointArrays, jbooleanArray isBeginningOfSentenceArray,
        jintArray word) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary || env->ExceptionCheck()) {
        return false;
    }
    const NgramContext ngramContext = JniDataUtils::constructNgramContext(env,
            prevWordCodePointArrays, isBeginningOfSentenceArray,
            prevWordCodePointArrays ? env->GetArrayLength(prevWordCodePointArrays) : 0);
    if (env->ExceptionCheck()) return false;
    jsize codePointCount = 0;
    int wordCodePoints[MAX_WORD_LENGTH] = {};
    if (!readWord(env, word, wordCodePoints, &codePointCount)) return false;
    return dictionary->removeNgramEntry(&ngramContext,
            CodePointArrayView(wordCodePoints, codePointCount));
}

static bool latinime_BinaryDictionary_updateEntriesForWordWithNgramContext(JNIEnv *env,
        jclass clazz, jlong dict, jobjectArray prevWordCodePointArrays,
        jbooleanArray isBeginningOfSentenceArray, jintArray word, jboolean isValidWord, jint count,
        jint timestamp) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary || env->ExceptionCheck()) {
        return false;
    }
    const NgramContext ngramContext = JniDataUtils::constructNgramContext(env,
            prevWordCodePointArrays, isBeginningOfSentenceArray,
            prevWordCodePointArrays ? env->GetArrayLength(prevWordCodePointArrays) : 0);
    if (env->ExceptionCheck()) return false;
    jsize codePointCount = 0;
    int wordCodePoints[MAX_WORD_LENGTH] = {};
    if (!readWord(env, word, wordCodePoints, &codePointCount)) return false;
    const HistoricalInfo historicalInfo(timestamp, 0 /* level */, count);
    return dictionary->updateEntriesForWordWithNgramContext(&ngramContext,
            CodePointArrayView(wordCodePoints, codePointCount), isValidWord == JNI_TRUE,
            historicalInfo);
}

// Returns how many input events are processed.
static int latinime_BinaryDictionary_updateEntriesForInputEvents(JNIEnv *env, jclass clazz,
        jlong dict, jobjectArray inputEvents, jint startIndex) {
    // Utterleaf: keep the legacy JNI signature, but never read event data or mutate dictionaries.
    // The inherited carrier no longer contains mIsValid; do not invent learning semantics.
    if (env->ExceptionCheck()) return 0;
    jclass unsupported = env->FindClass("java/lang/UnsupportedOperationException");
    if (env->ExceptionCheck()) return 0;
    env->ThrowNew(unsupported, "Legacy bulk personalization is unavailable");
    env->DeleteLocalRef(unsupported);
    return 0;
}

static jstring latinime_BinaryDictionary_getProperty(JNIEnv *env, jclass clazz, jlong dict,
        jstring query) {
    if (env->ExceptionCheck()) return nullptr;
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary || !query) {
        return env->NewStringUTF("");
    }
    // Utterleaf: only the existing stats commands are supported, without unbounded UTF/VLAs.
    static const char *const queries[] = {
        "UNIGRAM_COUNT", "BIGRAM_COUNT", "MAX_UNIGRAM_COUNT", "MAX_BIGRAM_COUNT"
    };
    static const int QUERY_CAPACITY = sizeof("MAX_UNIGRAM_COUNT");
    const jsize length = env->GetStringLength(query);
    if (env->ExceptionCheck()) return nullptr;
    if (length <= 0 || length >= QUERY_CAPACITY) return env->NewStringUTF("");
    jchar units[QUERY_CAPACITY] = {};
    char queryChars[QUERY_CAPACITY] = {};
    env->GetStringRegion(query, 0, length, units);
    if (env->ExceptionCheck()) return nullptr;
    for (int i = 0; i < length; ++i) {
        if (units[i] == 0 || units[i] > 0x7F) return env->NewStringUTF("");
        queryChars[i] = static_cast<char>(units[i]);
    }
    bool supported = false;
    for (const char *candidate : queries) {
        if (strcmp(queryChars, candidate) == 0) supported = true;
    }
    if (!supported) return env->NewStringUTF("");
    static const int GET_PROPERTY_RESULT_LENGTH = 100;
    char resultChars[GET_PROPERTY_RESULT_LENGTH] = {};
    dictionary->getProperty(queryChars, length, resultChars, GET_PROPERTY_RESULT_LENGTH);
    resultChars[GET_PROPERTY_RESULT_LENGTH - 1] = '\0';
    if (env->ExceptionCheck()) return nullptr;
    return env->NewStringUTF(resultChars);
}

static bool latinime_BinaryDictionary_isCorruptedNative(JNIEnv *env, jclass clazz, jlong dict) {
    Dictionary *dictionary = reinterpret_cast<Dictionary *>(dict);
    if (!dictionary) {
        return false;
    }
    return !dictionary->isStorageAvailable()
            || dictionary->getDictionaryStructurePolicy()->isCorrupted();
}

static void latinime_BinaryDictionary_markStorageUnavailableNative(JNIEnv *, jclass, jlong dict) {
    Dictionary *dictionary = reinterpret_cast<Dictionary *>(dict);
    if (dictionary) dictionary->markStorageUnavailable();
}

static bool latinime_BinaryDictionary_isStorageAvailableNative(JNIEnv *, jclass, jlong dict) {
    return getAvailableDictionary(dict) != nullptr;
}

static DictionaryStructureWithBufferPolicy::StructurePolicyPtr runGCAndGetNewStructurePolicy(
        DictionaryStructureWithBufferPolicy::StructurePolicyPtr structurePolicy,
        const char *const dictFilePath) {
    if (!structurePolicy->flushWithGC(dictFilePath)) return nullptr;
    // Release the old owner, including mappings, before opening the freshly written candidate.
    structurePolicy.reset();
    return DictionaryStructureWithBufferPolicyFactory::newPolicyForExistingDictFile(
            dictFilePath, 0 /* offset */, 0 /* size */, true /* isUpdatable */);
}

static bool latinime_BinaryDictionary_migrateNative(JNIEnv *env, jclass clazz, jlong dict,
        jstring dictFilePath, jlong newFormatVersion) {
    Dictionary *dictionary = getAvailableDictionary(dict);
    if (!dictionary) {
        return false;
    }
    std::vector<char> pathStorage;
    if (!JniDataUtils::readFilePath(env, dictFilePath, &pathStorage)) return false;
    const char *const dictFilePathChars = pathStorage.data();
    std::shared_ptr<StorageGeneration> candidateGeneration;
    StorageTransaction candidateTransaction(dictFilePathChars, &candidateGeneration);
    if (!candidateTransaction.admitted()) return false;


    const DictionaryHeaderStructurePolicy *const headerPolicy =
            dictionary->getDictionaryStructurePolicy()->getHeaderStructurePolicy();
    DictionaryStructureWithBufferPolicy::StructurePolicyPtr dictionaryStructureWithBufferPolicy =
            DictionaryStructureWithBufferPolicyFactory::newPolicyForOnMemoryDict(
                    newFormatVersion, *headerPolicy->getLocale(), headerPolicy->getAttributeMap());
    if (!dictionaryStructureWithBufferPolicy) {
        LogUtils::logToJava(env, "Cannot migrate header.");
        return false;
    }

    int wordCodePoints[MAX_WORD_LENGTH] = {};
    int wordCodePointCount = 0;
    int token = 0;
    // Add unigrams.
    do {
        token = dictionary->getNextWordAndNextToken(token, wordCodePoints, &wordCodePointCount);
        // An empty dictionary returns token zero and zero code points without writing the buffer.
        if (wordCodePointCount == 0) continue;
        if (wordCodePointCount < 0 || wordCodePointCount > MAX_WORD_LENGTH) return false;
        const WordProperty wordProperty = dictionary->getWordProperty(
                CodePointArrayView(wordCodePoints, wordCodePointCount));
        if (wordCodePoints[0] == CODE_POINT_BEGINNING_OF_SENTENCE) {
            // Skip beginning-of-sentence unigram.
            continue;
        }
        if (dictionaryStructureWithBufferPolicy->needsToRunGC(true /* mindsBlockByGC */)) {
            dictionaryStructureWithBufferPolicy = runGCAndGetNewStructurePolicy(
                    std::move(dictionaryStructureWithBufferPolicy), dictFilePathChars);
            if (!dictionaryStructureWithBufferPolicy) {
                LogUtils::logToJava(env, "Cannot open dict after GC.");
                return false;
            }
        }
        if (!dictionaryStructureWithBufferPolicy->addUnigramEntry(
                CodePointArrayView(wordCodePoints, wordCodePointCount),
                &wordProperty.getUnigramProperty())) {
            LogUtils::logToJava(env, "Cannot add unigram to the new dict.");
            return false;
        }
    } while (token != 0);

    // Add ngrams.
    do {
        token = dictionary->getNextWordAndNextToken(token, wordCodePoints, &wordCodePointCount);
        // An empty dictionary returns token zero and zero code points without writing the buffer.
        if (wordCodePointCount == 0) continue;
        if (wordCodePointCount < 0 || wordCodePointCount > MAX_WORD_LENGTH) return false;
        const WordProperty wordProperty = dictionary->getWordProperty(
                CodePointArrayView(wordCodePoints, wordCodePointCount));
        if (dictionaryStructureWithBufferPolicy->needsToRunGC(true /* mindsBlockByGC */)) {
            dictionaryStructureWithBufferPolicy = runGCAndGetNewStructurePolicy(
                    std::move(dictionaryStructureWithBufferPolicy), dictFilePathChars);
            if (!dictionaryStructureWithBufferPolicy) {
                LogUtils::logToJava(env, "Cannot open dict after GC.");
                return false;
            }
        }
        for (const NgramProperty &ngramProperty : wordProperty.getNgramProperties()) {
            if (!dictionaryStructureWithBufferPolicy->addNgramEntry(&ngramProperty)) {
                LogUtils::logToJava(env, "Cannot add ngram to the new dict.");
                return false;
            }
        }
    } while (token != 0);
    // Save to File.
    // A failed candidate write must never be reported as a successful migration.
    return dictionaryStructureWithBufferPolicy->flushWithGC(dictFilePathChars);
}

static const JNINativeMethod sMethods[] = {
    {
        const_cast<char *>("isStorageAvailableNative"),
        const_cast<char *>("(J)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_isStorageAvailableNative)
    },
    {
        const_cast<char *>("markStorageUnavailableNative"),
        const_cast<char *>("(J)V"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_markStorageUnavailableNative)
    },
    {
        const_cast<char *>("openNative"),
        const_cast<char *>("(Ljava/lang/String;JJZ)J"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_open)
    },
    {
        const_cast<char *>("createOnMemoryNative"),
        const_cast<char *>("(JLjava/lang/String;[Ljava/lang/String;[Ljava/lang/String;)J"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_createOnMemory)
    },
    {
        const_cast<char *>("closeNative"),
        const_cast<char *>("(J)V"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_close)
    },
    {
        const_cast<char *>("getFormatVersionNative"),
        const_cast<char *>("(J)I"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_getFormatVersion)
    },
    {
        const_cast<char *>("getHeaderInfoNative"),
        const_cast<char *>("(J[I[ILjava/util/ArrayList;Ljava/util/ArrayList;)V"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_getHeaderInfo)
    },
    {
        const_cast<char *>("flushNative"),
        const_cast<char *>("(JLjava/lang/String;)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_flush)
    },
    {
        const_cast<char *>("needsToRunGCNative"),
        const_cast<char *>("(JZ)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_needsToRunGC)
    },
    {
        const_cast<char *>("flushWithGCNative"),
        const_cast<char *>("(JLjava/lang/String;)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_flushWithGC)
    },
    {
        const_cast<char *>("getSuggestionsNative"),
        const_cast<char *>("(JJJ[I[I[I[I[II[I[[I[ZI[I[I[I[I[I[I[F)V"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_getSuggestions)
    },
    {
        const_cast<char *>("getProbabilityNative"),
        const_cast<char *>("(J[I)I"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_getProbability)
    },
    {
        const_cast<char *>("getMaxProbabilityOfExactMatchesNative"),
        const_cast<char *>("(J[I)I"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_getMaxProbabilityOfExactMatches)
    },
    {
        const_cast<char *>("getNgramProbabilityNative"),
        const_cast<char *>("(J[[I[Z[I)I"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_getNgramProbability)
    },
    {
        const_cast<char *>("getWordPropertyNative"),
        const_cast<char *>("(J[IZ[I[Z[ILjava/util/ArrayList;Ljava/util/ArrayList;"
                "Ljava/util/ArrayList;Ljava/util/ArrayList;Ljava/util/ArrayList;"
                "Ljava/util/ArrayList;)V"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_getWordProperty)
    },
    {
        const_cast<char *>("getNextWordNative"),
        const_cast<char *>("(JI[I[Z)I"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_getNextWord)
    },
    {
        const_cast<char *>("addUnigramEntryNative"),
        const_cast<char *>("(J[II[IIZZZI)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_addUnigramEntry)
    },
    {
        const_cast<char *>("removeUnigramEntryNative"),
        const_cast<char *>("(J[I)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_removeUnigramEntry)
    },
    {
        const_cast<char *>("addNgramEntryNative"),
        const_cast<char *>("(J[[I[Z[III)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_addNgramEntry)
    },
    {
        const_cast<char *>("removeNgramEntryNative"),
        const_cast<char *>("(J[[I[Z[I)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_removeNgramEntry)
    },
    {
        const_cast<char *>("updateEntriesForWordWithNgramContextNative"),
        const_cast<char *>("(J[[I[Z[IZII)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_updateEntriesForWordWithNgramContext)
    },
    {
        const_cast<char *>("updateEntriesForInputEventsNative"),
        const_cast<char *>(
                "(J[Lcom/android/inputmethod/latin/utils/WordInputEventForPersonalization;I)I"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_updateEntriesForInputEvents)
    },
    {
        const_cast<char *>("getPropertyNative"),
        const_cast<char *>("(JLjava/lang/String;)Ljava/lang/String;"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_getProperty)
    },
    {
        const_cast<char *>("isCorruptedNative"),
        const_cast<char *>("(J)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_isCorruptedNative)
    },
    {
        const_cast<char *>("migrateNative"),
        const_cast<char *>("(JLjava/lang/String;J)Z"),
        reinterpret_cast<void *>(latinime_BinaryDictionary_migrateNative)
    }
};

int register_BinaryDictionary(JNIEnv *env) {
    const char *const kClassPathName = "com/android/inputmethod/latin/BinaryDictionary";
    return registerNativeMethods(env, kClassPathName, sMethods, NELEMS(sMethods));
}
} // namespace latinime
