package org.utterleaf.keyboard.next.core

import android.text.InputType
import android.view.inputmethod.BaseInputConnection
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.ArrayDeque

@RunWith(AndroidJUnit4::class)
class SuggestionDispatcherTest {
    private class AnyThread : MainThreadCheck { override fun check() = Unit }
    private class Queue : TaskQueue {
        private val tasks = ArrayDeque<() -> Unit>()
        override fun post(task: () -> Unit) { tasks.addLast(task) }
        fun runOne() = tasks.removeFirst().invoke()
        fun hasTasks() = tasks.isNotEmpty()
    }
    private class Connection : BaseInputConnection(android.view.View(
        androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().targetContext), false) {
        override fun commitText(text: CharSequence?, newCursorPosition: Int) = true
    }

    @Test fun queuedWorkCannotPublishAfterManualIncognito() {
        val gateway = EditorGateway(AnyThread())
        val token = gateway.open(Connection(), InputType.TYPE_CLASS_TEXT, 0, 0, 0)!!
        val worker = Queue(); val main = Queue(); val published = mutableListOf<String>()
        val dispatcher = SuggestionDispatcher(gateway, worker, main, SuggestionDecoder { listOf("candidate") }) {
                _, values -> published += values
            }
        assertEquals(Outcome.APPLIED, dispatcher.submit(token, "context"))
        worker.runOne() // Decode has completed; delivery remains queued on main.
        gateway.setManualIncognito(true)
        main.runOne()
        assertTrue(published.isEmpty())
    }

    @Test fun staleRevisionCannotBeginDecode() {
        val gateway = EditorGateway(AnyThread())
        val connection = Connection()
        val token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, 0, 0, 0)!!
        val worker = Queue(); val main = Queue(); var decoded = false
        val dispatcher = SuggestionDispatcher(gateway, worker, main, SuggestionDecoder { decoded = true; emptyList() }) { _, _ -> }
        assertEquals(Outcome.APPLIED, dispatcher.submit(token, "context"))
        assertEquals(Outcome.APPLIED, gateway.commit(token, "x"))
        worker.runOne()
        assertFalse(decoded)
        assertTrue(!worker.hasTasks())
    }

    @Test fun manualPrivacyBeforeWorkerPreventsDecode() {
        val gateway = EditorGateway(AnyThread())
        val token = gateway.open(Connection(), InputType.TYPE_CLASS_TEXT, 0, 0, 0)!!
        val worker = Queue(); val main = Queue(); var decoded = false
        val dispatcher = SuggestionDispatcher(gateway, worker, main, SuggestionDecoder { decoded = true; emptyList() }) { _, _ -> }
        assertEquals(Outcome.APPLIED, dispatcher.submit(token, "context"))
        gateway.setManualIncognito(true)
        worker.runOne()
        assertFalse(decoded)
    }

    @Test fun cancelAndBoundsClearPendingWork() {
        val gateway = EditorGateway(AnyThread())
        val token = gateway.open(Connection(), InputType.TYPE_CLASS_TEXT, 0, 0, 0)!!
        val worker = Queue(); val main = Queue(); var decoded = false
        val dispatcher = SuggestionDispatcher(gateway, worker, main, SuggestionDecoder { decoded = true; emptyList() }) { _, _ -> }
        assertEquals(Outcome.REFUSED, dispatcher.submit(token, "x".repeat(257)))
        assertEquals(Outcome.APPLIED, dispatcher.submit(token, "context"))
        dispatcher.cancel()
        worker.runOne()
        assertFalse(decoded)
        assertFalse(main.hasTasks())
    }

    @Test fun publishedCandidatesAreBounded() {
        val gateway = EditorGateway(AnyThread())
        val token = gateway.open(Connection(), InputType.TYPE_CLASS_TEXT, 0, 0, 0)!!
        val worker = Queue(); val main = Queue(); var published = emptyList<String>()
        val dispatcher = SuggestionDispatcher(gateway, worker, main, SuggestionDecoder {
            listOf("a", "b", "c", "d", "z".repeat(65))
        }) { _, values -> published = values }
        assertEquals(Outcome.APPLIED, dispatcher.submit(token, "context"))
        worker.runOne(); main.runOne()
        assertEquals(listOf("a", "b", "c"), published)
    }
}
