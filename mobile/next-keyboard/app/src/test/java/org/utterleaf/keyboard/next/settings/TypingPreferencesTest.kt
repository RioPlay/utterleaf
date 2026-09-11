package org.utterleaf.keyboard.next.settings

import org.junit.Assert.*
import org.junit.Test
import org.utterleaf.keyboard.next.core.MainThreadCheck
import java.util.ArrayDeque
import java.util.concurrent.Executor

class TypingPreferencesTest {
    private class Storage : TypingStorage {
        var value = TypingOptions()
        var fail = false
        var writes = 0
        override fun read() = value
        override fun write(options: TypingOptions) { check(!fail); value = options; writes++ }
    }
    private class Fixture(val store: Storage = Storage()) {
        val work = ArrayDeque<Runnable>()
        val ui = ArrayDeque<() -> Unit>()
        val prefs = TypingPreferences(store, Executor { work.add(it) }, { ui.add(it) }, MainThreadCheck {})
        fun drain() { while (work.isNotEmpty()) work.removeFirst().run(); while (ui.isNotEmpty()) ui.removeFirst().invoke() }
    }
    @Test fun draftDiscardApplyAcknowledgementAndReopen() {
        val f = Fixture(); f.drain()
        f.prefs.edit(TypingOptions(numberRow = true, accentLongPress = false))
        assertEquals(TypingOptions(), f.prefs.state.saved)
        f.prefs.discard()
        assertEquals(TypingOptions(), f.prefs.state.draft)
        f.prefs.edit(TypingOptions(numberRow = true)); f.prefs.apply()
        f.work.removeFirst().run()
        assertFalse(f.prefs.state.saved.numberRow)
        f.ui.removeFirst().invoke()
        assertTrue(f.prefs.state.saved.numberRow)
        val reopened = Fixture(f.store); reopened.drain()
        assertTrue(reopened.prefs.state.saved.numberRow)
    }
    @Test fun failedWriteKeepsAppliedGeometryAndRetryPublishes() {
        val f = Fixture(); f.drain(); f.store.fail = true
        f.prefs.edit(TypingOptions(numberRow = true)); f.prefs.apply(); f.drain()
        assertTrue(f.prefs.state.failed)
        assertFalse(f.prefs.state.saved.numberRow)
        assertTrue(f.prefs.state.draft.numberRow)
        f.store.fail = false; f.prefs.apply(); f.drain()
        assertTrue(f.prefs.state.saved.numberRow)
        assertFalse(f.prefs.state.failed)
    }
    @Test fun pendingWriteRejectsEditsAndResetOnlyRestoresTypingDefaults() {
        val f = Fixture(); f.drain()
        f.prefs.edit(TypingOptions(true, false)); f.prefs.apply()
        f.prefs.edit(TypingOptions()); f.prefs.reset(); f.prefs.discard(); f.drain()
        assertEquals(TypingOptions(true, false), f.prefs.state.saved)
        assertEquals(1, f.store.writes)
        f.prefs.reset(); f.drain()
        assertEquals(TypingOptions(), f.store.value)
    }
}
