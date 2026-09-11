/*
 * Copyright (C) 2013 The Android Open Source Project
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

// Utterleaf modification: bounded work and linear-memory edit-distance computation.
#ifndef LATINIME_EDIT_DISTANCE_H
#define LATINIME_EDIT_DISTANCE_H

#include <algorithm>
#include <memory>
#include <new>

#include "defines.h"
#include "suggest/policyimpl/utils/edit_distance_policy.h"

namespace latinime {

class EditDistance {
 public:
    // Utterleaf resource policy: reject, never truncate, unsupported work.
    static constexpr int MAX_INPUT_CODE_POINTS = 4096;
    static constexpr int MAX_WORK_CELLS = 1048576;
    static bool supportsLengths(const int beforeLength, const int afterLength) {
        return beforeLength >= 0 && afterLength >= 0
                && beforeLength <= MAX_INPUT_CODE_POINTS && afterLength <= MAX_INPUT_CODE_POINTS
                && (beforeLength + 1) <= MAX_WORK_CELLS / (afterLength + 1);
    }

    // -1 means unavailable. Three rows preserve the original adjacent-transposition policy
    // without a caller-sized stack allocation or a quadratic memory allocation.
    AK_FORCE_INLINE static float getEditDistance(const EditDistancePolicy *const policy) {
        const int beforeLength = policy->getString0Length();
        const int afterLength = policy->getString1Length();
        if (!supportsLengths(beforeLength, afterLength)) return -1.0f;
        const int width = afterLength + 1;
        std::unique_ptr<float[]> storage(new (std::nothrow) float[3 * width]);
        if (!storage) return -1.0f;
        float *previousPrevious = storage.get();
        float *previous = previousPrevious + width;
        float *current = previous + width;
        for (int j = 0; j <= afterLength; ++j) {
            previous[j] = j * policy->getDeletionCost(-1, j - 1);
        }
        for (int i = 0; i < beforeLength; ++i) {
            current[0] = (i + 1) * policy->getInsertionCost(i, -1);
            for (int j = 0; j < afterLength; ++j) {
                current[j + 1] = std::min(previous[j + 1] + policy->getInsertionCost(i, j),
                        std::min(current[j] + policy->getDeletionCost(i, j),
                                previous[j] + policy->getSubstitutionCost(i, j)));
                if (i > 0 && j > 0 && policy->allowTransposition(i, j)) {
                    current[j + 1] = std::min(current[j + 1], previousPrevious[j - 1]
                            + policy->getTranspositionCost(i, j));
                }
            }
            std::swap(previousPrevious, previous);
            std::swap(previous, current);
        }
        return previous[afterLength];
    }

    AK_FORCE_INLINE static void dumpEditDistance10ForDebug(const float *const editDistanceTable,
            const int editDistanceTableWidth, const int outputLength) {
        if (DEBUG_DICT) {
            AKLOGI("EditDistanceTable");
            for (int i = 0; i <= 10; ++i) {
                float c[11];
                for (int j = 0; j <= 10; ++j) {
                    if (j < editDistanceTableWidth + 1 && i < outputLength + 1) {
                        c[j] = (editDistanceTable + i * (editDistanceTableWidth + 1))[j];
                    } else {
                        c[j] = -1.0f;
                    }
                }
                AKLOGI("[ %f, %f, %f, %f, %f, %f, %f, %f, %f, %f, %f ]",
                        c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[9], c[10]);
                (void)c; // To suppress compiler warning
            }
        }
    }

 private:
    DISALLOW_IMPLICIT_CONSTRUCTORS(EditDistance);
};
} // namespace latinime

#endif  // LATINIME_EDIT_DISTANCE_H
