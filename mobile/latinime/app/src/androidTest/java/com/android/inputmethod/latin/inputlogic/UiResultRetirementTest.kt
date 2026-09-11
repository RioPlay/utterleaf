package com.android.inputmethod.latin.inputlogic

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.LatinIME
import com.android.inputmethod.latin.PunctuationSuggestions
import com.android.inputmethod.latin.SuggestedWords
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Queue ownership checks only: the synthetic IME never delivers framework UI callbacks. */
@RunWith(AndroidJUnit4::class)
class UiResultRetirementTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private fun main(block: () -> Unit) {
        var failure: Throwable? = null
        instrumentation.runOnMainSync { try { block() } catch (error: Throwable) { failure = error } }
        failure?.let { throw it }
    }
    private fun message(name: String) = LatinIME.UIHandler::class.java.getDeclaredField(name)
        .apply { isAccessible = true }.getInt(null)

    @Test fun renewalDropsQueuedResultsPreservesSetupAndAllowsCurrentCancellationPreview() = main {
        val ime = LatinIME()
        val worker = InputLogicHandler(ime, null)
        val results = message("MSG_SHOW_GESTURE_PREVIEW_AND_SUGGESTION_STRIP")
        val tail = message("MSG_UPDATE_TAIL_BATCH_INPUT_COMPLETED")
        val cache = message("MSG_RESET_CACHES")
        val language = message("MSG_SWITCH_LANGUAGE_AUTOMATICALLY")
        val resume = message("MSG_RESUME_SUGGESTIONS_FOR_START_INPUT")
        val words = PunctuationSuggestions.newPunctuationSuggestions(arrayOf("synthetic-retained-result"))
        try {
            ime.mEditorSession.start()
            val oldIdentity = ime.mEditorSession.capture()
            // Use real enqueue methods for result payloads; setup messages are never dispatched.
            ime.mHandler.showSuggestionStrip(words)
            ime.mHandler.showTailBatchInputResult(words)
            ime.mHandler.postResetCaches(false, 1)
            ime.mHandler.sendEmptyMessage(language)
            ime.mHandler.sendEmptyMessage(resume)
            assertTrue(ime.mHandler.hasMessages(results))
            assertTrue(ime.mHandler.hasMessages(tail))
            worker.invalidatePendingRequests()
            assertFalse(ime.mEditorSession.isCurrent(oldIdentity))
            assertNotNull(ime.mEditorSession.capture())
            assertFalse("Queued suggestion words survived retirement", ime.mHandler.hasMessages(results))
            assertFalse("Queued tail words survived retirement", ime.mHandler.hasMessages(tail))
            assertTrue("Current start-view cache setup was removed", ime.mHandler.hasMessages(cache))
            assertTrue("Current language setup was removed", ime.mHandler.hasMessages(language))
            assertTrue("Current start-view resume setup was removed", ime.mHandler.hasMessages(resume))
            // InputLogic cancellation posts this after the invalidation boundary.
            ime.mHandler.showGesturePreviewAndSuggestionStrip(SuggestedWords.getEmptyInstance(), true)
            assertTrue("Current cancellation preview was discarded", ime.mHandler.hasMessages(results))
            ime.mHandler.showTailBatchInputResult(SuggestedWords.getEmptyInstance())
            assertTrue("Current result posting stopped working", ime.mHandler.hasMessages(tail))
        } finally {
            // All queue work is removed before yielding main; no fake service UI calls execute.
            ime.mHandler.removeAllMessages()
            worker.destroy()
            ime.mEditorSession.finish()
        }
    }

    @Test fun broadEditorRetirementAlsoDropsQueuedSuggestionAndTailPayloads() = main {
        val ime = LatinIME()
        val results = message("MSG_SHOW_GESTURE_PREVIEW_AND_SUGGESTION_STRIP")
        val tail = message("MSG_UPDATE_TAIL_BATCH_INPUT_COMPLETED")
        try {
            ime.mEditorSession.start()
            val words = PunctuationSuggestions.newPunctuationSuggestions(arrayOf("synthetic-finished-editor"))
            ime.mHandler.showGesturePreviewAndSuggestionStrip(words, false)
            ime.mHandler.showTailBatchInputResult(words)
            assertTrue(ime.mHandler.hasMessages(results)); assertTrue(ime.mHandler.hasMessages(tail))
            ime.mEditorSession.finish()
            ime.mHandler.cancelEditorWork()
            assertFalse(ime.mHandler.hasMessages(results)); assertFalse(ime.mHandler.hasMessages(tail))
        } finally { ime.mHandler.removeAllMessages(); ime.mEditorSession.finish() }
    }
}
