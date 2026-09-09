package org.utterleaf.voice

/** Main-thread generation gate: delayed callbacks must never deliver to a new field. */
class TakeGate {
    private var generation = 0L
    fun next(): Long = ++generation
    fun accepts(token: Long) = token == generation
    fun invalidate() { generation++ }
}
