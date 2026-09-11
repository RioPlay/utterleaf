package org.utterleaf.keyboard

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.android.inputmethod.event.Event
import com.android.inputmethod.latin.WordComposer
import com.android.inputmethod.latin.common.InputPointers
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ComposerLifetimeTest {
    @Test fun everyNativeCarrierPreservesTheCapturedEditorIdentity() {
        val session = EditorSession().apply { start() }
        val identity = session.capture()
        val snapshot = SuggestionComposerSnapshot(WordComposer()) { session.isCurrent(identity) }
        val first = snapshot.getComposedDataSnapshot()
        val second = snapshot.getComposedDataSnapshot()
        assertTrue(first.isRequestCurrent)
        assertTrue(second.isRequestCurrent)
        session.finish()
        session.start()
        assertFalse(first.isRequestCurrent)
        assertFalse(second.isRequestCurrent)
        assertFalse(snapshot.getComposedDataSnapshot().isRequestCurrent)
    }

    private fun path() = InputPointers(3).apply {
        addPointer(11, 21, 1, 31); addPointer(12, 22, 2, 32); addPointer(13, 23, 3, 33)
    }

    @Test fun fullResetDetachesPreviousPathWithoutChangingSharedOwner() {
        val path = path()
        val composer = WordComposer()
        composer.setBatchInputPointers(path)
        composer.setBatchInputWord("synthetic")
        composer.reset()
        assertEquals("", composer.typedWord)
        assertFalse(composer.isBatchMode)
        assertEquals(0, composer.inputPointers.pointerSize)
        assertNotSame(path.xCoordinates, composer.inputPointers.xCoordinates)
        assertNotSame(path.yCoordinates, composer.inputPointers.yCoordinates)
        assertNotSame(path.pointerIds, composer.inputPointers.pointerIds)
        assertNotSame(path.times, composer.inputPointers.times)
        assertEquals(3, path.pointerSize)
        assertArrayEquals(intArrayOf(11, 12, 13), path.xCoordinates.copyOf(3))
        // A shorter new composition cannot inherit the old gesture tail.
        composer.applyProcessedEvent(composer.processEvent(Event.createEventForCodePointFromUnknownSource('a'.code)))
        assertEquals(1, composer.inputPointers.pointerSize)
        assertEquals(1, SuggestionComposerSnapshot(composer).getComposedDataSnapshot().mInputPointers.pointerSize)
    }

    @Test fun replacingGestureTextPreservesItsPathAndCapitalization() {
        val path = path()
        val composer = WordComposer()
        composer.setBatchInputPointers(path)
        composer.setCapitalizedModeAtStartComposingTime(WordComposer.CAPS_MODE_MANUAL_SHIFTED)
        composer.setBatchInputWord("first")
        composer.setBatchInputWord("second")
        assertEquals("second", composer.typedWord)
        assertTrue(composer.isBatchMode)
        assertTrue(composer.wasShiftedNoLock())
        assertEquals(3, composer.inputPointers.pointerSize)
        assertArrayEquals(intArrayOf(31, 32, 33), composer.inputPointers.times.copyOf(3))
    }
}
