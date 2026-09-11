package com.android.inputmethod.latin.inputlogic

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.Dictionary
import com.android.inputmethod.latin.LatinIME
import com.android.inputmethod.latin.Suggest
import com.android.inputmethod.latin.SuggestedWords
import com.android.inputmethod.latin.common.InputPointers
import org.utterleaf.keyboard.SuggestionDecoder
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** Deterministic queue boundaries; no real dictionary or timing-dependent decoding required. */
@RunWith(AndroidJUnit4::class)
class EditorSessionDispatchTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private class TestIme : LatinIME() {
        val decoded = AtomicInteger()
        val shown = ArrayList<SuggestedWords>()
        val inputLogic: InputLogic get() = LatinIME::class.java.getDeclaredField("mInputLogic")
            .apply { isAccessible = true }.get(this) as InputLogic
        var onCapture: () -> Unit = {}
        var decode: (Suggest.OnGetSuggestedWordsCallback) -> Unit = {
            it.onGetSuggestedWords(SuggestedWords.getEmptyInstance())
        }

        override fun captureSuggestionRequest(style: Int, sequence: Int): SuggestionDecoder {
            check(android.os.Looper.myLooper() == android.os.Looper.getMainLooper())
            onCapture()
            return SuggestionDecoder { callback ->
                decoded.incrementAndGet()
                decode(callback)
            }
        }

