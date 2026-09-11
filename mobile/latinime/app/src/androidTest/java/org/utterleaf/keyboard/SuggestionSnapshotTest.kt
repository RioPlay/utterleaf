package org.utterleaf.keyboard

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.event.Event
import com.android.inputmethod.latin.*
import com.android.inputmethod.latin.common.ComposedData
import com.android.inputmethod.latin.common.InputPointers
import com.android.inputmethod.latin.settings.SettingsValuesForSuggestion
import com.android.inputmethod.latin.utils.SuggestionResults
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.lang.reflect.Proxy
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/** Synthetic words only; pause at the dictionary boundary to expose reads after decoding. */
@RunWith(AndroidJUnit4::class)
class SuggestionSnapshotTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }

    private fun type(composer: WordComposer, text: String) {
        text.codePoints().toArray().forEach {
            composer.applyProcessedEvent(composer.processEvent(Event.createEventForCodePointFromUnknownSource(it)))
        }
    }

    @Test fun pointerArraysAndComposerFlagsAreDetachedFromSourceAndDecoderCopies() {
        main {
            val composer = WordComposer()
            composer.setBatchInputWord("AB7")
            composer.setCapitalizedModeAtStartComposingTime(WordComposer.CAPS_MODE_MANUAL_SHIFTED)
            composer.setRejectedBatchModeSuggestion("synthetic-rejected")
            val source = InputPointers(2).apply {
                addPointer(11, 21, 1, 31)
                addPointer(12, 22, 2, 32)
            }
            composer.setBatchInputPointers(source)
            val snapshot = SuggestionComposerSnapshot(composer)
            source.xCoordinates[0] = 111
            source.yCoordinates[0] = 121
            source.pointerIds[0] = 101
            source.times[0] = 131
            source.addPointer(13, 23, 3, 33)
            composer.reset()
            type(composer, "later")
            composer.setCapitalizedModeAtStartComposingTime(WordComposer.CAPS_MODE_OFF)
            assertEquals("AB7", snapshot.getTypedWord())
            assertTrue(snapshot.isBatchMode())
            assertTrue(snapshot.isComposingWord())
            assertTrue(snapshot.hasDigits())
            assertTrue(snapshot.isMostlyCaps())
            assertFalse(snapshot.isAllUpperCase())
            assertFalse(snapshot.isResumed())
            assertTrue(snapshot.wasShiftedNoLock())
            assertEquals("synthetic-rejected", snapshot.getRejectedBatchModeSuggestion())
            val first = snapshot.getComposedDataSnapshot().mInputPointers
            assertEquals(2, first.pointerSize)
            assertArrayEquals(intArrayOf(11, 12), first.xCoordinates.copyOf(2))
            assertArrayEquals(intArrayOf(21, 22), first.yCoordinates.copyOf(2))
            assertArrayEquals(intArrayOf(1, 2), first.pointerIds.copyOf(2))
            assertArrayEquals(intArrayOf(31, 32), first.times.copyOf(2))
            first.xCoordinates[0] = 999
            first.yCoordinates[0] = 999
            first.pointerIds[0] = 999
            first.times[0] = 999
            val second = snapshot.getComposedDataSnapshot().mInputPointers
            assertEquals(11, second.xCoordinates[0])
            assertEquals(21, second.yCoordinates[0])
            assertEquals(1, second.pointerIds[0])
            assertEquals(31, second.times[0])
        }
    }

    @Test fun contextSnapshotDetachesMutableWordsAndPreservesSentenceAndCapacity() {
        val mutableWord = StringBuilder("earlier")
        val words = arrayOf(NgramContext.WordInfo(mutableWord),
            NgramContext.WordInfo.BEGINNING_OF_SENTENCE_WORD_INFO)
        val snapshot = NgramContext(2, *words).snapshot()
        mutableWord.replace(0, mutableWord.length, "later")
        assertEquals("earlier", snapshot.getNthPrevWord(1).toString())
        assertTrue(snapshot.isNthPrevWordBeginningOfSentence(2))
        val next = snapshot.getNextNgramContext(NgramContext.WordInfo("next"))
        assertEquals(2, next.prevWordCount)
        assertEquals("earlier", next.getNthPrevWord(2).toString())
        assertFalse(NgramContext.EMPTY_PREV_WORDS_INFO.snapshot().isValid)
        assertTrue(NgramContext.BEGINNING_OF_SENTENCE.snapshot().isBeginningOfSentenceContext)
    }

    private fun delayedDecode(batch: Boolean) {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val finished = CountDownLatch(1)
        val observed = AtomicReference<ComposedData>()
        val result = AtomicReference<SuggestedWords>()
        val failure = AtomicReference<Throwable>()
        val composer = main {
            WordComposer().apply {
                if (batch) setBatchInputWord("AB") else type(this, "AB")
                setCapitalizedModeAtStartComposingTime(WordComposer.CAPS_MODE_MANUAL_SHIFT_LOCKED)
                inputPointers.addPointerAt(0, 11, 21, 1, 31)
            }
        }
        val snapshot = main { SuggestionComposerSnapshot(composer) }
        val facilitator = Proxy.newProxyInstance(DictionaryFacilitator::class.java.classLoader,
            arrayOf(DictionaryFacilitator::class.java)) { _, method, args ->
            when (method.name) {
                "getSuggestionResults" -> {
                    observed.set(args!![0] as ComposedData)
                    entered.countDown()
                    check(release.await(5, TimeUnit.SECONDS))
                    SuggestionResults(10, false, false).apply {
                        add(SuggestedWords.SuggestedWordInfo("alpha", "", 100,
                            SuggestedWords.SuggestedWordInfo.KIND_CORRECTION,
                            Dictionary.DICTIONARY_USER_TYPED,
                            SuggestedWords.SuggestedWordInfo.NOT_AN_INDEX,
                            SuggestedWords.SuggestedWordInfo.NOT_A_CONFIDENCE))
                    }
                }
                "getLocale" -> Locale.US
                "hasAtLeastOneInitializedMainDictionary" -> false
                else -> error("Unexpected dictionary call: ${method.name}")
            }
        } as DictionaryFacilitator
        val worker = Thread {
            try {
                Suggest(facilitator).getSuggestedWords(snapshot, NgramContext.EMPTY_PREV_WORDS_INFO,
                    null, SettingsValuesForSuggestion(true), false, 1f,
                    if (batch) SuggestedWords.INPUT_STYLE_TAIL_BATCH else SuggestedWords.INPUT_STYLE_TYPING,
                    7) { result.set(it) }
            } catch (error: Throwable) { failure.set(error) }
            finally { finished.countDown() }
        }
        worker.start()
        try {
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            // The owner must remain able to reset/type while dictionary decoding is blocked.
            main {
                composer.inputPointers.xCoordinates[0] = 999
                composer.reset()
                type(composer, "later")
                composer.setCapitalizedModeAtStartComposingTime(WordComposer.CAPS_MODE_OFF)
            }
            assertEquals("AB", observed.get().mTypedWord)
            assertEquals(11, observed.get().mInputPointers.xCoordinates[0])
            release.countDown()
            assertTrue(finished.await(5, TimeUnit.SECONDS))
            failure.get()?.let { throw it }
            val words = result.get()
            assertEquals(7, words.mSequenceNumber)
            assertEquals("ALPHA", words.getWord(if (batch) 0 else 1))
            if (!batch) assertEquals("AB", words.getWord(0))
        } finally {
            release.countDown()
            worker.join(5000)
            assertFalse("Decoder worker did not terminate", worker.isAlive)
        }
    }

    @Test fun typingResultUsesCapturedCapitalizationAfterLiveComposerReset() = delayedDecode(false)
    @Test fun gestureResultUsesCapturedCapitalizationAfterLiveComposerReset() = delayedDecode(true)
}
