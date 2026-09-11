package org.utterleaf.keyboard

import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

class NativeOperationMaintenanceTest {
    private fun await(latch: CountDownLatch) = assertTrue(latch.await(5, TimeUnit.SECONDS))

    @Test fun pendingResetCoalescesAndRunsBeforeOwnershipBecomesAvailable() {
        val resets = AtomicInteger()
        val disposals = AtomicInteger()
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val done = CountDownLatch(1)
        val failure = AtomicReference<Throwable>()
        lateinit var gate: NativeOperationGate
        gate = NativeOperationGate(Runnable { disposals.incrementAndGet() }, Runnable {
            assertNull("Maintenance must not admit even same-thread native work", gate.tryAcquire())
            resets.incrementAndGet(); entered.countDown(); await(release)
        })
        val admitted = CountDownLatch(1)
        val finish = CountDownLatch(1)
        val worker = Thread {
            try {
                val outer = gate.tryAcquire()!!
                val inner = gate.tryAcquire()!!
                admitted.countDown(); await(finish)
                inner.close(); assertEquals(0, resets.get())
                outer.close()
            } catch (error: Throwable) { failure.set(error) }
            finally { done.countDown() }
        }
        worker.start()
        try {
            await(admitted)
            gate.requestMaintenance(); gate.requestMaintenance()
            assertEquals(0, resets.get())
            finish.countDown(); await(entered)
            assertNull(gate.tryAcquire())
            release.countDown(); await(done)
            failure.get()?.let { throw it }
            assertEquals(1, resets.get())
            gate.tryAcquire()!!.close()
            assertEquals(0, disposals.get())
        } finally { finish.countDown(); release.countDown(); worker.join(5000); gate.close() }
        assertEquals(1, disposals.get())
    }

    @Test fun requestDuringMaintenanceDrainsAgainBeforeIdle() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val done = CountDownLatch(1)
        val count = AtomicInteger()
        val failure = AtomicReference<Throwable>()
        val gate = NativeOperationGate(Runnable {}, Runnable {
            if (count.incrementAndGet() == 1) { entered.countDown(); await(release) }
        })
        val worker = Thread {
            try { gate.requestMaintenance() } catch (error: Throwable) { failure.set(error) }
            finally { done.countDown() }
        }
        worker.start()
        try {
            await(entered)
            gate.requestMaintenance()
            assertNull(gate.tryAcquire())
            release.countDown(); await(done)
            failure.get()?.let { throw it }
            assertEquals(2, count.get())
            gate.tryAcquire()!!.close()
        } finally { release.countDown(); worker.join(5000); gate.close() }
    }

    @Test fun closeDuringIdleRequestedMaintenanceDefersDisposalAndSupersedesPendingReset() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val done = CountDownLatch(1)
        val resets = AtomicInteger()
        val disposals = AtomicInteger()
        val failure = AtomicReference<Throwable>()
        val gate = NativeOperationGate(Runnable { disposals.incrementAndGet() }, Runnable {
            resets.incrementAndGet(); entered.countDown(); await(release)
        })
        val worker = Thread {
            try { gate.requestMaintenance() } catch (error: Throwable) { failure.set(error) }
            finally { done.countDown() }
        }
        worker.start()
        try {
            await(entered)
            gate.requestMaintenance(); gate.close()
            assertFalse(gate.isOpen()); assertNull(gate.tryAcquire())
            assertEquals(0, disposals.get())
            release.countDown(); await(done)
            failure.get()?.let { throw it }
            assertEquals(1, resets.get()); assertEquals(1, disposals.get())
            gate.requestMaintenance(); gate.close()
            assertEquals(1, resets.get()); assertEquals(1, disposals.get())
        } finally { release.countDown(); worker.join(5000); gate.close() }
    }

    @Test fun throwingMaintenanceReleasesOwnershipAndHonorsReentrantResetAndClose() {
        val calls = AtomicInteger()
        val disposals = AtomicInteger()
        lateinit var gate: NativeOperationGate
        gate = NativeOperationGate(Runnable { disposals.incrementAndGet() }, Runnable {
            when (calls.incrementAndGet()) {
                1 -> { gate.requestMaintenance(); throw IllegalStateException("synthetic reset failure") }
                2 -> { assertNull(gate.tryAcquire()); gate.close() }
            }
        })
        try {
            gate.requestMaintenance()
            fail("Expected maintenance failure")
        } catch (expected: IllegalStateException) {
            assertEquals("synthetic reset failure", expected.message)
        }
        assertEquals(2, calls.get()); assertEquals(1, disposals.get())
        assertNull(gate.tryAcquire()); gate.close(); assertEquals(1, disposals.get())

        val recoverable = NativeOperationGate(Runnable {}, Runnable { throw IllegalArgumentException("reset") })
        try { recoverable.requestMaintenance(); fail("Expected reset failure") }
        catch (_: IllegalArgumentException) {}
        recoverable.tryAcquire()!!.close()
        recoverable.close()
    }
}
