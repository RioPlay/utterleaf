package org.utterleaf.keyboard

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.BinaryDictionary
import com.android.inputmethod.latin.Dictionary
import com.android.inputmethod.latin.makedict.FormatSpec
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.Locale
import java.util.UUID

/** Synthetic native word boundaries, separate from the shorter tapping decoder limit. */
@RunWith(AndroidJUnit4::class)
class NativeWordBoundsTest {
    private fun fixture(test: (BinaryDictionary, Long) -> Unit) {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-word-bounds-${UUID.randomUUID()}")
        check(directory.mkdir())
        val dictionary = BinaryDictionary(File(directory, "fixture.dict").absolutePath, false,
            Locale.GERMAN, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "de", "version" to "1",
                "REQUIRES_GERMAN_UMLAUT_PROCESSING" to "1"))
        try {
            assertTrue(dictionary.runWithNativeOperationForTesting {
                val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                    .apply { isAccessible = true }.getLong(dictionary)
                assertNotEquals(0L, handle)
                test(dictionary, handle)
            })
        } finally { dictionary.close(); check(directory.deleteRecursively()) }
    }

    private fun native(name: String, vararg args: Any?): Any? = BinaryDictionary::class.java.declaredMethods
        .single { it.name == name }.apply { isAccessible = true }.invoke(null, *args)

    private fun add(handle: Long, word: IntArray?, beginning: Boolean = false, shortcut: IntArray? = null) =
        native("addUnigramEntryNative", handle, word, 180, shortcut, 0, beginning, false, false, 0)

    @Test fun maximumStoredWordsPreserveCodepointsAndDigraphExpansion() = fixture { dictionary, _ ->
        for (word in listOf("a".repeat(48), "\uD83D\uDE42".repeat(48))) {
            assertEquals(48, word.codePointCount(0, word.length))
            assertTrue(dictionary.addUnigramEntry(word, 200, false, false, false, 0))
            assertEquals(200, dictionary.getFrequency(word))
            assertTrue(dictionary.removeUnigramEntry(word))
            assertEquals(Dictionary.NOT_A_PROBABILITY, dictionary.getFrequency(word))
        }
        // A stored umlaut expands to two query codepoints: legitimate queries exceed 48.
        for (length in listOf(25, 46)) {
            val word = "ö".repeat(length)
            assertTrue(dictionary.addUnigramEntry(word, 190, false, false, false, 0))
            assertEquals("Normalized query with ${length * 2} codepoints", 190,
                dictionary.getMaxFrequencyOfExactMatches("oe".repeat(length)))
        }
        // Storage supports 48 codepoints. The JNI source permits 96 normalized codepoints;
        // the unavailable result below cannot independently prove admission. The
        // upstream exact-match walker separately stops expanding after stored depth 46
        // (DicNodeUtils uses MAX_WORD_LENGTH - 3); do not claim broader search quality.
        val maximumStoredUmlauts = "ö".repeat(48)
        assertTrue(dictionary.addUnigramEntry(maximumStoredUmlauts, 190, false, false, false, 0))
        assertEquals(190, dictionary.getFrequency(maximumStoredUmlauts))
        assertEquals(Dictionary.NOT_A_PROBABILITY,
            dictionary.getMaxFrequencyOfExactMatches("oe".repeat(48)))
        assertEquals(Dictionary.NOT_A_PROBABILITY, dictionary.getMaxFrequencyOfExactMatches("a".repeat(97)))
    }

    @Test fun malformedWordBuffersRejectQueriesAndMutationsWithoutExceptions() = fixture { _, handle ->
        val context = arrayOf(intArrayOf('p'.code))
        val flags = booleanArrayOf(false)
        for (word in listOf(null, IntArray(0), IntArray(49), IntArray(65_536))) {
            assertEquals(Dictionary.NOT_A_PROBABILITY, native("getProbabilityNative", handle, word))
            assertEquals(Dictionary.NOT_A_PROBABILITY, native("getNgramProbabilityNative", handle, context, flags, word))
            assertEquals(false, add(handle, word))
            assertEquals(false, native("removeUnigramEntryNative", handle, word))
            assertEquals(false, native("addNgramEntryNative", handle, context, flags, word, 180, 0))
            assertEquals(false, native("removeNgramEntryNative", handle, context, flags, word))
            assertEquals(false, native("updateEntriesForWordWithNgramContextNative", handle, context, flags, word, true, 1, 0))
        }
        for (word in listOf(null, IntArray(0), IntArray(97), IntArray(65_536))) {
            assertEquals(Dictionary.NOT_A_PROBABILITY, native("getMaxProbabilityOfExactMatchesNative", handle, word))
        }
        assertEquals(Dictionary.NOT_A_PROBABILITY, native("getNgramProbabilityNative", 0L, context, flags, intArrayOf(97)))
        val target = "shortcutcanary".map { it.code }.toIntArray()
        assertEquals(false, add(handle, target, shortcut = IntArray(49)))
        assertEquals(Dictionary.NOT_A_PROBABILITY, native("getProbabilityNative", handle, target))
        assertEquals(true, add(handle, target, shortcut = IntArray(0)))
        assertEquals(180, native("getProbabilityNative", handle, target))
    }

    private fun property(handle: Long, word: IntArray?, beginning: Boolean): Array<Any> {
        val outputs: Array<Any> = arrayOf(IntArray(48) { 73 }, BooleanArray(5), IntArray(4) { 73 },
            ArrayList<Array<IntArray>>(), ArrayList<BooleanArray>(), ArrayList<IntArray>(),
            ArrayList<IntArray>(), ArrayList<IntArray>(), ArrayList<Int>())
        native("getWordPropertyNative", handle, word, beginning, *outputs)
        return outputs
    }

    @Test fun beginningOfSentenceCapacityAndMalformedPropertyInputAreHandled() = fixture { dictionary, handle ->
        assertTrue(dictionary.addUnigramEntry("", 170, true, false, false, 0))
        val beginning = checkNotNull(dictionary.getWordProperty("", true))
        assertTrue(beginning.mIsBeginningOfSentence)
        assertEquals(170, beginning.mProbabilityInfo.mProbability)
        val marked = IntArray(48) { 'a'.code }.apply { this[0] = 0x110000 } // Native BoS marker.
        assertEquals(true, add(handle, marked, beginning = true))
        assertEquals(180, (property(handle, marked, true)[2] as IntArray)[0])
        assertEquals(false, add(handle, IntArray(48) { 'b'.code }, beginning = true))
        for ((word, beginning) in listOf(null to false, IntArray(0) to false,
            IntArray(49) to false, IntArray(48) { 'b'.code } to true)) {
            val output = property(handle, word, beginning)
            assertArrayEquals(IntArray(48) { 73 }, output[0] as IntArray)
            assertArrayEquals(IntArray(4) { 73 }, output[2] as IntArray)
            assertTrue((output[3] as ArrayList<*>).isEmpty())
        }
    }
}
