package org.utterleaf.voice

import android.content.Context
import android.os.SystemClock
import android.provider.Settings
import android.view.inputmethod.InputMethodManager

internal object ImeTestReadiness {
    private const val TIMEOUT_MILLIS = 10_000L
    private const val STABLE_MILLIS = 250L
    private const val POLL_MILLIS = 50L

    /**
     * Waits for a shell-requested IME selection to settle without issuing another
     * selection command. A single matching read is insufficient while Android is
     * still completing asynchronous input-method transition callbacks.
     */
    fun awaitDefaultImeStable(
        context: Context,
        manager: InputMethodManager,
        expected: String,
        phase: String,
    ) {
        val deadline = SystemClock.elapsedRealtime() + TIMEOUT_MILLIS
        var matchingSince: Long? = null
        var observed: String? = null
        while (SystemClock.elapsedRealtime() < deadline) {
            val now = SystemClock.elapsedRealtime()
            observed = Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.DEFAULT_INPUT_METHOD,
            )
            if (observed == expected) {
                val since = matchingSince ?: now.also { matchingSince = it }
                if (now - since >= STABLE_MILLIS) return
            } else {
                matchingSince = null
            }
            SystemClock.sleep(POLL_MILLIS)
        }
        val enabled = manager.enabledInputMethodList.map { it.id }.sorted()
        val stableFor = matchingSince?.let { SystemClock.elapsedRealtime() - it } ?: 0L
        throw AssertionError(
            "$phase did not stabilize: expected=$expected, observed=$observed, " +
                "matchingFor=${stableFor}ms, enabled=$enabled",
        )
    }

    /** Runs every cleanup step and never replaces an in-flight test failure. */
    fun cleanupPreserving(primaryFailure: Throwable?, vararg steps: () -> Unit) {
        var cleanupFailure: Throwable? = null
        steps.forEach { step ->
            try {
                step()
            } catch (error: Throwable) {
                if (primaryFailure != null) {
                    if (error !== primaryFailure) primaryFailure.addSuppressed(error)
                } else if (cleanupFailure == null) {
                    cleanupFailure = error
                } else {
                    if (error !== cleanupFailure) cleanupFailure!!.addSuppressed(error)
                }
            }
        }
        cleanupFailure?.let { throw it }
    }
}
