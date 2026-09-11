package org.utterleaf.keyboard

import android.content.Context
import android.util.SparseArray
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.*
import com.android.inputmethod.latin.common.ComposedData
import com.android.inputmethod.latin.common.InputPointers
import com.android.inputmethod.latin.makedict.FormatSpec
import com.android.inputmethod.latin.settings.SettingsValuesForSuggestion
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.Locale
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import java.util.function.BooleanSupplier

/** Real synthetic native sessions, with deterministic pauses inside dictionary admission. */
@RunWith(AndroidJUnit4::class)
class NativeSessionRetirementTest {
    private fun fixture(test: (BinaryDictionary, File) -> Unit) {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-session-retirement-${UUID.randomUUID()}")
        check(directory.mkdir())
        val file = File(directory, "fixture.dict")
        val dictionary = BinaryDictionary(file.absolutePath, false, Locale.US,
            Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en_US", "version" to "1"))
        try {
            assertTrue(dictionary.addUnigramEntry("sessioncanary", 200, false, false, false, 0))
            assertTrue(dictionary.flush())
            assertTrue(file.isDirectory)
            test(dictionary, file)
        } finally { dictionary.close(); check(directory.deleteRecursively()) }
    }

    private fun handle(dictionary: BinaryDictionary) = BinaryDictionary::class.java
        .getDeclaredField("mNativeDict").apply { isAccessible = true }.getLong(dictionary)

    @Suppress("UNCHECKED_CAST")
    private fun sessions(dictionary: BinaryDictionary) = BinaryDictionary::class.java
        .getDeclaredField("mDicTraverseSessions").apply { isAccessible = true }
        .get(dictionary) as SparseArray<DicTraverseSession>

    private fun prediction(dictionary: BinaryDictionary,
                           data: ComposedData = ComposedData(InputPointers(1), false, ""),
                           id: Int = 0) = dictionary.getSuggestions(data,
        NgramContext.EMPTY_PREV_WORDS_INFO, 0, SettingsValuesForSuggestion(true), id, 1f, null)

    private fun snapshot(editor: EditorSession): ComposedData {
        val identity = editor.capture()
        return SuggestionComposerSnapshot(WordComposer(), BooleanSupplier {
            editor.isCurrent(identity)
        }).getComposedDataSnapshot()
    }

    private fun bytes(path: File): Map<String, List<Byte>> = path.walkTopDown().filter { it.isFile }
        .associate { it.relativeTo(path).invariantSeparatorsPath to it.readBytes().toList() }

    @Test fun idleClearClosesAllTraversalSessionsWhileDictionaryAndFileRemainIntact() = fixture { dictionary, file ->
        val originalBytes = bytes(file)
        val dictionaryHandle = handle(dictionary)
        assertNotNull(prediction(dictionary, id = 0))
        assertNotNull(prediction(dictionary, id = 1))
        val retired = listOf(sessions(dictionary).get(0), sessions(dictionary).get(1))
        retired.forEach { assertNotEquals(0L, it.session) }
        dictionary.clearSession()
        dictionary.clearSession()
        assertEquals(0, sessions(dictionary).size())
        retired.forEach { assertEquals(0L, it.session) }
        assertEquals(dictionaryHandle, handle(dictionary))
        assertTrue(dictionary.isValidDictionary)
        assertEquals(200, dictionary.getFrequency("sessioncanary"))
        assertEquals(originalBytes, bytes(file))
        assertNotNull(prediction(dictionary))
        assertNotSame(retired[0], sessions(dictionary).get(0))
    }

    @Test fun clearDuringAdmittedDecodeDefersSessionCloseUntilLeaseReturn() = fixture { dictionary, file ->
        val editor = EditorSession().apply { start() }
        val identity = editor.capture()
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val completed = CountDownLatch(1)
        val failure = AtomicReference<Throwable>()
        val retired = AtomicReference<DicTraverseSession>()
        val dictionaryHandle = handle(dictionary)
        val originalBytes = bytes(file)
        val data = object : ComposedData(InputPointers(1), false, "") {
            override fun isRequestCurrent() = editor.isCurrent(identity)
            override fun copyCodePointsExceptTrailingSingleQuotesAndReturnCodePointCount(destination: IntArray): Int {
                // getSuggestions has admitted the operation and created its real native session.
                retired.set(sessions(dictionary).get(0))
                entered.countDown()
                check(release.await(5, TimeUnit.SECONDS))
                return 0
            }
        }
        val worker = Thread {
            try { assertNotNull(prediction(dictionary, data)) }
            catch (error: Throwable) { failure.set(error) }
            finally { completed.countDown() }
        }
        worker.start()
        try {
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            editor.finish()
            dictionary.clearSession()
            // The caller returned while the decoder is still deliberately paused.
            assertEquals(1L, release.count)
            assertEquals(1L, completed.count)
            assertNotEquals(0L, retired.get().session)
            assertEquals(dictionaryHandle, handle(dictionary))
            release.countDown()
            assertTrue(completed.await(5, TimeUnit.SECONDS))
            failure.get()?.let { throw it }
            assertEquals(0L, retired.get().session)
            assertEquals(0, sessions(dictionary).size())
            assertEquals(dictionaryHandle, handle(dictionary))
            assertTrue(dictionary.isValidDictionary)
            assertEquals(200, dictionary.getFrequency("sessioncanary"))
            assertEquals(originalBytes, bytes(file))
        } finally { release.countDown(); worker.join(5000) }
    }

    @Test fun staleSnapshotCannotRecreateSessionAfterRetirementButFreshIdentityCan() = fixture { dictionary, _ ->
        val editor = EditorSession().apply { start() }
        val stale = snapshot(editor)
        // Model the worker's earlier precheck passing before dictionary admission.
        assertTrue(stale.isRequestCurrent)
        assertNotNull(prediction(dictionary, stale))
        val old = sessions(dictionary).get(0)
        editor.finish()
        dictionary.clearSession()
        assertEquals(0L, old.session)
        assertNull(prediction(dictionary, stale))
        assertEquals(0, sessions(dictionary).size())
        editor.start()
        assertNull(prediction(dictionary, stale))
        assertNotNull(prediction(dictionary, snapshot(editor)))
        assertEquals(1, sessions(dictionary).size())
        assertNotSame(old, sessions(dictionary).get(0))
        assertNotEquals(0L, sessions(dictionary).get(0).session)
    }

    private class ControlledFacilitator(private val mainDictionary: Dictionary) : DictionaryFacilitatorImpl() {
        val queued = ArrayList<Runnable>()
        override fun executeDictionaryLoad(task: Runnable) { queued.add(task) }
        override fun createMainDictionary(context: Context, locale: Locale): Dictionary = mainDictionary
    }

    @Test fun facilitatorAndCollectionForwardRetirementWithoutClosingSharedDictionary() = fixture { dictionary, _ ->
        val collection = DictionaryCollection(Dictionary.TYPE_MAIN, Locale.US, dictionary)
        val facilitator = ControlledFacilitator(collection)
        try {
            facilitator.resetDictionaries(InstrumentationRegistry.getInstrumentation().targetContext,
                Locale.US, false, false, false, null, "", null)
            assertEquals(1, facilitator.queued.size)
            facilitator.queued.single().run()
            assertNotNull(prediction(dictionary))
            val retired = sessions(dictionary).get(0)
            facilitator.clearSession()
            assertEquals(0L, retired.session)
            assertEquals(0, sessions(dictionary).size())
            assertTrue(dictionary.isValidDictionary)
            assertEquals(200, dictionary.getFrequency("sessioncanary"))
        } finally { facilitator.closeDictionaries() }
    }
}
