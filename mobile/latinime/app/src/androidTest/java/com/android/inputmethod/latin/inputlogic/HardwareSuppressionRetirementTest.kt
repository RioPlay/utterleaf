package com.android.inputmethod.latin.inputlogic

import android.view.inputmethod.InputConnection
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.LatinIME
import com.android.inputmethod.latin.Suggest
import com.android.inputmethod.latin.SuggestedWords
import org.utterleaf.keyboard.SuggestionDecoder
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.lang.reflect.Proxy
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** Hardware-suppression cleanup retires editor work while preserving an active session token. */
@RunWith(AndroidJUnit4::class)
class HardwareSuppressionRetirementTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private class Host {
        var finishes = 0
        val connection = Proxy.newProxyInstance(InputConnection::class.java.classLoader,
            arrayOf(InputConnection::class.java)) { _, method, _ ->
            check(method.name == "finishComposingText") {
                "Unexpected editor call: ${method.name}"
            }
            finishes++
            true
        } as InputConnection
    }

    private class TestIme : LatinIME() {
        val decoded = AtomicInteger()
        val editorLookups = AtomicInteger()
        var cleared = 0
        var decode: (Suggest.OnGetSuggestedWordsCallback) -> Unit = {
            it.onGetSuggestedWords(SuggestedWords.getEmptyInstance())
        }

        val inputLogic: InputLogic
            get() = LatinIME::class.java.getDeclaredField("mInputLogic")
                .apply { isAccessible = true }.get(this) as InputLogic

        override fun getCurrentInputConnection(): InputConnection? {
            editorLookups.incrementAndGet()
            return null
        }

        // Invocation spy only; base dictionary/view/accessibility cleanup is outside this test.
        override fun clearEditorTransientState() {
            cleared++
        }

        override fun captureSuggestionRequest(
            style: Int, sequence: Int
        ): SuggestionDecoder = SuggestionDecoder { callback ->
            decoded.incrementAndGet()
            decode(callback)
        }
    }

    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }

    private fun await(latch: CountDownLatch) {
        assertTrue("Queue did not complete", latch.await(5, TimeUnit.SECONDS))
    }

    private fun field(owner: Any, name: String) = owner.javaClass.getDeclaredField(name).apply {
        isAccessible = true
    }

    private fun cleanupForHardwareSuppression(ime: LatinIME) {
        LatinIME::class.java.getDeclaredMethod("cleanupInternalStateForFinishInput")
            .apply { isAccessible = true }.invoke(ime)
    }

    private fun uiMessage(name: String): Int = LatinIME.UIHandler::class.java
        .getDeclaredField(name).apply { isAccessible = true }.getInt(null)

    @Test
    fun cleanupRenewsActiveSessionAndRejectsQueuedAndLateWork() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val logic = main { ime.inputLogic }
        val worker = InputLogicHandler(ime, logic)
        main { field(logic, "mInputLogicHandler").set(logic, worker) }
        val host = Host()
        val entered = CountDownLatch(1)
        val releaseBarrier = CountDownLatch(1)
        val releaseDecoder = CountDownLatch(1)
        val running = CountDownLatch(1)
        val lateDone = CountDownLatch(1)
        val runningCallback = AtomicReference<Suggest.OnGetSuggestedWordsCallback>()
        val oldDelivered = AtomicInteger()
        val currentDelivered = CountDownLatch(1)
        try {
            ime.decode = { callback ->
                runningCallback.set(callback)
                running.countDown()
                assertTrue(releaseDecoder.await(5, TimeUnit.SECONDS))
            }
            // Hold the worker before the first request so the second request is definitely queued.
            worker.mNonUIThreadHandler.post {
                entered.countDown()
                assertTrue(releaseBarrier.await(5, TimeUnit.SECONDS))
            }
            await(entered)
            val oldIdentity = main {
                logic.mWordComposer.setBatchInputWord("synthetic-hardware-composition")
                field(logic.mConnection, "mIC").set(logic.mConnection, host.connection)
                field(logic, "mEnteredText").set(logic, "synthetic-entered")
                field(logic, "mWordBeingCorrectedByCursor").set(logic, "synthetic-correction")
                logic.mCurrentlyPressedHardwareKeys.add(17L)
                worker.onStartBatchInput()
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TAIL_BATCH, 1) {
                    oldDelivered.incrementAndGet()
                }
                ime.mEditorSession.capture()
            }
            // The first worker message must be allowed through the barrier to enter decoding.
            releaseBarrier.countDown()
            await(running)

            // Queue a second old request and two real UI results under the old identity.
            main {
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 2) {
                    oldDelivered.incrementAndGet()
                }
                val oldWords = SuggestedWords.getEmptyInstance()
                ime.mHandler.showSuggestionStrip(oldWords)
                ime.mHandler.showTailBatchInputResult(oldWords)
                assertTrue(ime.mEditorSession.isCurrent(oldIdentity))
                cleanupForHardwareSuppression(ime)
            }

            val renewedIdentity = main { ime.mEditorSession.capture() }
            assertNotSame(oldIdentity, renewedIdentity)
            assertTrue(renewedIdentity != null)
            main {
                assertFalse(worker.isInBatchInput)
                assertFalse(ime.mHandler.hasMessages(uiMessage("MSG_SHOW_GESTURE_PREVIEW_AND_SUGGESTION_STRIP")))
                assertFalse(ime.mHandler.hasMessages(uiMessage("MSG_UPDATE_TAIL_BATCH_INPUT_COMPLETED")))
                assertEquals("", logic.mWordComposer.typedWord)
                assertEquals(0, logic.mWordComposer.inputPointers.pointerSize)
                assertTrue(logic.mSuggestedWords.isEmpty())
                assertNull(field(logic, "mEnteredText").get(logic))
                assertNull(field(logic, "mWordBeingCorrectedByCursor").get(logic))
                assertTrue(logic.mCurrentlyPressedHardwareKeys.isEmpty())
                assertTrue(logic.isInputStateRetired)
                assertEquals(1, ime.cleared)
                assertEquals(0, ime.editorLookups.get())
                assertEquals(1, host.finishes)
            }

            // The decoder was admitted under the old identity; its completion is now stale.
            releaseDecoder.countDown()
            worker.mNonUIThreadHandler.post {
                runningCallback.get().onGetSuggestedWords(SuggestedWords.getEmptyInstance())
                lateDone.countDown()
            }
            await(lateDone)
            instrumentation.waitForIdleSync()
            assertEquals(0, oldDelivered.get())

            ime.decode = { it.onGetSuggestedWords(SuggestedWords.getEmptyInstance()) }
            main {
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 3) {
                    currentDelivered.countDown()
                }
            }
            await(currentDelivered)
            assertEquals(2, ime.decoded.get())
        } finally {
            releaseBarrier.countDown()
            releaseDecoder.countDown()
            worker.destroy()
            main {
                ime.mEditorSession.finish()
                ime.mHandler.removeAllMessages()
            }
        }
    }

    @Test
    fun cleanupDoesNotReopenAClosedSession() {
        val ime = main { TestIme() }
        val logic = main { ime.inputLogic }
        val worker = InputLogicHandler(ime, logic)
        main { field(logic, "mInputLogicHandler").set(logic, worker) }
        try {
            main {
                ime.mEditorSession.finish()
                cleanupForHardwareSuppression(ime)
                assertNull(ime.mEditorSession.capture())
                assertEquals(1, ime.cleared)
                assertEquals(0, ime.editorLookups.get())
            }
        } finally {
            worker.destroy()
            main { ime.mHandler.removeAllMessages() }
        }
    }
}
