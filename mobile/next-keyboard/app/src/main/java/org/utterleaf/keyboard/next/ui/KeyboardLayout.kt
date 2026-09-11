package org.utterleaf.keyboard.next.ui

import java.util.Collections
import kotlin.math.hypot

data class KeyAction(val kind: Kind, val value: String = "") {
    enum class Kind { TEXT, SHIFT, SYMBOLS, BACKSPACE, ENTER, SPACE, PUNCTUATION }
}

data class KeyBounds(val left: Float, val top: Float, val right: Float, val bottom: Float) {
    val width get() = right - left
    val height get() = bottom - top
    fun contains(x: Float, y: Float) = x >= left && x < right && y >= top && y < bottom
    fun distanceTo(x: Float, y: Float): Float {
        val dx = when { x < left -> left - x; x > right -> x - right; else -> 0f }
        val dy = when { y < top -> top - y; y > bottom -> y - bottom; else -> 0f }
        return hypot(dx.toDouble(), dy.toDouble()).toFloat()
    }
}

data class KeyGeometry(val action: KeyAction, val label: String, val bounds: KeyBounds, val utility: Boolean = false)

data class KeyboardSnapshot(val width: Float, val height: Float, val keys: List<KeyGeometry>) {
    val keyboardBounds = KeyBounds(0f, 0f, width, keys.maxOfOrNull { it.bounds.bottom } ?: 0f)
}

object KeyboardLayout {
    const val DEFAULT_ROW_HEIGHT = 56f
    const val DEFAULT_GAP = 4f
    const val UTILITY_WIDTH = 48f

    fun standard(width: Float, height: Float, rowHeight: Float = DEFAULT_ROW_HEIGHT, unitScale: Float = 1f): KeyboardSnapshot {
        if (!width.isFinite() || !height.isFinite() || width <= 0f || height <= 0f || !rowHeight.isFinite() || !unitScale.isFinite() || unitScale <= 0f || rowHeight < 48f * unitScale || width < 240f * unitScale || height < 4f * rowHeight + 3f * DEFAULT_GAP * unitScale) return KeyboardSnapshot(width, height, emptyList())
        val gap = DEFAULT_GAP * unitScale
        val utility = UTILITY_WIDTH * unitScale
        val keys = ArrayList<KeyGeometry>()
        var top = 0f
        fun row(labels: List<Pair<String, KeyAction>>, inset: Float = 0f, fixed: Map<Int, Float> = emptyMap(), weights: Map<Int, Float> = emptyMap()) {
            val usable = width - inset * 2f - gap * (labels.size - 1)
            val fixedTotal = fixed.values.fold(0f) { total, value -> total + value }
            val weightTotal = labels.indices.filter { it !in fixed }.fold(0f) { total, index -> total + (weights[index] ?: 1f) }
            if (usable <= fixedTotal || weightTotal <= 0f) return
            val unit = (usable - fixedTotal) / weightTotal
            var left = inset
            labels.forEachIndexed { index, (label, action) ->
                val keyWidth = fixed[index] ?: unit * (weights[index] ?: 1f)
                keys += KeyGeometry(action, label, KeyBounds(left, top, left + keyWidth, top + rowHeight), action.kind != KeyAction.Kind.TEXT)
                left += keyWidth + gap
            }
            top += rowHeight + gap
        }
        row("qwertyuiop".map { it.toString() to KeyAction(KeyAction.Kind.TEXT, it.toString()) })
        row("asdfghjkl".map { it.toString() to KeyAction(KeyAction.Kind.TEXT, it.toString()) }, inset = width * .045f)
        row(listOf("⇧" to KeyAction(KeyAction.Kind.SHIFT)) + "zxcvbnm".map { it.toString() to KeyAction(KeyAction.Kind.TEXT, it.toString()) } + listOf("⌫" to KeyAction(KeyAction.Kind.BACKSPACE)), inset = width * .02f, fixed = mapOf(0 to utility, 8 to utility))
        row(listOf("?123" to KeyAction(KeyAction.Kind.SYMBOLS), "," to KeyAction(KeyAction.Kind.PUNCTUATION, ","), "space" to KeyAction(KeyAction.Kind.SPACE), "." to KeyAction(KeyAction.Kind.PUNCTUATION, "."), "↵" to KeyAction(KeyAction.Kind.ENTER)), fixed = mapOf(0 to utility, 4 to utility), weights = mapOf(2 to 4f))
        val valid = keys.all { it.bounds.width > 0f && it.bounds.height > 0f && it.bounds.right <= width + .01f }
        return KeyboardSnapshot(width, height, Collections.unmodifiableList(ArrayList(if (valid) keys else emptyList())))
    }

    fun symbols(width: Float, height: Float, rowHeight: Float = DEFAULT_ROW_HEIGHT, unitScale: Float = 1f): KeyboardSnapshot {
        val base = standard(width, height, rowHeight, unitScale)
        val values = "1234567890@#$%&*()-!?/\"':;".map { it.toString() }
        var textIndex = 0
        val replaced = base.keys.map { key ->
            if (key.action.kind == KeyAction.Kind.TEXT) {
                val value = values.getOrElse(textIndex++) { "?" }
                key.copy(action = KeyAction(KeyAction.Kind.PUNCTUATION, value), label = value)
            } else if (key.action.kind == KeyAction.Kind.SYMBOLS) key.copy(label = "ABC") else key
        }
        return base.copy(keys = Collections.unmodifiableList(ArrayList(replaced)))
    }

    fun resolve(snapshot: KeyboardSnapshot, x: Float, y: Float): KeyGeometry? {
        if (!x.isFinite() || !y.isFinite() || !snapshot.keyboardBounds.contains(x, y)) return null
        snapshot.keys.firstOrNull { it.bounds.contains(x, y) }?.let { return it }
        val proximity = snapshot.keys.firstOrNull()?.bounds?.height?.times(.45f) ?: return null
        if (snapshot.keys.any { it.utility && it.bounds.distanceTo(x, y) <= proximity }) return null
        val candidates = snapshot.keys.filter { !it.utility && it.bounds.distanceTo(x, y) <= minOf(it.bounds.width, it.bounds.height) * .45f }
        return candidates.minWithOrNull(compareBy<KeyGeometry> { it.bounds.distanceTo(x, y) }.thenBy { snapshot.keys.indexOf(it) })
    }
}
