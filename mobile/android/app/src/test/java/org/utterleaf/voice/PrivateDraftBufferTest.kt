package org.utterleaf.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PrivateDraftBufferTest {
    @Test fun startsEmptyAndAcceptsExternalTextAndReversedSelection() {
        val buffer = PrivateDraftBuffer()
        assertEquals(PrivateDraftSnapshot("", 0, 0), buffer.current)
        assertFalse(buffer.canUndo)
        assertFalse(buffer.canRedo)

        assertTrue(buffer.acceptExternalEdit("A😀B", 3, 1))
        assertEquals(PrivateDraftSnapshot("A😀B", 3, 1), buffer.current)
        assertTrue(buffer.canUndo)
        assertFalse(buffer.canRedo)
    }

    @Test fun replacementUsesTheSelectedRangeAndKeepsCompleteUnicodeSequences() {
        val buffer = PrivateDraftBuffer()
        val replacement = "👩🏽‍⚕️"
        assertTrue(buffer.acceptExternalEdit("A😀B", 3, 1))
        assertTrue(buffer.replaceSelection(replacement))

        assertEquals("A${replacement}B", buffer.current.text)
        assertEquals(1 + replacement.length, buffer.current.selectionStart)
        assertEquals(buffer.current.selectionStart, buffer.current.selectionEnd)
        assertTrue(buffer.undo())
        assertEquals(PrivateDraftSnapshot("A😀B", 3, 1), buffer.current)
        assertTrue(buffer.redo())
        assertEquals("A${replacement}B", buffer.current.text)
    }

    @Test fun invalidUtf16RangesAndSurrogateBoundariesAreAtomic() {
        val buffer = PrivateDraftBuffer()
        assertTrue(buffer.acceptExternalEdit("A😀B", 0, 0))
        val before = buffer.current
        val undoBefore = buffer.canUndo
        val redoBefore = buffer.canRedo

        listOf(
            { buffer.acceptExternalEdit("\uD83D", 0, 0) },
            { buffer.acceptExternalEdit("\uDE00", 0, 0) },
            { buffer.acceptExternalEdit("A😀B", -1, 0) },
            { buffer.acceptExternalEdit("A😀B", 0, 5) },
            { buffer.acceptExternalEdit("A😀B", 2, 2) },
            { buffer.setSelection(2, 3) },
            { buffer.replaceSelection("\uD83D") },
        ).forEach { invalid ->
            assertFalse(invalid())
            assertEquals(before, buffer.current)
            assertEquals(undoBefore, buffer.canUndo)
            assertEquals(redoBefore, buffer.canRedo)
        }
    }

    @Test fun utf16LimitAcceptsExactBoundaryAndRejectsOverflowWithoutPartialEdit() {
        val buffer = PrivateDraftBuffer()
        val maximum = "a".repeat(PrivateDraftBuffer.MAX_UTF16_UNITS - 2) + "😀"
        assertEquals(PrivateDraftBuffer.MAX_UTF16_UNITS, maximum.length)
        assertTrue(buffer.acceptExternalEdit(maximum, maximum.length, maximum.length))
        val before = buffer.current

        assertFalse(buffer.replaceSelection("x"))
        assertEquals(before, buffer.current)
        assertFalse(buffer.acceptExternalEdit("x".repeat(PrivateDraftBuffer.MAX_UTF16_UNITS + 1), 0, 0))
        assertEquals(before, buffer.current)
        assertTrue(buffer.setSelection(maximum.length - 2, maximum.length))
        assertTrue(buffer.replaceSelection("ok"))
        assertEquals(PrivateDraftBuffer.MAX_UTF16_UNITS, buffer.current.text.length)
        assertTrue(buffer.current.text.endsWith("ok"))
    }

    @Test fun selectionOnlyChangesCreateNoHistoryAndPreserveRedo() {
        val buffer = PrivateDraftBuffer()
        assertTrue(buffer.acceptExternalEdit("a", 1, 1))
        assertTrue(buffer.acceptExternalEdit("ab", 2, 2))
        assertTrue(buffer.undo())
        assertEquals("a", buffer.current.text)
        assertTrue(buffer.canRedo)

        assertTrue(buffer.setSelection(0, 1))
        assertTrue(buffer.acceptExternalEdit("a", 1, 0))
        assertTrue(buffer.replaceSelection("a")) // Same text, collapsed selection only.
        assertTrue(buffer.canRedo)
        assertTrue(buffer.redo())
        assertEquals("ab", buffer.current.text)

        assertTrue(buffer.undo())
        assertTrue(buffer.undo())
        assertEquals("", buffer.current.text)
        assertFalse(buffer.undo())
    }

    @Test fun branchTextEditClearsRedoAndAcceptedNoOpsDoNot() {
        val buffer = PrivateDraftBuffer()
        assertTrue(buffer.acceptExternalEdit("one", 3, 3))
        assertTrue(buffer.acceptExternalEdit("two", 3, 3))
        assertTrue(buffer.undo())
        assertTrue(buffer.canRedo)
        assertTrue(buffer.setSelection(3, 3))
        assertTrue(buffer.acceptExternalEdit("one", 3, 3))
        assertTrue(buffer.canRedo)

        assertTrue(buffer.replaceSelection("!"))
        assertEquals("one!", buffer.current.text)
        assertFalse(buffer.canRedo)
        assertFalse(buffer.redo())
    }

    @Test fun combinedUndoRedoHistoryIsBoundedToTwentySnapshots() {
        val buffer = PrivateDraftBuffer()
        for (length in 1..25) {
            assertTrue(buffer.acceptExternalEdit("x".repeat(length), length, length))
        }
        var undoCount = 0
        while (buffer.undo()) undoCount++
        assertEquals(PrivateDraftBuffer.MAX_HISTORY_SNAPSHOTS, undoCount)
        assertEquals("x".repeat(5), buffer.current.text)

        var redoCount = 0
        while (buffer.redo()) redoCount++
        assertEquals(PrivateDraftBuffer.MAX_HISTORY_SNAPSHOTS, redoCount)
        assertEquals("x".repeat(25), buffer.current.text)
    }

    @Test fun clearErasesTextAndHistoryButAllowsAReusableEmptyDraft() {
        val buffer = PrivateDraftBuffer()
        assertTrue(buffer.acceptExternalEdit("private", 7, 7))
        assertTrue(buffer.acceptExternalEdit("private draft", 13, 13))
        assertTrue(buffer.undo())
        assertTrue(buffer.canRedo)

        assertTrue(buffer.clear())
        assertEquals(PrivateDraftSnapshot("", 0, 0), buffer.current)
        assertFalse(buffer.canUndo)
        assertFalse(buffer.canRedo)
        assertFalse(buffer.undo())
        assertFalse(buffer.redo())
        assertTrue(buffer.clear())
        assertTrue(buffer.replaceSelection("new"))
        assertEquals("new", buffer.current.text)
    }

    @Test fun disposeErasesEverythingAndPermanentlyRejectsMutations() {
        val buffer = PrivateDraftBuffer()
        assertTrue(buffer.acceptExternalEdit("secret", 6, 0))
        assertTrue(buffer.acceptExternalEdit("secret two", 10, 10))
        assertTrue(buffer.undo())
        buffer.dispose()

        assertTrue(buffer.isDisposed)
        assertEquals(PrivateDraftSnapshot("", 0, 0), buffer.current)
        assertFalse(buffer.canUndo)
        assertFalse(buffer.canRedo)
        assertFalse(buffer.acceptExternalEdit("later", 5, 5))
        assertFalse(buffer.replaceSelection("later"))
        assertFalse(buffer.setSelection(0, 0))
        assertFalse(buffer.undo())
        assertFalse(buffer.redo())
        assertFalse(buffer.clear())
        buffer.dispose()
        assertEquals(PrivateDraftSnapshot("", 0, 0), buffer.current)
    }
}
