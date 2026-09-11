package com.android.inputmethod.latin.inputlogic

import android.os.Handler
import android.view.inputmethod.InputConnection
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
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

/** Controlled lifecycle/queue checks; actual subtype typing belongs to the framework IME fixture. */
@RunWith(AndroidJUnit4::class)
class SubtypeLifecycleTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }
    private fun await(latch: CountDownLatch) =
        assertTrue("Controlled queue did not complete", latch.await(5, TimeUnit.SECONDS))

    private class TestIme : LatinIME() {
        val decoded = AtomicInteger()
        var decode: (Suggest.OnGetSuggestedWordsCallback) -> Unit = {
            it.onGetSuggestedWords(SuggestedWords.getEmptyInstance())
        }
        override fun getCurrentInputConnection(): InputConnection? =
            error("Inactive subtype must not look up an editor")
        override fun captureSuggestionRequest(style: Int, sequence: Int) = SuggestionDecoder {
            decoded.incrementAndGet()
            decode(it)
        }
    }
    private fun logic(ime: LatinIME) = LatinIME::class.java.getDeclaredField("mInputLogic")
        .apply { isAccessible = true }.get(ime) as InputLogic
    private fun field(owner: Any, name: String) = owner.javaClass.getDeclaredField(name)
        .apply { isAccessible = true }

    @Test fun inactiveSubtypeClearsLocalCachesWithoutEditorLookupOrSessionReopening() {
        val ime = main { TestIme() }
        val logic = logic(ime)
        try {
            main {
                logic.mWordComposer.setBatchInputPointers(InputPointers(1).apply { addPointer(1, 2, 3, 4) })
                logic.mWordComposer.setBatchInputWord("synthetic-ended-composition")
                val cached = field(logic.mConnection, "mCommittedTextBeforeComposingText")
                    .get(logic.mConnection) as StringBuilder
                cached.append("synthetic-ended-prefix")
                // No settings needed: an inactive editor must return before startInput.
                logic.onSubtypeChanged("synthetic-next-spec", null)
                assertNull(ime.mEditorSession.capture())
                assertEquals("", logic.mWordComposer.typedWord)
                assertEquals(0, logic.mWordComposer.inputPointers.pointerSize)
                assertNotSame(cached, field(logic.mConnection, "mCommittedTextBeforeComposingText")
                    .get(logic.mConnection))
                assertEquals("", field(logic.mConnection, "mCommittedTextBeforeComposingText")
                    .get(logic.mConnection).toString())
                assertFalse(logic.mConnection.isConnected)
            }
        } finally { main { logic.destroy(); ime.mHandler.removeAllMessages() } }
    }

    @Test fun subtypeRequestInvalidationRejectsInFlightResultAndKeepsCurrentRequestsWorking() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val worker = InputLogicHandler(ime, logic(ime))
        val callback = AtomicReference<Suggest.OnGetSuggestedWordsCallback>()
        val captured = CountDownLatch(1)
        val delivered = AtomicInteger()
        ime.decode = { callback.set(it); captured.countDown() }
        try {
            val oldIdentity = main {
                val identity = ime.mEditorSession.capture()
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 1) { delivered.incrementAndGet() }
                identity
            }
            await(captured)
            main {
                worker.invalidatePendingRequests()
                assertFalse(ime.mEditorSession.isCurrent(oldIdentity))
                assertNotNull(ime.mEditorSession.capture())
            }
            val completed = CountDownLatch(1)
            worker.mNonUIThreadHandler.post {
                callback.get().onGetSuggestedWords(SuggestedWords.getEmptyInstance())
                completed.countDown()
            }
            await(completed)
            assertEquals(0, delivered.get())
            ime.decode = { it.onGetSuggestedWords(SuggestedWords.getEmptyInstance()) }
            val current = CountDownLatch(1)
            main { worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 2) { current.countDown() } }
            await(current)
            assertEquals(2, ime.decoded.get())
            main {
                ime.mEditorSession.finish()
                worker.invalidatePendingRequests()
                assertNull(ime.mEditorSession.capture())
            }
        } finally { worker.destroy(); main { ime.mEditorSession.finish(); ime.mHandler.removeAllMessages() } }
    }

    @Test fun cancellationRemovesBothQueuedOwnersAndDecodersBeforeTheyExecute() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val worker = InputLogicHandler(ime, logic(ime))
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val drained = CountDownLatch(1)
        val retainedQueueMarker = AtomicInteger()
        try {
            worker.mNonUIThreadHandler.post { entered.countDown(); release.await(5, TimeUnit.SECONDS) }
            await(entered)
            main {
                worker.onStartBatchInput()
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 1) { retainedQueueMarker.incrementAndGet() }
                worker.mNonUIThreadHandler.post { retainedQueueMarker.incrementAndGet() }
                val owner = field(worker, "mOwnerHandler").get(worker) as Handler
                owner.post { retainedQueueMarker.incrementAndGet() }
                worker.onCancelBatchInput()
                assertFalse(worker.isInBatchInput)
                worker.mNonUIThreadHandler.post { drained.countDown() }
            }
            release.countDown()
            await(drained)
            instrumentation.waitForIdleSync()
            assertEquals(0, ime.decoded.get())
            assertEquals("Cancellation retained queued closures", 0, retainedQueueMarker.get())
        } finally {
            release.countDown(); worker.destroy()
            main { ime.mEditorSession.finish(); ime.mHandler.removeAllMessages() }
        }
    }
}
