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

@RunWith(AndroidJUnit4::class)
class NativeExactCodepointTest {
    @Test fun malformedExactCodepointsRejectAndLegitimateWordsAndBosRemainReadable() {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-exact-codepoints-${UUID.randomUUID()}")
        check(directory.mkdir())
        val dictionary = BinaryDictionary(File(directory, "fixture.dict").absolutePath, false,
            Locale.ENGLISH, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en", "version" to "1"))
        try {
            for (word in listOf("café", "a\uD83D\uDE42b")) {
                assertTrue(dictionary.addUnigramEntry(word, 190, false, false, false, 0))
                assertEquals(190, dictionary.getMaxFrequencyOfExactMatches(word))
            }
            assertEquals(190, dictionary.getMaxFrequencyOfExactMatches("CAFE"))
            assertTrue(dictionary.runWithNativeOperationForTesting {
                val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                    .apply { isAccessible = true }.getLong(dictionary)
                fun native(name: String, vararg arguments: Any?): Any? = BinaryDictionary::class.java
                    .declaredMethods.single { it.name == name }.apply { isAccessible = true }
                    .invoke(null, *arguments)
                for (invalid in listOf(intArrayOf(-1), intArrayOf(Int.MIN_VALUE),
                    intArrayOf(Int.MAX_VALUE), intArrayOf(0x110001), intArrayOf(97, 0x110000),
                    intArrayOf(0x110000, -1), intArrayOf(0x110000, 0x110000))) {
                    assertEquals(Dictionary.NOT_A_PROBABILITY,
                        native("getMaxProbabilityOfExactMatchesNative", handle, invalid))
                }
                // BoS is an internal leading marker, not a negative decoder-padding sentinel.
                val marked = intArrayOf(0x110000, 'x'.code)
                assertEquals(true, native("addUnigramEntryNative", handle, marked,
                    180, null, 0, true, false, false, 0))
                assertEquals(180, native("getProbabilityNative", handle, marked))
                assertEquals(180, native("getMaxProbabilityOfExactMatchesNative", handle, marked))
            })
            assertEquals(190, dictionary.getFrequency("café"))
        } finally { dictionary.close(); check(directory.deleteRecursively()) }
    }
}
