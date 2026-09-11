package com.android.inputmethod.latin

import android.content.Context
import android.os.Looper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.common.ComposedData
import com.android.inputmethod.latin.settings.SettingsValuesForSuggestion
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** Per-instance controlled load queue; no global executor replacement or real vocabulary. */
@RunWith(AndroidJUnit4::class)
class DictionaryLoadLifecycleTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext

    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }

    private class FakeDictionary(locale: Locale) : Dictionary(TYPE_MAIN, locale) {
        val closes = AtomicInteger()
        var beforeClose: () -> Unit = {}
        override fun close() { closes.incrementAndGet(); beforeClose() }
        override fun isInDictionary(word: String) = false
        override fun getSuggestions(data: ComposedData, context: NgramContext, proximity: Long,
            settings: SettingsValuesForSuggestion, session: Int, weight: Float, weights: FloatArray?):
            ArrayList<SuggestedWords.SuggestedWordInfo>? = null
    }

    private class ControlledFacilitator : DictionaryFacilitatorImpl() {
        val queued = ArrayList<Runnable>()
        val loads = AtomicInteger()
        var factory: (Locale) -> Dictionary = { FakeDictionary(it) }
        override fun executeDictionaryLoad(task: Runnable) { queued.add(task) }
        override fun createMainDictionary(context: Context, locale: Locale): Dictionary {
            loads.incrementAndGet()
            return factory(locale)
        }
    }

    private fun reset(facilitator: ControlledFacilitator, locale: Locale,
        listener: DictionaryFacilitator.DictionaryInitializationListener? = null, force: Boolean = false) {
        facilitator.resetDictionaries(context, locale, false, false, force, null, "", listener)
    }

    private fun loadLatch(facilitator: ControlledFacilitator): CountDownLatch =
        DictionaryFacilitatorImpl::class.java.getDeclaredField("mLatchForWaitingLoadingMainDictionaries")
            .apply { isAccessible = true }.get(facilitator) as CountDownLatch

    private fun runTask(task: Runnable) {
        val failure = AtomicReference<Throwable>()
        val thread = Thread { try { task.run() } catch (error: Throwable) { failure.set(error) } }
        thread.start()
        thread.join(5000)
        assertFalse("Dictionary task blocked", thread.isAlive)
        failure.get()?.let { throw it }
    }

    @Test fun obsoleteQueuedSameLocaleLoadNeverOpensOrNotifies() {
        val facilitator = ControlledFacilitator()
        val oldEvents = ArrayList<Boolean>()
        val currentEvents = ArrayList<Boolean>()
        val oldLatch = main {
            reset(facilitator, Locale.US, { oldEvents.add(it) })
            val latch = loadLatch(facilitator)
            reset(facilitator, Locale.US, {
                assertEquals(Looper.getMainLooper(), Looper.myLooper())
                currentEvents.add(it)
            }, force = true)
            latch
        }
        instrumentation.waitForIdleSync()
        val oldCount = main { oldEvents.size }
        try {
            runTask(facilitator.queued[0])
            assertEquals(0, facilitator.loads.get())
            assertEquals(0L, oldLatch.count)
            runTask(facilitator.queued[1])
            instrumentation.waitForIdleSync()
            assertEquals(1, facilitator.loads.get())
            main {
                assertEquals(oldCount, oldEvents.size)
                assertEquals(true, currentEvents.last())
            }
        } finally { main { facilitator.closeDictionaries() } }
    }

    @Test fun closeDuringLoadReturnsWithoutWaitingAndDisposesObsoleteResult() {
        val facilitator = ControlledFacilitator()
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val finished = CountDownLatch(1)
        val dictionary = FakeDictionary(Locale.US)
        val events = ArrayList<Boolean>()
        facilitator.factory = {
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            dictionary
        }
        val latch = main { reset(facilitator, Locale.US, { events.add(it) }); loadLatch(facilitator) }
        instrumentation.waitForIdleSync()
        val before = main { events.size }
        val failure = AtomicReference<Throwable>()
        val worker = Thread {
            try { facilitator.queued.single().run() }
            catch (error: Throwable) { failure.set(error) }
            finally { finished.countDown() }
        }
        worker.start()
        try {
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            main { facilitator.closeDictionaries() }
            assertFalse(facilitator.isActive)
            release.countDown()
            assertTrue(finished.await(5, TimeUnit.SECONDS))
            failure.get()?.let { throw it }
            instrumentation.waitForIdleSync()
            assertEquals(1, dictionary.closes.get())
            assertEquals(0L, latch.count)
            main { assertEquals(before, events.size) }
        } finally { release.countDown(); worker.join(5000); main { facilitator.closeDictionaries() } }
    }

    @Test fun completedLoadCannotNotifyAfterOwnerQueueInvalidation() {
        val facilitator = ControlledFacilitator()
        val events = ArrayList<Boolean>()
        try {
            main {
                reset(facilitator, Locale.US, {
                    assertEquals(Looper.getMainLooper(), Looper.myLooper())
                    events.add(it)
                })
                // Worker finishes while main cannot deliver the queued availability result.
                runTask(facilitator.queued.single())
                facilitator.closeDictionaries()
            }
            instrumentation.waitForIdleSync()
            main { assertFalse("Retired dictionary notified availability", events.contains(true)) }
        } finally { main { facilitator.closeDictionaries() } }
    }

    @Test fun loaderFailureCompletesLatchAndAllowsNextLoad() {
        val facilitator = ControlledFacilitator()
        facilitator.factory = { throw IllegalStateException("synthetic factory failure") }
        val latch = main { reset(facilitator, Locale.US); loadLatch(facilitator) }
        try {
            // Propagation policy is independent from releasing waiters and allowing recovery.
            try { runTask(facilitator.queued[0]) } catch (_: IllegalStateException) { }
            assertEquals(0L, latch.count)
            facilitator.factory = { FakeDictionary(it) }
            main { reset(facilitator, Locale.US, force = true) }
            runTask(facilitator.queued[1])
            assertTrue(facilitator.hasAtLeastOneInitializedMainDictionary())
        } finally { main { facilitator.closeDictionaries() } }
    }

    @Test fun reusedDictionaryStaysOpenAndLocaleReplacementClosesItOnce() {
        val facilitator = ControlledFacilitator()
        val first = FakeDictionary(Locale.US)
        facilitator.factory = { first }
        try {
            main { reset(facilitator, Locale.US) }
            runTask(facilitator.queued[0])
            main { reset(facilitator, Locale.US) }
            assertEquals(1, facilitator.queued.size)
            assertEquals(0, first.closes.get())
            main { reset(facilitator, Locale.FRANCE) }
            assertEquals(1, first.closes.get())
            main { facilitator.closeDictionaries(); facilitator.closeDictionaries() }
            assertEquals(1, first.closes.get())
        } finally { main { facilitator.closeDictionaries() } }
    }

    @Test fun concurrentCloseDoesNotAwaitOrRedisposeDetachedDictionary() {
        val facilitator = ControlledFacilitator()
        val dictionary = FakeDictionary(Locale.US)
        val closing = CountDownLatch(1)
        val release = CountDownLatch(1)
        val failure = AtomicReference<Throwable>()
        facilitator.factory = { dictionary }
        main { reset(facilitator, Locale.US) }
        runTask(facilitator.queued.single())
        dictionary.beforeClose = {
            closing.countDown()
            check(release.await(5, TimeUnit.SECONDS))
        }
        val worker = Thread {
            try { reset(facilitator, Locale.US, force = true) }
            catch (error: Throwable) { failure.set(error) }
        }
        worker.start()
        try {
            assertTrue(closing.await(5, TimeUnit.SECONDS))
            // Disposal is blocked, but ownership has already moved under the short state lock.
            main { facilitator.closeDictionaries(); facilitator.closeDictionaries() }
            assertEquals(1, dictionary.closes.get())
            release.countDown()
            worker.join(5000)
            assertFalse(worker.isAlive)
            failure.get()?.let { throw it }
            assertEquals(0L, loadLatch(facilitator).count)
        } finally { release.countDown(); worker.join(5000); main { facilitator.closeDictionaries() } }
    }

    @Test fun inFlightSameLocaleResetDiscardsOldResultAndKeepsCurrentLoad() {
        val facilitator = ControlledFacilitator()
        val old = FakeDictionary(Locale.US)
        val current = FakeDictionary(Locale.US)
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val failure = AtomicReference<Throwable>()
        facilitator.factory = {
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            old
        }
        main { reset(facilitator, Locale.US) }
        val worker = Thread {
            try { facilitator.queued[0].run() }
            catch (error: Throwable) { failure.set(error) }
        }
        worker.start()
        try {
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            val currentLatch = main {
                reset(facilitator, Locale.US, force = true)
                loadLatch(facilitator)
            }
            release.countDown()
            worker.join(5000)
            assertFalse(worker.isAlive)
            failure.get()?.let { throw it }
            assertEquals(1, old.closes.get())
            assertEquals("Old completion released the current load", 1L, currentLatch.count)
            facilitator.factory = { current }
            runTask(facilitator.queued[1])
            assertEquals(0L, currentLatch.count)
            assertTrue(facilitator.hasAtLeastOneInitializedMainDictionary())
            assertEquals(0, current.closes.get())
        } finally { release.countDown(); worker.join(5000); main { facilitator.closeDictionaries() } }
        assertEquals(1, current.closes.get())
    }

}
