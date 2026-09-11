package org.utterleaf.keyboard.next.settings

import org.junit.Assert.*
import org.junit.Test
import org.utterleaf.keyboard.next.core.MainThreadCheck
import java.util.ArrayDeque
import java.util.concurrent.Executor

class PrivacyPreferencesTest {
    private class Storage : PrivacyStorage {
        var value = false
        var fail = false
        var writes = 0
        override fun read() = value
        override fun write(incognito: Boolean) {
            writes++
            check(!fail)
            value = incognito
        }
    }
    private class Fixture(val store: Storage = Storage()) {
        val work = ArrayDeque<Runnable>()
        val ui = ArrayDeque<() -> Unit>()
        val prefs = PrivacyPreferences(store, Executor { work.add(it) }, { ui.add(it) }, MainThreadCheck {})
        fun drain() { while (work.isNotEmpty()) work.removeFirst().run(); while (ui.isNotEmpty()) ui.removeFirst().invoke() }
    }

    @Test fun enterIsImmediateExitWaitsForAcknowledgementAndResetPreservesChoice() {
        val f = Fixture()
        assertTrue(f.prefs.state.incognito)
        f.drain()
        assertFalse(f.prefs.state.incognito)
        f.prefs.setIncognito(true)
        assertTrue(f.prefs.state.incognito)
        assertTrue(f.prefs.state.saving)
        f.drain()
        f.prefs.resetPreferences()
        assertTrue(f.prefs.state.incognito)
        f.prefs.setIncognito(false)
        assertTrue(f.prefs.state.incognito)
        f.work.removeFirst().run()
        assertTrue(f.prefs.state.incognito)
        f.ui.removeFirst().invoke()
        assertFalse(f.prefs.state.incognito)
    }

    @Test fun failedSaveStaysPrivateAndRetryRestoresDurableChoice() {
        val f = Fixture(); f.drain(); f.store.fail = true
        f.prefs.setIncognito(true); f.drain()
        assertTrue(f.prefs.state.failed)
        assertTrue(f.prefs.state.incognito)
        assertFalse(f.store.value)
        f.store.fail = false; f.prefs.retry(); f.drain()
        assertFalse(f.prefs.state.failed)
        val restarted = Fixture(f.store); restarted.drain()
        assertTrue(restarted.prefs.state.incognito)
    }

    @Test fun pendingWriteRejectsOverlappingToggleAndRemovedObserverGetsNoDelivery() {
        val f = Fixture(); f.drain()
        var callbacks = 0
        val listener: (PrivacyPreferences.State) -> Unit = { callbacks++ }
        f.prefs.observe(listener)
        f.prefs.setIncognito(true)
        f.prefs.setIncognito(false)
        f.prefs.removeObserver(listener)
        val before = callbacks; f.drain()
        assertEquals(before, callbacks)
        assertTrue(f.store.value)
        assertEquals(1, f.store.writes)
    }
}
