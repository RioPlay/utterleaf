package org.utterleaf.keyboard

/** Request identity for results that must never outlive their editor or input view. */
class EditorSession {
    private var token: Any? = null

    @Synchronized fun start() { token = Any() }
    @Synchronized fun finish() { token = null }
    @Synchronized fun renewIfActive() { if (token != null) token = Any() }
    @Synchronized fun capture(): Any? = token
    @Synchronized fun isCurrent(request: Any?): Boolean = request != null && request === token

    /**
     * Publish a short callback atomically with lifecycle invalidation. The callback must not
     * perform decoding, wait for the UI thread, or block: existing suggestion callbacks only
     * fill a result holder or enqueue UI work. UI work checks the identity again on delivery.
     */
    @Synchronized fun publish(request: Any?, callback: Runnable) {
        if (isCurrent(request)) callback.run()
    }
}
