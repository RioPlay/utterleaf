package com.android.inputmethod.latin.inputlogic

import android.os.Handler
import android.view.inputmethod.InputConnection
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.LatinIME
import com.android.inputmethod.latin.SuggestedWords
import com.android.inputmethod.latin.common.InputPointers
import org.utterleaf.keyboard.SuggestionDecoder
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/** No view lifecycle is invoked: local retirement must work independently of it. */
@RunWith(AndroidJUnit4::class)
class InputRetirementTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }
    private fun await(latch: CountDownLatch) = assertTrue(latch.await(5, TimeUnit.SECONDS))
    private fun field(owner: Any, name: String) = owner.javaClass.getDeclaredField(name)
        .apply { isAccessible = true }
    private class TestIme : LatinIME() {
        val decoded = AtomicInteger()
        val captured = AtomicInteger()
        val inputLogic get() = LatinIME::class.java.getDeclaredField("mInputLogic")
            .apply { isAccessible = true }.get(this) as InputLogic
        override fun getCurrentInputConnection(): InputConnection? = error("Retirement queried host editor")
        override fun captureSuggestionRequest(style: Int, sequence: Int): SuggestionDecoder {
            val snapshotText = inputLogic.mWordComposer.typedWord
            captured.incrementAndGet()
            return SuggestionDecoder {
                check(snapshotText.isNotEmpty())
                decoded.incrementAndGet()
                it.onGetSuggestedWords(SuggestedWords.getEmptyInstance())
            }
        }
    }

    @Test fun noViewRetirementDropsTextAndQueuedWorkWithoutEditorCallsAndAllowsNextSession() {
        val ime = main { TestIme().apply { mEditorSession.start() } }
        val logic = ime.inputLogic
        val worker = InputLogicHandler(ime, logic)
        main { field(logic, "mInputLogicHandler").set(logic, worker) }
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val drained = CountDownLatch(1)
        val stale = AtomicInteger()
        try {
            worker.mNonUIThreadHandler.post { entered.countDown(); release.await(5, TimeUnit.SECONDS) }
            await(entered)
            main {
                logic.mWordComposer.setBatchInputPointers(InputPointers(1).apply { addPointer(1, 2, 3, 4) })
                logic.mWordComposer.setBatchInputWord("synthetic-prior-editor")
                val cacheField = field(logic.mConnection, "mCommittedTextBeforeComposingText")
                val previousCache = cacheField.get(logic.mConnection) as StringBuilder
                previousCache.append("synthetic-private-prefix")
                worker.onStartBatchInput()
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 1) { stale.incrementAndGet() }
                assertEquals(1, ime.captured.get())
                val suggestionMessage = field(worker, "MSG_GET_SUGGESTED_WORDS").getInt(null)
                assertTrue(worker.mNonUIThreadHandler.hasMessages(suggestionMessage))
                worker.mNonUIThreadHandler.post { stale.incrementAndGet() }
                (field(worker, "mOwnerHandler").get(worker) as Handler).post { stale.incrementAndGet() }
                ime.mEditorSession.finish()
                logic.retireInput()
                assertNull(ime.mEditorSession.capture())
                assertTrue(logic.isInputStateRetired)
                assertEquals("", logic.mWordComposer.typedWord)
                assertEquals(0, logic.mWordComposer.inputPointers.pointerSize)
                assertNotSame(previousCache, cacheField.get(logic.mConnection))
                assertEquals("", cacheField.get(logic.mConnection).toString())
                assertFalse(logic.mConnection.isConnected)
                assertFalse(worker.isInBatchInput)
                assertFalse(worker.mNonUIThreadHandler.hasMessages(suggestionMessage))
                assertFalse(worker.mNonUIThreadHandler.hasMessages(0))
                assertFalse((field(worker, "mOwnerHandler").get(worker) as Handler).hasMessages(0))
                worker.mNonUIThreadHandler.post { drained.countDown() }
            }
            release.countDown(); await(drained)
            instrumentation.waitForIdleSync()
            assertEquals(0, stale.get()); assertEquals(0, ime.decoded.get())
            val fresh = CountDownLatch(1)
            main {
                ime.mEditorSession.start()
                logic.mWordComposer.setBatchInputWord("synthetic-next-editor")
                worker.getSuggestedWords(SuggestedWords.INPUT_STYLE_TYPING, 2) { fresh.countDown() }
            }
            await(fresh)
            assertEquals(1, ime.decoded.get())
        } finally {
            release.countDown()
            main { ime.mEditorSession.finish(); logic.destroy(); ime.mHandler.removeAllMessages() }
        }
    }
}
