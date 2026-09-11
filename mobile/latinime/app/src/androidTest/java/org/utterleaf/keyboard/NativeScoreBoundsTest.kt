package org.utterleaf.keyboard

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.android.inputmethod.latin.utils.BinaryDictionaryUtils
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.random.Random

/** Independent full-matrix reference for the bounded native three-row score calculation. */
@RunWith(AndroidJUnit4::class)
class NativeScoreBoundsTest {
    private fun score(before: IntArray?, after: IntArray?, value: Int = 1_000_000): Float =
        BinaryDictionaryUtils::class.java.getDeclaredMethod("calcNormalizedScoreNative",
            IntArray::class.java, IntArray::class.java, Int::class.javaPrimitiveType)
            .apply { isAccessible = true }.invoke(null, before, after, value) as Float

    // Only the explicitly selected oracle alphabet needs base-case folding.
    private fun base(value: Int) = when (value) {
        in 65..90 -> value + 32
        0xE9, 0xC9 -> 'e'.code
        else -> value
    }
    private fun reference(before: IntArray, after: IntArray, value: Int): Float {
        if (before.isEmpty() || after.isEmpty() || value <= 0 || after.all { it == 32 }) return 0f
        val matrix = Array(before.size + 1) { IntArray(after.size + 1) }
        for (i in matrix.indices) matrix[i][0] = i
        for (j in matrix[0].indices) matrix[0][j] = j
        for (i in before.indices) for (j in after.indices) {
            val substitution = if (base(before[i]) == base(after[j])) 0 else 1
            var distance = minOf(matrix[i][j + 1] + 1, matrix[i + 1][j] + 1,
                matrix[i][j] + substitution)
            if (i > 0 && j > 0 && base(before[i]) == base(after[j - 1]) &&
                base(after[j]) == base(before[i - 1])) {
                distance = minOf(distance, matrix[i - 1][j - 1] + substitution)
            }
            matrix[i + 1][j + 1] = distance
        }
        val distance = matrix.last().last()
        return if (distance >= after.size) 0f else
            (value / 1_000_000f) * (1f - distance.toFloat() / after.size)
    }

    @Test fun scoreMatchesOriginalMatrixForUnicodeAndEditOperations() {
        val alphabet = intArrayOf(0, 32, 97, 98, 99, 65, 0xE9, 0xC9, 0xD800, 0x1F642, 0x10FFFF)
        val random = Random(391)
        val cases = mutableListOf(
            intArrayOf(97, 98) to intArrayOf(98, 97),
            intArrayOf(0, 0xD800, 0x1F642) to intArrayOf(0, 0xD800, 0x1F642),
            intArrayOf(0xE9, 65) to intArrayOf(101, 97))
        repeat(150) {
            cases += IntArray(random.nextInt(0, 10)) { alphabet.random(random) } to
                IntArray(random.nextInt(0, 10)) { alphabet.random(random) }
        }
        for ((before, after) in cases) {
            assertEquals(reference(before, after, 1_000_000), score(before, after), 0.000001f)
        }
        for (word in listOf("a\u0000b", "a\uD800b", "a\uD83D\uDE42b")) {
            assertEquals(1f, BinaryDictionaryUtils.calcNormalizedScore(word, word, 1_000_000), 0f)
        }
    }

    @Test fun unsupportedWorkAndMalformedCodepointsAreUnavailableWithoutTruncation() {
        for (invalid in listOf(null, intArrayOf(-1), intArrayOf(Int.MIN_VALUE),
            intArrayOf(0x110000), IntArray(4097) { 97 })) {
            assertEquals(0f, score(invalid, intArrayOf(97)), 0f)
            assertEquals(0f, score(intArrayOf(97), invalid), 0f)
        }
        assertEquals(1f, score(IntArray(1023) { 97 }, IntArray(1023) { 97 }), 0f)
        assertEquals(0f, score(IntArray(1024) { 97 }, IntArray(1024) { 97 }), 0f)
        assertEquals(1f / 4096, score(intArrayOf(97), IntArray(4096) { 97 }), 0f)
        val supplementary = "\uD83D\uDE42".repeat(1023)
        assertEquals(1f, BinaryDictionaryUtils.calcNormalizedScore(supplementary, supplementary, 1_000_000), 0f)
        assertEquals(1f / 4096, BinaryDictionaryUtils.calcNormalizedScore(
            "\uD83D\uDE42", "\uD83D\uDE42".repeat(4096), 1_000_000), 0f)
        assertEquals(0f, BinaryDictionaryUtils.calcNormalizedScore("a".repeat(100_000), "a", 1_000_000), 0f)
        assertEquals(0f, score(intArrayOf(97), intArrayOf(97), -1), 0f)
        assertEquals(0f, score(intArrayOf(), intArrayOf(97)), 0f)
        assertEquals(0f, score(intArrayOf(32), intArrayOf(32)), 0f)
    }
}
