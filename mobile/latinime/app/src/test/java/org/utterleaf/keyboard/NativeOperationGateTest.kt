package org.utterleaf.keyboard

import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

class NativeOperationGateTest {
    @Test fun terminalCloseDefersDisposalUntilOutermostLeaseAndNeverReopens() {
        val disposals = AtomicInteger()
        val gate = NativeOperationGate { disposals.incrementAndGet() }
        val outer = gate.tryAcquire()!!
        val nested = gate.tryAcquire()!!
        gate.close()
        assertFalse(gate.isOpen())
        assertNull(gate.tryAcquire())
        assertEquals(0, disposals.get())
        nested.close()
        assertEquals(0, disposals.get())
        outer.close()
        assertEquals(1, disposals.get())
        gate.close()
        assertNull(gate.tryAcquire())
        assertEquals(1, disposals.get())
    }

    @Test fun competingOperationsFailPromptlyAndCloseDoesNotWaitForOwner() {
        val disposed = CountDownLatch(1)
        val gate = NativeOperationGate { disposed.countDown() }
        val lease = gate.tryAcquire()!!
        val returned = CountDownLatch(1)
        val failure = AtomicReference<Throwable>()
        val competitor = Thread {
            try {
                assertNull(gate.tryAcquire())
                gate.close()
                assertFalse(gate.isOpen())
            } catch (error: Throwable) { failure.set(error) }
            finally { returned.countDown() }
        }
        competitor.start()
        try {
            assertTrue("Close waited for the active operation", returned.await(2, TimeUnit.SECONDS))
            failure.get()?.let { throw it }
            assertEquals(1L, disposed.count)
        } finally { lease.close(); competitor.join(2000) }
        assertEquals(0L, disposed.count)
    }

    @Test fun disposalRunsOutsideMonitorAndLeaseFinallyReleasesOnFailure() {
        lateinit var gate: NativeOperationGate
        val disposals = AtomicInteger()
        gate = NativeOperationGate {
            val observed = CountDownLatch(1)
            val observer = Thread { gate.isOpen(); observed.countDown() }
            observer.start()
            assertTrue("Destructor held the gate monitor", observed.await(2, TimeUnit.SECONDS))
            observer.join(2000)
            disposals.incrementAndGet()
        }
        try {
            gate.tryAcquire()!!.use {
                gate.close()
                throw IllegalArgumentException("synthetic operation failure")
            }
        } catch (_: IllegalArgumentException) { }
        assertEquals(1, disposals.get())
        assertNull(gate.tryAcquire())
    }
}
