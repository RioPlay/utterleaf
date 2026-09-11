package org.utterleaf.keyboard.next.core

import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import java.util.Collections

/** A copied, bounded request. Production N1 does not wire a decoder or candidate UI. */
data class SuggestionRequest(
    val token: EditorToken,
    val sequence: Long,
    val context: String,
)

fun interface TaskQueue { fun post(task: () -> Unit) }
fun interface SuggestionDecoder { fun decode(request: SuggestionRequest): List<String> }

/** One in-flight decode, one latest pending request and one pending UI result. */
class SuggestionDispatcher(
    private val gateway: EditorGateway,
    private val worker: TaskQueue,
    private val main: TaskQueue,
    private val decoder: SuggestionDecoder,
    private val onPublished: (SuggestionRequest, List<String>) -> Unit,
) {
    private data class UiResult(val request: SuggestionRequest, val candidates: List<String>)

    private val nextSequence = AtomicLong(0L)
    private val latestSequence = AtomicLong(0L)
    private val pending = AtomicReference<SuggestionRequest?>(null)
    private val inFlight = AtomicReference<SuggestionRequest?>(null)
    private val pendingUi = AtomicReference<UiResult?>(null)
    private val workerScheduled = AtomicBoolean(false)
    private val mainScheduled = AtomicBoolean(false)

    fun submit(token: EditorToken, suppliedContext: String): Outcome {
        if (!gateway.accepts(token, requireSuggestionPolicy = true)) return Outcome.REFUSED
        val context = copyBounded(suppliedContext, MAX_CONTEXT_CODE_POINTS) ?: return Outcome.REFUSED
        val request = SuggestionRequest(token, nextSequence.incrementAndGet(), context)
        latestSequence.set(request.sequence)
        pending.set(request)
        scheduleWorker()
        return Outcome.APPLIED
    }

    /** Drops queued references and rejects in-flight output. A racing result may
     * remain bounded until main drains; this is not an immediate zeroization promise. */
    fun cancel() {
        latestSequence.incrementAndGet()
        pending.set(null)
        inFlight.set(null)
        pendingUi.set(null)
    }

    private fun scheduleWorker() {
        if (workerScheduled.compareAndSet(false, true)) worker.post(::runWorker)
    }

    private fun runWorker() {
        val request = pending.getAndSet(null)
        if (request != null) {
            inFlight.set(request)
            if (isLatest(request) && gateway.workerPermits(request.token)) {
                val candidates = try { sanitize(decoder.decode(request)) } catch (_: RuntimeException) { emptyList() }
                if (isLatest(request) && gateway.workerPermits(request.token)) {
                    pendingUi.set(UiResult(request, candidates))
                    scheduleMain()
                }
            }
            inFlight.compareAndSet(request, null)
        }
        workerScheduled.set(false)
        if (pending.get() != null) scheduleWorker()
    }

    private fun scheduleMain() {
        if (mainScheduled.compareAndSet(false, true)) main.post(::deliverOnMain)
    }

    private fun deliverOnMain() {
        val result = pendingUi.getAndSet(null)
        mainScheduled.set(false)
        if (result != null && isLatest(result.request) && gateway.accepts(result.request.token, requireSuggestionPolicy = true)) {
            onPublished(result.request, result.candidates)
        }
        if (pendingUi.get() != null) scheduleMain()
    }

    private fun isLatest(request: SuggestionRequest): Boolean = latestSequence.get() == request.sequence

    private fun sanitize(values: List<String>): List<String> {
        val bounded = ArrayList<String>(MAX_CANDIDATES)
        var index = 0
        while (index < values.size && index < MAX_CANDIDATES) {
            copyBounded(values[index], MAX_CANDIDATE_CODE_POINTS)?.let(bounded::add)
            index++
        }
        return Collections.unmodifiableList(bounded)
    }

    /** Copies at most limit code points plus one; malformed and over-limit values reject. */
    private fun copyBounded(value: String, limit: Int): String? {
        var index = 0
        var count = 0
        while (index < value.length && count < limit) {
            val first = value[index]
            val width = when {
                first.isHighSurrogate() && index + 1 < value.length && value[index + 1].isLowSurrogate() -> 2
                first.isHighSurrogate() || first.isLowSurrogate() -> return null
                else -> 1
            }
            index += width
            count++
        }
        if (index < value.length) return null
        return String(value.toCharArray())
    }

    private companion object {
        const val MAX_CONTEXT_CODE_POINTS = 256
        const val MAX_CANDIDATES = 3
        const val MAX_CANDIDATE_CODE_POINTS = 64
    }
}
