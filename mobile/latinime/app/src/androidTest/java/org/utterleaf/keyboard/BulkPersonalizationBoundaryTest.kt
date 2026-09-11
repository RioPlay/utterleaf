package org.utterleaf.keyboard

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.BinaryDictionary
import com.android.inputmethod.latin.Dictionary
import com.android.inputmethod.latin.ExpandableBinaryDictionary
import com.android.inputmethod.latin.NgramContext
import com.android.inputmethod.latin.makedict.FormatSpec
import com.android.inputmethod.latin.utils.WordInputEventForPersonalization
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.lang.reflect.InvocationTargetException
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/** The legacy bulk path is explicitly unavailable; explicit single-entry operations still work. */
@RunWith(AndroidJUnit4::class)
class BulkPersonalizationBoundaryTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private fun fixture(test: (BinaryDictionary, File, Long) -> Unit) {
        val directory = File(context.cacheDir, "synthetic-bulk-boundary-${UUID.randomUUID()}")
        check(directory.mkdir())
        val file = File(directory, "fixture.dict")
        val dictionary = BinaryDictionary(file.absolutePath, false, Locale.US,
            Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en_US", "version" to "1"))
        try {
            assertTrue(dictionary.addUnigramEntry("preservedcanary", 200, false, false, false, 0))
            assertTrue(dictionary.flush())
            val before = snapshot(directory)
            val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                .apply { isAccessible = true }.getLong(dictionary)
            assertNotEquals(0L, handle)
            test(dictionary, file, handle)
            assertEquals(200, dictionary.getFrequency("preservedcanary"))
            assertEquals(Dictionary.NOT_A_PROBABILITY, dictionary.getFrequency("bulkcanary"))
            assertEquals(before, snapshot(directory))
            assertEquals(handle, BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                .apply { isAccessible = true }.getLong(dictionary))
        } finally { dictionary.close(); check(directory.deleteRecursively()) }
    }
    private fun snapshot(directory: File) = directory.walkTopDown().filter { it.isFile }
        .associate { it.relativeTo(directory).invariantSeparatorsPath to
            MessageDigest.getInstance("SHA-256").digest(it.readBytes())
                .joinToString("") { byte -> "%02x".format(byte) } }
    private fun event() = WordInputEventForPersonalization("bulkcanary",
        NgramContext.EMPTY_PREV_WORDS_INFO, 0)
    private fun unavailable(block: () -> Unit) {
        try { block(); fail("Legacy bulk personalization was accepted") }
        catch (error: UnsupportedOperationException) {
            assertEquals("Legacy bulk personalization is unavailable", error.message)
        }
    }

    @Test fun binaryWrapperRejectsSynchronouslyWithoutGcOrMutation() = fixture { dictionary, _, _ ->
        unavailable { dictionary.updateEntriesForInputEvents(arrayOf(event())) }
        unavailable { dictionary.updateEntriesForInputEvents(emptyArray()) }
        unavailable { dictionary.updateEntriesForInputEvents(null) }
    }

    private class Expandable(context: Context, file: File) : ExpandableBinaryDictionary(
        context, "synthetic-bulk-wrapper", Locale.US, Dictionary.TYPE_MAIN, file) {
        var initialLoads = 0
        override fun loadInitialContentsLocked() { initialLoads++ }
    }

    @Test fun expandableWrapperRejectsBeforeReloadQueueOrCompletionCallback() = fixture { dictionary, file, _ ->
        val wrapper = Expandable(context, file)
        val binary = ExpandableBinaryDictionary::class.java.getDeclaredField("mBinaryDictionary")
            .apply { isAccessible = true }
        binary.set(wrapper, dictionary)
        var callbacks = 0
        try {
            unavailable { wrapper.updateEntriesForInputEvents(arrayListOf(event())) { callbacks++ } }
            assertEquals(0, callbacks)
            assertEquals(0, wrapper.initialLoads)
            val reloading = ExpandableBinaryDictionary::class.java.getDeclaredField("mIsReloading")
                .apply { isAccessible = true }.get(wrapper) as AtomicBoolean
            assertFalse(reloading.get())
            assertSame(dictionary, binary.get(wrapper))
        } finally {
            // Constructor acquired no native resources; avoid scheduling its asynchronous close.
            binary.set(wrapper, null)
        }
    }

    @Test fun nativeStubRejectsMalformedArgumentsWithoutReadingThem() = fixture { dictionary, _, handle ->
        val method = BinaryDictionary::class.java.declaredMethods
            .single { it.name == "updateEntriesForInputEventsNative" }.apply { isAccessible = true }
        assertTrue(dictionary.runWithNativeOperationForTesting {
            for (events in listOf(null, emptyArray<WordInputEventForPersonalization>(),
                arrayOfNulls<WordInputEventForPersonalization>(1), arrayOf(event()))) {
                for (start in listOf(Int.MIN_VALUE, -1, 0, Int.MAX_VALUE)) {
                    try { method.invoke(null, handle, events, start); fail("Native bulk API accepted input") }
                    catch (error: InvocationTargetException) {
                        assertTrue(error.targetException is UnsupportedOperationException)
                        assertEquals("Legacy bulk personalization is unavailable", error.targetException.message)
                    }
                }
            }
        })
    }
}
