package org.utterleaf.keyboard

/**
 * Exclusive, nonwaiting ownership for native operations. Only bookkeeping runs under
 * the monitor. Closing rejects new operations immediately; the last owner disposes
 * the resource outside the monitor. Busy callers must return their unavailable result.
 */
class NativeOperationGate(
    private val dispose: Runnable,
    private val maintenance: Runnable?,
) : AutoCloseable {
    constructor(dispose: Runnable) : this(dispose, null)

    private val monitor = Any()
    private var owner: Thread? = null
    private var depth = 0
    private var open = true
    private var disposalClaimed = false
    private var maintenancePending = false

    fun isOpen(): Boolean = synchronized(monitor) { open }

    fun tryAcquire(): Lease? = synchronized(monitor) {
        val current = Thread.currentThread()
        // A reserved owner at depth zero is draining maintenance, not a native caller.
        if (!open || (owner != null && (owner !== current || depth == 0))) return@synchronized null
        owner = current
        depth++
        Lease(current)
    }

    override fun close() {
        val shouldDispose = synchronized(monitor) {
            open = false
            maintenancePending = false
            claimDisposal()
        }
        if (shouldDispose) dispose.run()
    }

    private fun claimDisposal(): Boolean {
        if (open || owner != null || disposalClaimed) return false
        disposalClaimed = true
        return true
    }

    /** Coalesces one fixed, idempotent cleanup action without waiting for native work. */
    fun requestMaintenance() {
        checkNotNull(maintenance) { "No native maintenance action configured" }
        val shouldDrain = synchronized(monitor) {
            if (!open) return
            maintenancePending = true
            if (owner != null) false else {
                owner = Thread.currentThread()
                true
            }
        }
        if (shouldDrain) drainMaintenance()
    }

    /** Keeps ownership reserved between the last native return and pending cleanup. */
    private fun drainMaintenance() {
        var failure: Throwable? = null
        while (true) {
            var done = false
            val action = synchronized(monitor) {
                check(owner === Thread.currentThread() && depth == 0)
                if (!open) {
                    maintenancePending = false
                    owner = null
                    done = true
                    if (claimDisposal()) dispose else null
                } else if (maintenancePending) {
                    maintenancePending = false
                    maintenance
                } else {
                    owner = null
                    done = true
                    null
                }
            }
            try {
                action?.run()
            } catch (error: Throwable) {
                if (failure == null) failure = error
                else if (failure !== error) failure.addSuppressed(error)
            }
            if (done) {
                failure?.let { throw it }
                return
            }
        }
    }

    inner class Lease internal constructor(private val thread: Thread) : AutoCloseable {
        private var released = false

        override fun close() {
            val shouldDrain = synchronized(monitor) {
                check(Thread.currentThread() === thread) { "Native lease must stay on its owner thread" }
                if (released) return
                released = true
                check(owner === thread && depth > 0)
                depth--
                // Do not expose idle before choosing pending maintenance or disposal.
                depth == 0
            }
            if (shouldDrain) drainMaintenance()
        }
    }
}
