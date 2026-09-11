package org.utterleaf.keyboard.next.core

import android.text.InputType
import android.view.inputmethod.BaseInputConnection
import android.view.inputmethod.EditorInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class EditorGatewayTest {
    private class AnyThread : MainThreadCheck { override fun check() = Unit }

    private class RecordingConnection : BaseInputConnection(android.view.View(
        androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().targetContext), false) {
        var committed = ""
        var beforeReads = 0
        var deletedCodePoints = 0
        var action = 0
        var before: CharSequence? = null
        var honorRequestedBeforeLength = false
        var commitResult = true
        var deleteResult = true
        var onCommit: (() -> Unit)? = null
        var onRead: (() -> Unit)? = null
        var onDelete: (() -> Unit)? = null

        override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
            committed += text ?: ""
            onCommit?.invoke()
            return commitResult
        }
        override fun getTextBeforeCursor(length: Int, flags: Int): CharSequence? {
            beforeReads++
            onRead?.invoke()
            val value = before ?: return null
            return if (honorRequestedBeforeLength && value.length > length) value.subSequence(value.length - length, value.length) else value
        }
        override fun deleteSurroundingTextInCodePoints(beforeLength: Int, afterLength: Int): Boolean {
            deletedCodePoints = beforeLength
            onDelete?.invoke()
            return deleteResult
        }
        override fun performEditorAction(editorAction: Int): Boolean {
            action = editorAction
            return true
        }
    }

    @Test fun staleTokenCannotWriteAfterCommitOrRetire() {
        val connection = RecordingConnection()
        val gateway = EditorGateway(AnyThread())
        val token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, 0, 0, 0)!!
        assertEquals(Outcome.APPLIED, gateway.commit(token, "a"))
        assertEquals(Outcome.STALE, gateway.commit(token, "b"))
        gateway.retire()
        assertEquals(Outcome.STALE, gateway.commit(gateway.currentToken() ?: token, "c"))
        assertEquals("a", connection.committed)
    }

    @Test fun sensitiveBackspaceNeverReadsContext() {
        val connection = RecordingConnection().apply { before = "secret" }
        val gateway = EditorGateway(AnyThread())
        val token = gateway.open(
            connection,
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD,
            0,
            2,
            2,
        )!!
        assertEquals(Outcome.APPLIED, gateway.backspace(token))
        assertEquals(0, connection.beforeReads)
        assertEquals(1, connection.deletedCodePoints)
    }

    @Test fun ordinaryBackspaceUsesWholeEmojiOrCombiningGrapheme() {
        fun deleteFor(before: String): Int {
            val connection = RecordingConnection().apply { this.before = before }
            val gateway = EditorGateway(AnyThread())
            val token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, 0, before.length, before.length)!!
            assertEquals(Outcome.APPLIED, gateway.backspace(token))
            return connection.deletedCodePoints
        }
        assertEquals(1, deleteFor("a😀"))
        assertEquals(2, deleteFor("e\u0301"))
    }

    @Test fun ordinaryBackspaceAcceptsProvenFinalClustersFromFullBoundedTail() {
        fun deleteFor(before: String): Int {
            val connection = RecordingConnection().apply {
                this.before = before
                honorRequestedBeforeLength = true
            }
            val gateway = EditorGateway(AnyThread())
            val token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, 0, before.length, before.length)!!
            assertEquals(Outcome.APPLIED, gateway.backspace(token))
            return connection.deletedCodePoints
        }
        assertEquals(1, deleteFor("a".repeat(200)))
        assertEquals(2, deleteFor("a".repeat(198) + "e\u0301"))
        assertEquals(2, deleteFor("a".repeat(198) + "\r\n"))
        assertEquals(7, deleteFor("a".repeat(190) + "👨‍👩‍👧‍👦"))
    }

    @Test fun ordinaryBackspaceRefusesAmbiguousOrOverlongBoundedContext() {
        fun outcomeFor(before: CharSequence, honorLimit: Boolean = true): Outcome {
            val connection = RecordingConnection().apply {
                this.before = before
                honorRequestedBeforeLength = honorLimit
            }
            val gateway = EditorGateway(AnyThread())
            val token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, 0, before.length, before.length)!!
            val outcome = gateway.backspace(token)
            assertEquals(0, connection.deletedCodePoints)
            return outcome
        }
        // The final flag's prior RI is not a proof of its pairing parity before the tail.
        assertEquals(Outcome.REFUSED, outcomeFor("a".repeat(116) + "🇺🇸🇨🇦🇩🇪"))
        assertEquals(Outcome.REFUSED, outcomeFor("\u0301".repeat(128)))
        assertEquals(Outcome.REFUSED, outcomeFor("a".repeat(127) + "\uD83D"))
        // A faulty host that ignores the requested maximum remains bounded and refused.
        assertEquals(Outcome.REFUSED, outcomeFor("a".repeat(129), honorLimit = false))
        val oversized = object : CharSequence {
            override val length = 129
            override fun get(index: Int): Char = error("Oversized context must not be read")
            override fun subSequence(startIndex: Int, endIndex: Int): CharSequence = error("Oversized context must not be copied")
            override fun toString(): String = error("Oversized context must be rejected before copying")
        }
        assertEquals(Outcome.REFUSED, outcomeFor(oversized, honorLimit = false))
    }

    @Test fun ordinaryDeletePredictsCaretForImmediateCommitAndCoalescedAck() {
        val before = "a😀"
        val connection = RecordingConnection().apply { this.before = before }
        val gateway = EditorGateway(AnyThread())
        var token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, 0, before.length, before.length)!!
        assertEquals(Outcome.APPLIED, gateway.backspace(token))
        token = gateway.currentToken()!!
        assertEquals(Outcome.APPLIED, gateway.commit(token, "x"))
        assertEquals(SelectionUpdate.OWN_ACK, gateway.updateSelection(1, 1, -1, -1))
        assertEquals(SelectionUpdate.OWN_ACK, gateway.updateSelection(2, 2, -1, -1))
        assertEquals("x", connection.committed)
    }

    @Test fun restrictedDeleteDoesNotReadAndWaitsForHostSelectionAck() {
        val connection = RecordingConnection().apply { before = "secret" }
        val gateway = EditorGateway(AnyThread())
        var token = gateway.open(
            connection,
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD,
            0,
            2,
            2,
        )!!
        assertEquals(Outcome.APPLIED, gateway.backspace(token))
        assertEquals(0, connection.beforeReads)
        token = gateway.currentToken()!!
        assertEquals(Outcome.REFUSED, gateway.backspace(token))
        assertEquals(SelectionUpdate.EXTERNAL, gateway.updateSelection(1, 1, -1, -1))
        token = gateway.currentToken()!!
        assertEquals(Outcome.APPLIED, gateway.backspace(token))
    }

    @Test fun enterUsesActionWithoutNewlineFallback() {
        val connection = RecordingConnection().apply { commitResult = false }
        val gateway = EditorGateway(AnyThread())
        val token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, EditorInfo.IME_ACTION_SEND, 0, 0)!!
        assertEquals(Outcome.APPLIED, gateway.enter(token))
        assertEquals(EditorInfo.IME_ACTION_SEND, connection.action)
        assertEquals("", connection.committed)
    }

    @Test fun namedEnterClearsCaretUntilHostAcknowledgement() {
        val connection = RecordingConnection()
        val gateway = EditorGateway(AnyThread())
        var token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, EditorInfo.IME_ACTION_SEND, 4, 4)!!
        assertEquals(Outcome.APPLIED, gateway.enter(token))
        token = gateway.currentToken()!!
        assertEquals(Outcome.REFUSED, gateway.backspace(token))
        assertEquals(SelectionUpdate.EXTERNAL, gateway.updateSelection(5, 5, -1, -1))
    }

    @Test fun ownSelectionAckIsDistinctFromExternalMove() {
        val connection = RecordingConnection()
        val gateway = EditorGateway(AnyThread())
        val token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, 0, 0, 0)!!
        assertEquals(Outcome.APPLIED, gateway.commit(token, "a"))
        assertEquals(SelectionUpdate.OWN_ACK, gateway.updateSelection(1, 1, -1, -1))
        assertEquals(SelectionUpdate.EXTERNAL, gateway.updateSelection(0, 0, -1, -1))
    }

    @Test fun rapidCommitsKeepPredictedCaretAcrossCoalescedAcks() {
        val connection = RecordingConnection()
        val gateway = EditorGateway(AnyThread())
        var token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, 0, 0, 0)!!
        assertEquals(Outcome.APPLIED, gateway.commit(token, "a"))
        token = gateway.currentToken()!!
        assertEquals(Outcome.APPLIED, gateway.commit(token, "b"))
        assertEquals(SelectionUpdate.OWN_ACK, gateway.updateSelection(1, 1, -1, -1))
        token = gateway.currentToken()!!
        assertEquals(Outcome.APPLIED, gateway.commit(token, "c"))
        assertEquals("abc", connection.committed)
    }

    @Test fun rawInputIsUnavailableInN1() {
        assertEquals(null, EditorGateway(AnyThread()).open(RecordingConnection(), InputType.TYPE_NULL, 0, 0, 0))
    }

    @Test fun missingInputTypeOpensOnlyWithConservativePolicy() {
        val gateway = EditorGateway(AnyThread())
        val token = gateway.open(RecordingConnection(), null, 0, 0, 0)!!
        assertTrue(token.policy.sensitive)
        assertTrue(gateway.effectiveIncognito())
    }

    @Test fun reentrantEditorCallsCannotAdvanceReplacementSession() {
        val gateway = EditorGateway(AnyThread())
        val connection = RecordingConnection()
        val token = gateway.open(connection, InputType.TYPE_CLASS_TEXT, 0, 0, 0)!!
        connection.onCommit = { gateway.retire() }
        assertEquals(Outcome.STALE, gateway.commit(token, "x"))
        assertEquals(null, gateway.currentToken())

        val readConnection = RecordingConnection().apply { before = "x" }
        val readToken = gateway.open(readConnection, InputType.TYPE_CLASS_TEXT, 0, 1, 1)!!
        readConnection.onRead = { gateway.open(RecordingConnection(), InputType.TYPE_CLASS_TEXT, 0, 0, 0) }
        assertEquals(Outcome.STALE, gateway.backspace(readToken))
        assertEquals(0, readConnection.deletedCodePoints)

        val deleteConnection = RecordingConnection()
        val deleteToken = gateway.open(
            deleteConnection,
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD,
            0,
            0,
            0,
        )!!
        deleteConnection.onDelete = { gateway.retire() }
        assertEquals(Outcome.STALE, gateway.backspace(deleteToken))
    }
}