        override fun showSuggestionStrip(words: SuggestedWords) { shown.add(words) }
    }

    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }

    private fun await(latch: CountDownLatch) = assertTrue("Queue did not complete", latch.await(5, TimeUnit.SECONDS))

    @Test fun queuedOldRequestNeverStartsDecodingInNewSession() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val worker = InputLogicHandler(ime, null)
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val drained = CountDownLatch(1)
        val delivered = AtomicInteger()
        try {
            worker.mNonUIThreadHandler.post { entered.countDown(); release.await(5, TimeUnit.SECONDS) }
            await(entered)
            main { worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 1) { delivered.incrementAndGet() } }
            main { ime.mEditorSession.start() }
            worker.mNonUIThreadHandler.post { drained.countDown() }
            release.countDown()
            await(drained)
            assertEquals(0, ime.decoded.get())
            assertEquals(0, delivered.get())
        } finally {
            release.countDown()
            worker.destroy()
            main { ime.mHandler.removeAllMessages() }
        }
    }

    @Test fun inFlightOldCallbackIsRejectedAndCurrentWorkerCallbackStillCompletes() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val callback = AtomicReference<Suggest.OnGetSuggestedWordsCallback>()
        val computed = CountDownLatch(1)
        ime.decode = { callback.set(it); computed.countDown() }
        val worker = InputLogicHandler(ime, null)
        val delivered = AtomicInteger()
        try {
            main { worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 1) { delivered.incrementAndGet() } }
            await(computed)
            main { ime.mEditorSession.finish(); ime.mEditorSession.start() }
            val completed = CountDownLatch(1)
            worker.mNonUIThreadHandler.post {
                callback.get().onGetSuggestedWords(SuggestedWords.getEmptyInstance())
                completed.countDown()
            }
            await(completed)
            assertEquals(0, delivered.get())

            // The real typing path waits synchronously for a worker result. Do not marshal
            // this callback onto main, which would starve that waiting caller.
            ime.decode = { it.onGetSuggestedWords(SuggestedWords.getEmptyInstance()) }
            val current = CountDownLatch(1)
            main {
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 2) { current.countDown() }
                await(current)
            }
            assertEquals(2, ime.decoded.get())
        } finally {
            worker.destroy()
            main { ime.mHandler.removeAllMessages() }
        }
    }

    @Test fun resetEndsBatchEvenWhenOldTailCallbackIsRejected() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val callback = AtomicReference<Suggest.OnGetSuggestedWordsCallback>()
        val computed = CountDownLatch(1)
        ime.decode = { callback.set(it); computed.countDown() }
        val worker = InputLogicHandler(ime, null)
        val oldTailDelivered = AtomicInteger()
        try {
            worker.onStartBatchInput()
            assertTrue(worker.isInBatchInput)
            main { worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TAIL_BATCH, 1) { oldTailDelivered.incrementAndGet() } }
            await(computed)
            main {
                ime.mEditorSession.finish()
                worker.reset()
                ime.mEditorSession.start()
            }
            assertFalse(worker.isInBatchInput)
            worker.onStartBatchInput()
            val drained = CountDownLatch(1)
            worker.mNonUIThreadHandler.post {
                callback.get().onGetSuggestedWords(SuggestedWords.getEmptyInstance())
                drained.countDown()
            }
            await(drained)
            assertEquals(0, oldTailDelivered.get())
            assertTrue("Old completion must not cancel the new gesture", worker.isInBatchInput)
            worker.reset()
            assertFalse(worker.isInBatchInput)
        } finally {
            worker.destroy()
            main { ime.mHandler.removeAllMessages() }
        }
    }

    @Test fun queuedUiSuggestionsAndTailResultsCannotOutliveSession() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val word = SuggestedWords.SuggestedWordInfo("old-session-canary", "", 100,
            SuggestedWords.SuggestedWordInfo.KIND_TYPED, Dictionary.DICTIONARY_USER_TYPED,
            SuggestedWords.SuggestedWordInfo.NOT_AN_INDEX, SuggestedWords.SuggestedWordInfo.NOT_A_CONFIDENCE)
        val result = SuggestedWords(arrayListOf(word), null, word, true, false, false,
            SuggestedWords.INPUT_STYLE_TAIL_BATCH, 1)
        try {
            main {
                ime.mHandler.showSuggestionStrip(result)
                ime.mHandler.showTailBatchInputResult(result)
                // Both messages are enqueued, but cannot execute until this main task returns.
                ime.mEditorSession.finish()
                ime.mEditorSession.start()
            }
            instrumentation.waitForIdleSync()
            assertTrue(main { ime.shown.isEmpty() })
            main { ime.mHandler.showSuggestionStrip(result) }
            instrumentation.waitForIdleSync()
            assertEquals(listOf(result), main { ime.shown.toList() })
        } finally {
            main { ime.mHandler.removeAllMessages() }
        }
    }

    @Test fun cancelRejectsInFlightAndQueuedTailResultsWithoutClosingTheEditor() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val callback = AtomicReference<Suggest.OnGetSuggestedWordsCallback>()
        val computed = CountDownLatch(1)
        ime.decode = { callback.set(it); computed.countDown() }
        val worker = InputLogicHandler(ime, null)
        val delivered = AtomicInteger()
        val word = SuggestedWords.SuggestedWordInfo("cancelled-tail-canary", "", 100,
            SuggestedWords.SuggestedWordInfo.KIND_TYPED, Dictionary.DICTIONARY_USER_TYPED,
            SuggestedWords.SuggestedWordInfo.NOT_AN_INDEX, SuggestedWords.SuggestedWordInfo.NOT_A_CONFIDENCE)
        val result = SuggestedWords(arrayListOf(word), null, word, true, false, false,
            SuggestedWords.INPUT_STYLE_TAIL_BATCH, 1)
        try {
            worker.onStartBatchInput()
            main { worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TAIL_BATCH, 1) {
                delivered.incrementAndGet()
                ime.mHandler.showTailBatchInputResult(it)
            } }
            await(computed)
            main {
                ime.mHandler.showSuggestionStrip(result)
                ime.mHandler.showTailBatchInputResult(result)
                worker.onCancelBatchInput()
            }
            val drained = CountDownLatch(1)
            worker.mNonUIThreadHandler.post {
                callback.get().onGetSuggestedWords(result)
                drained.countDown()
            }
            await(drained)
            instrumentation.waitForIdleSync()
            assertEquals(0, delivered.get())
            assertTrue(main { ime.shown.isEmpty() })
            assertFalse(worker.isInBatchInput)

            ime.decode = { it.onGetSuggestedWords(result) }
            val current = CountDownLatch(1)
            main { worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 2) {
                ime.mHandler.showSuggestionStrip(it)
                current.countDown()
            } }
            await(current)
            instrumentation.waitForIdleSync()
            assertEquals(listOf(result), main { ime.shown.toList() })
            main {
                ime.mEditorSession.finish()
                worker.onCancelBatchInput()
                assertNull(ime.mEditorSession.capture())
            }
        } finally {
            worker.destroy()
            main { ime.mHandler.removeAllMessages() }
        }
    }

    @Test fun backgroundBatchCopiesPointersAndRejectsCanceledOwnerQueueWork() {
        val ime = main { TestIme().apply { mEditorSession.start(); decode = {} } }
        val worker = InputLogicHandler(ime, ime.inputLogic)
        val captured = ArrayList<IntArray>()
        ime.onCapture = {
            val points = ime.inputLogic.mWordComposer.inputPointers
            captured.add(intArrayOf(points.xCoordinates[0], points.yCoordinates[0],
                points.pointerIds[0], points.times[0]))
        }
        fun queueFromBackground(points: InputPointers) {
            val thread = Thread { worker.onUpdateBatchInput(points, 1) }
            thread.start()
            thread.join(5000)
            assertFalse("Background capture blocked waiting for the owner", thread.isAlive)
        }
        try {
            main {
                worker.onStartBatchInput()
                queueFromBackground(InputPointers(1).apply { addPointer(11, 21, 1, 31) })
                // Main is still occupied: the old update must not adopt the renewed session.
                worker.onCancelBatchInput()
                worker.onStartBatchInput()
            }
            instrumentation.waitForIdleSync()
            assertTrue(main { captured.isEmpty() })
            main {
                val points = InputPointers(1).apply { addPointer(12, 22, 2, 32) }
                queueFromBackground(points)
                points.xCoordinates[0] = 999
                points.yCoordinates[0] = 999
                points.pointerIds[0] = 999
                points.times[0] = 999
            }
            instrumentation.waitForIdleSync()
            main { assertArrayEquals(intArrayOf(12, 22, 2, 32), captured.single()) }
        } finally {
            main { worker.reset(); ime.mEditorSession.finish(); ime.mHandler.removeAllMessages() }
            worker.destroy()
        }
    }

    @Test fun recorrectionIndicatorChangesOnlyAtCurrentSessionUiDelivery() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val logic = ime.inputLogic
        val indicator = InputLogic::class.java.getDeclaredField("mIsAutoCorrectionIndicatorOn")
            .apply { isAccessible = true }
        val worker = InputLogicHandler(ime, logic)
        try {
            main {
                indicator.setBoolean(logic, true)
                val enqueued = CountDownLatch(1)
                worker.mNonUIThreadHandler.post {
                    logic.doShowSuggestionsAndClearAutoCorrectionIndicator(SuggestedWords.getEmptyInstance())
                    enqueued.countDown()
                }
                await(enqueued)
                assertTrue("Worker changed owner state", indicator.getBoolean(logic))
                ime.mEditorSession.start()
            }
            instrumentation.waitForIdleSync()
            main {
                assertTrue("Stale UI result changed the new session", indicator.getBoolean(logic))
                logic.doShowSuggestionsAndClearAutoCorrectionIndicator(SuggestedWords.getEmptyInstance())
            }
            instrumentation.waitForIdleSync()
            main { assertFalse(indicator.getBoolean(logic)) }
        } finally {
            worker.destroy()
            main { ime.mHandler.removeAllMessages() }
        }
    }

}
