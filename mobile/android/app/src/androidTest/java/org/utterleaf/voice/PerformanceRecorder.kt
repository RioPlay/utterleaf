package org.utterleaf.voice

import android.os.SystemClock
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/** Opt-in only: ordinary connected correctness runs exclude this annotation. */
@Target(AnnotationTarget.CLASS, AnnotationTarget.FUNCTION)
@Retention(AnnotationRetention.RUNTIME)
annotation class PerformanceMeasurement

/**
 * Buffers numeric, on-device measurements and emits one bounded JSON object per
 * logcat line after measurement. It never accepts transcript or editor text.
 */
internal class PerformanceRecorder(
    val runId: String = UUID.randomUUID().toString(),
) {
    private data class Sample(
        val metric: String,
        val index: Int,
        val value: Long,
        val unit: String,
        val elapsedNs: Long?,
        val startNs: Long?,
        val endNs: Long?,
        val attributes: Map<String, Any>,
    )

    private val metadata = linkedMapOf<String, Any>()
    private val samples = mutableListOf<Sample>()
    private val counts = linkedMapOf<String, Int>()
    private var flushed = false

    @Synchronized
    fun metadata(name: String, value: Any) {
        check(!flushed) { "Performance evidence was already flushed" }
        metadata[name] = value
    }

    @Synchronized
    fun duration(
        metric: String,
        startElapsedRealtimeNs: Long,
        endElapsedRealtimeNs: Long,
        attributes: Map<String, Any> = emptyMap(),
    ) {
        require(endElapsedRealtimeNs >= startElapsedRealtimeNs) { "$metric ended before it started" }
        add(
            metric = metric,
            value = endElapsedRealtimeNs - startElapsedRealtimeNs,
            unit = "ns",
            elapsedNs = null,
            startNs = startElapsedRealtimeNs,
            endNs = endElapsedRealtimeNs,
            attributes = attributes,
        )
    }

    @Synchronized
    fun value(
        metric: String,
        value: Long,
        unit: String,
        attributes: Map<String, Any> = emptyMap(),
        elapsedRealtimeNs: Long = SystemClock.elapsedRealtimeNanos(),
    ) {
        require(value >= 0) { "$metric must be non-negative" }
        require(unit == "kb" || unit == "count" || unit == "ns") { "Unsupported unit $unit" }
        add(metric, value, unit, elapsedRealtimeNs, null, null, attributes)
    }

    private fun add(
        metric: String,
        value: Long,
        unit: String,
        elapsedNs: Long?,
        startNs: Long?,
        endNs: Long?,
        attributes: Map<String, Any>,
    ) {
        check(!flushed) { "Performance evidence was already flushed" }
        require(metric.matches(Regex("[a-z0-9_]+"))) { "Unsafe metric name" }
        val index = counts.getOrDefault(metric, 0)
        counts[metric] = index + 1
        samples += Sample(metric, index, value, unit, elapsedNs, startNs, endNs, attributes)
    }

    @Synchronized
    fun flush() {
        if (flushed) return
        val values = linkedMapOf<String, Any>().apply {
            putAll(metadata)
            put("recorded_counts", counts.toMap())
        }
        val records = mutableListOf(JSONObject().apply {
            put("schema", SCHEMA)
            put("kind", "metadata")
            put("run_id", runId)
            put("record_id", "$runId:metadata")
            put("clock", CLOCK)
            put("values", json(values))
        })
        samples.forEach { sample ->
            records += JSONObject().apply {
                put("schema", SCHEMA)
                put("kind", "sample")
                put("run_id", runId)
                put("record_id", "$runId:${sample.metric}:${sample.index}")
                put("metric", sample.metric)
                put("index", sample.index)
                put("value", sample.value)
                put("unit", sample.unit)
                sample.elapsedNs?.let { put("elapsed_realtime_ns", it) }
                sample.startNs?.let { put("start_elapsed_realtime_ns", it) }
                sample.endNs?.let { put("end_elapsed_realtime_ns", it) }
                if (sample.attributes.isNotEmpty()) put("attributes", json(sample.attributes))
            }
        }
        val lines = records.map { MARKER + it.toString() }
        lines.forEach { line ->
            require(line.toByteArray(Charsets.UTF_8).size <= MAX_LOG_BYTES) {
                "Performance record exceeds the safe Android log-line bound"
            }
        }
        flushed = true
        lines.forEach(::emit)
    }

    private fun emit(line: String) { Log.i(TAG, line) }

    private fun json(values: Map<String, Any>): JSONObject = JSONObject().apply {
        values.forEach { (key, value) -> put(key, jsonValue(value)) }
    }

    private fun jsonValue(value: Any): Any = when (value) {
        is Map<*, *> -> JSONObject().apply {
            value.forEach { (key, nested) -> if (key != null && nested != null) put(key.toString(), jsonValue(nested)) }
        }
        is Iterable<*> -> JSONArray().apply {
            value.forEach { nested -> put(if (nested == null) JSONObject.NULL else jsonValue(nested)) }
        }
        is Array<*> -> JSONArray().apply {
            value.forEach { nested -> put(if (nested == null) JSONObject.NULL else jsonValue(nested)) }
        }
        else -> value
    }

    companion object {
        const val SCHEMA = "utterleaf.performance.v1"
        const val CLOCK = "android.os.SystemClock.elapsedRealtimeNanos"
        const val MARKER = "UTTERLEAF_PERF_V1 "
        private const val TAG = "UtterleafPerf"
        // Android log payload limits vary; stay below the common 4 KiB boundary.
        private const val MAX_LOG_BYTES = 3_800
    }
}
