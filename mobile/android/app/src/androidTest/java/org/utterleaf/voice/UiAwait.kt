package org.utterleaf.voice

import android.os.Looper
import android.os.SystemClock
import android.view.ViewConfiguration
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import java.util.concurrent.atomic.AtomicBoolean

/** Conditions run on the UI thread; waiting never blocks that thread. */
internal object UiAwait {
    // Observe cancellation past the initial hold delay and two 80 ms repeat periods.
    val cancellationWindowMs get() = ViewConfiguration.getLongPressTimeout().toLong() + 160

    private fun sample(condition: () -> Boolean): Boolean {
        val result = AtomicBoolean()
        InstrumentationRegistry.getInstrumentation().runOnMainSync { result.set(condition()) }
        return result.get()
    }

    fun until(message: String, timeoutMs: Long = 5000, condition: () -> Boolean) {
        check(Looper.myLooper() != Looper.getMainLooper())
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        do {
            if (sample(condition)) return
            Thread.sleep(10) // Poll spacing only; success depends on the observed state.
        } while (SystemClock.uptimeMillis() < deadline)
        assertTrue(message, sample(condition))
    }

    fun remains(message: String, durationMs: Long = cancellationWindowMs, condition: () -> Boolean) {
        check(Looper.myLooper() != Looper.getMainLooper())
        val deadline = SystemClock.uptimeMillis() + durationMs
        do {
            assertTrue(message, sample(condition))
            Thread.sleep(10)
        } while (SystemClock.uptimeMillis() < deadline)
        assertTrue(message, sample(condition))
    }
}
