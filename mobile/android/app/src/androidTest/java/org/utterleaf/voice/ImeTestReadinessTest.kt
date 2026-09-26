package org.utterleaf.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class ImeTestReadinessTest {
    @Test fun cleanupAttemptsEveryStepAndKeepsTheFirstFailure() {
        val calls = mutableListOf<Int>()
        val first = IllegalStateException("first cleanup")
        val later = IllegalArgumentException("later cleanup")

        val thrown = runCatching {
            ImeTestReadiness.cleanupPreserving(
                null,
                { calls += 1; throw first },
                { calls += 2 },
                { calls += 3; throw later },
            )
        }.exceptionOrNull()

        assertEquals(listOf(1, 2, 3), calls)
        assertSame(first, thrown)
        assertEquals(listOf(later), first.suppressed.toList())
    }

    @Test fun cleanupPreservesPrimaryFailureAndSuppressesDistinctCleanupFailure() {
        val calls = mutableListOf<Int>()
        val primary = AssertionError("primary test failure")
        val cleanup = IllegalStateException("cleanup failure")

        ImeTestReadiness.cleanupPreserving(
            primary,
            { calls += 1; throw primary },
            { calls += 2; throw cleanup },
            { calls += 3 },
        )

        assertEquals(listOf(1, 2, 3), calls)
        assertEquals(listOf(cleanup), primary.suppressed.toList())
    }
}
