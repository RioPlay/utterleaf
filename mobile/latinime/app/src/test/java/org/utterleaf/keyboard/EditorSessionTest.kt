package org.utterleaf.keyboard

import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class EditorSessionTest {
    @Test fun cancellationInvalidatesActiveRequestsWithoutReopeningFinishedSession() {
        val session = EditorSession()
        session.renewIfActive()
        assertNull(session.capture())
        session.start()
        val old = session.capture()
        session.renewIfActive()
        assertFalse(session.isCurrent(old))
        assertTrue(session.isCurrent(session.capture()))
        session.finish()
        session.renewIfActive()
        assertNull(session.capture())
    }

    @Test fun restartAndHideInvalidateOldRequestsAndResumeAcceptsNewOnes() {
        val session = EditorSession()
        assertFalse(session.isCurrent(session.capture()))
        session.start()
        val first = session.capture()
        session.start()
        assertFalse(session.isCurrent(first))
        val restarted = session.capture()
        session.finish()
        assertFalse(session.isCurrent(restarted))
        session.start()
        var delivered = 0
        session.publish(first) { delivered++ }
        session.publish(restarted) { delivered++ }
        session.publish(session.capture()) { delivered++ }
        assertEquals(1, delivered)
    }

    @Test fun workerCanPublishWhileCallerWaitsForSynchronousSuggestionHolder() {
        val session = EditorSession()
        session.start()
        val token = session.capture()
        val delivered = CountDownLatch(1)
        val worker = Thread { session.publish(token) { delivered.countDown() } }
        worker.start()
        assertTrue(delivered.await(2, TimeUnit.SECONDS))
        worker.join(2_000)
        assertFalse(worker.isAlive)
    }
}
