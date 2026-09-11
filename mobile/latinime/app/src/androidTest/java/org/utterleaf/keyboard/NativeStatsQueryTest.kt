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
class NativeStatsQueryTest {
    @Test fun exactStatsCommandsAndMalformedQueriesPreserveSyntheticEntries() {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-stats-${UUID.randomUUID()}")
        check(directory.mkdir())
        val dictionary = BinaryDictionary(File(directory, "fixture.dict").absolutePath, false,
            Locale.ENGLISH, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en", "version" to "1"))
        try {
            assertTrue(dictionary.addUnigramEntry("syntheticcanary", 190, false, false, false, 0))
            assertTrue(dictionary.runWithNativeOperationForTesting {
                val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                    .apply { isAccessible = true }.getLong(dictionary)
                val method = BinaryDictionary::class.java.getDeclaredMethod("getPropertyNative",
                    Long::class.javaPrimitiveType, String::class.java).apply { isAccessible = true }
                fun query(value: String?) = method.invoke(null, handle, value) as String
                assertEquals("1", query("UNIGRAM_COUNT"))
                assertEquals("0", query("BIGRAM_COUNT"))
                assertTrue(query("MAX_UNIGRAM_COUNT").toInt() > 0)
                assertTrue(query("MAX_BIGRAM_COUNT").toInt() > 0)
                for (value in listOf(null, "", "UNIGRAM", "unigram_count", "UNIGRAM_COUNTx",
                    "UNIGRAM_COUNT\u0000", "\uD800", "\uD83D\uDE42", "a".repeat(100_000))) {
                    assertEquals("", query(value))
                }
            })
            assertEquals(190, dictionary.getFrequency("syntheticcanary"))
        } finally { dictionary.close(); check(directory.deleteRecursively()) }
    }
}
