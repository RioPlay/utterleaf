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
import android.util.SparseArray
import com.android.inputmethod.latin.NgramContext
import com.android.inputmethod.latin.common.ComposedData
import com.android.inputmethod.latin.common.InputPointers
import com.android.inputmethod.latin.settings.SettingsValuesForSuggestion
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/** Generated test words only; no imported third-party dictionary or user vocabulary. */
@RunWith(AndroidJUnit4::class)
class NativeDictionaryTest {
    private fun fixture(test: (File) -> Unit) {
        val cache = InstrumentationRegistry.getInstrumentation().targetContext.cacheDir
        val directory = File(cache, "synthetic-dictionary-${UUID.randomUUID()}")
        check(directory.mkdir())
        try { test(directory) } finally { check(directory.deleteRecursively()) }
    }

    @Test fun nativeDictionaryPersistsExplicitSyntheticEntries() = fixture { directory ->
        val file = File(directory, "fixture.dict")
        val dictionary = BinaryDictionary(file.absolutePath, false, Locale.US, Dictionary.TYPE_MAIN,
            FormatSpec.VERSION4.toLong(), mapOf("dictionary" to "synthetic-test", "locale" to "en_US", "version" to "1"))
        try {
            assertTrue(dictionary.isValidDictionary)
            assertTrue(dictionary.addUnigramEntry("utterleafqa", 200, false, false, false, 0))
            assertEquals(200, dictionary.getFrequency("utterleafqa"))
            assertTrue(dictionary.flush())
            assertTrue("Internal reopen closed the public lifetime gate", dictionary.isValidDictionary)
            assertEquals(200, dictionary.getFrequency("utterleafqa"))
        } finally { dictionary.close() }
        val reopened = BinaryDictionary(file.absolutePath, 0, file.length(), false, Locale.US, Dictionary.TYPE_MAIN, true)
        try {
            assertTrue(reopened.isValidDictionary)
            assertEquals(200, reopened.getFrequency("utterleafqa"))
            assertFalse(reopened.isValidWord("notinthefixture"))
        } finally { reopened.close() }
    }

    @Test fun emptyAndInvalidHeadersAreRejectedByNativeLoader() = fixture { directory ->
        for (length in listOf(0, 1, 4, 16, 64)) {
            val file = File(directory, "invalid-$length.dict")
            file.writeBytes(ByteArray(length))
            val dictionary = BinaryDictionary(file.absolutePath, 0, file.length(), false,
                Locale.US, Dictionary.TYPE_MAIN, false)
            try {
                assertFalse("Accepted invalid header of length $length", dictionary.isValidDictionary)
                assertFalse(dictionary.isValidNgram(NgramContext.EMPTY_PREV_WORDS_INFO, "synthetic"))
                assertEquals(Dictionary.NOT_A_PROBABILITY,
                    dictionary.getNgramProbability(NgramContext.EMPTY_PREV_WORDS_INFO, "synthetic"))
            }
            finally { dictionary.close() }
        }
    }

    @Test fun closeDuringAdmittedDecodeKeepsNativeMemoryUntilReturn() = fixture { directory ->
        val dictionary = BinaryDictionary(File(directory, "lease.dict").absolutePath, false,
            Locale.US, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en_US", "version" to "1"))
        assertTrue(dictionary.addUnigramEntry("utterleafqa", 200, false, false, false, 0))
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val completed = CountDownLatch(1)
        val failure = AtomicReference<Throwable>()
        val pointer = BinaryDictionary::class.java.getDeclaredField("mNativeDict").apply { isAccessible = true }
        val sessions = BinaryDictionary::class.java.getDeclaredField("mDicTraverseSessions").apply { isAccessible = true }
        val data = object : ComposedData(InputPointers(1), false, "") {
            override fun copyCodePointsExceptTrailingSingleQuotesAndReturnCodePointCount(destination: IntArray): Int {
                entered.countDown()
                check(release.await(5, TimeUnit.SECONDS))
                return 0 // Real JNI prediction path does not use a proximity handle.
            }
        }
        val worker = Thread {
            try {
                assertNotNull(dictionary.getSuggestions(data, NgramContext.EMPTY_PREV_WORDS_INFO,
                    0, SettingsValuesForSuggestion(true), 0, 1f, null))
            } catch (error: Throwable) { failure.set(error) }
            finally { completed.countDown() }
        }
        worker.start()
        try {
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            // Competing calls fail conservatively instead of touching shared traversal buffers.
            assertEquals(Dictionary.NOT_A_PROBABILITY, dictionary.getFrequency("utterleafqa"))
            assertFalse(dictionary.addUnigramEntry("denied", 100, false, false, false, 0))
            assertFalse(dictionary.flush())
            assertNull(dictionary.getNextWordProperty(0).mWordProperty)
            assertEquals(0, dictionary.getNextWordProperty(0).mNextToken)
            dictionary.close()
            dictionary.close()
            assertFalse(dictionary.isValidDictionary)
            assertNotEquals("Native dictionary deleted during an admitted operation", 0L, pointer.getLong(dictionary))
            assertEquals(1, (sessions.get(dictionary) as SparseArray<*>).size())
            release.countDown()
            assertTrue(completed.await(5, TimeUnit.SECONDS))
            failure.get()?.let { throw it }
            assertEquals(0L, pointer.getLong(dictionary))
            assertEquals(0, (sessions.get(dictionary) as SparseArray<*>).size())
            assertFalse(dictionary.flushWithGC())
            assertEquals(Dictionary.NOT_A_PROBABILITY, dictionary.getFrequency("utterleafqa"))
        } finally { release.countDown(); worker.join(5000); dictionary.close() }
    }

    @Test fun nestedNativeOperationsRecoverAfterBusyOwnerReleases() = fixture { directory ->
        val dictionary = BinaryDictionary(File(directory, "nested.dict").absolutePath, false,
            Locale.US, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en_US", "version" to "1"))
        try {
            assertTrue(dictionary.runWithNativeOperationForTesting {
                assertTrue(dictionary.addUnigramEntry("nestedqa", 200, false, false, false, 0))
                assertTrue(dictionary.flushWithGCIfHasUpdated())
                assertEquals(200, dictionary.getFrequency("nestedqa"))
            })
            assertTrue(dictionary.isValidDictionary)
            assertEquals(200, dictionary.getFrequency("nestedqa"))
            dictionary.close()
            assertFalse(dictionary.runWithNativeOperationForTesting { fail("Closed gate admitted work") })
        } finally { dictionary.close() }
    }

}
