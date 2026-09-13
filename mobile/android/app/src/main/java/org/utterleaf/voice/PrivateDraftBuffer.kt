package org.utterleaf.voice

import java.util.ArrayDeque

/** Immutable UTF-16 draft state. Selection direction is retained. */
data class PrivateDraftSnapshot(
    val text: String,
    val selectionStart: Int,
    val selectionEnd: Int,
)

/**
 * Bounded in-memory editing state for the private draft UI.
 *
 * The buffer has no Android, storage, clipboard, network, or logging dependency.
 * Every rejected operation leaves the snapshot and both history stacks unchanged.
 */
class PrivateDraftBuffer {
    private val lock = Any()
    private var snapshot = EMPTY
    private val undo = ArrayDeque<PrivateDraftSnapshot>()
    private val redo = ArrayDeque<PrivateDraftSnapshot>()
    private var disposed = false

    val current: PrivateDraftSnapshot
        get() = synchronized(lock) { snapshot }

    val canUndo: Boolean
        get() = synchronized(lock) { !disposed && undo.isNotEmpty() }

    val canRedo: Boolean
        get() = synchronized(lock) { !disposed && redo.isNotEmpty() }

    val isDisposed: Boolean
        get() = synchronized(lock) { disposed }

    /** Accepts an owned editor state. Text changes form history; selection-only changes do not. */
    fun acceptExternalEdit(text: String, selectionStart: Int, selectionEnd: Int): Boolean = synchronized(lock) {
        if (disposed || !validSnapshot(text, selectionStart, selectionEnd)) return@synchronized false
        val next = PrivateDraftSnapshot(text, selectionStart, selectionEnd)
        if (text != snapshot.text) recordTextEdit(next) else snapshot = next
        true
    }

    /** Replaces the selected range and collapses the cursor after the inserted text. */
    fun replaceSelection(text: String): Boolean = synchronized(lock) {
        if (disposed || text.length > MAX_UTF16_UNITS || !validUtf16(text)) return@synchronized false
        val low = minOf(snapshot.selectionStart, snapshot.selectionEnd)
        val high = maxOf(snapshot.selectionStart, snapshot.selectionEnd)
        val nextLength = snapshot.text.length - (high - low) + text.length
        if (nextLength > MAX_UTF16_UNITS) return@synchronized false
        val nextText = snapshot.text.substring(0, low) + text + snapshot.text.substring(high)
        val cursor = low + text.length
        val next = PrivateDraftSnapshot(nextText, cursor, cursor)
        if (nextText != snapshot.text) recordTextEdit(next) else snapshot = next
        true
    }

    /** Updates selection direction without creating or branching history. */
    fun setSelection(selectionStart: Int, selectionEnd: Int): Boolean = synchronized(lock) {
        if (disposed || !validSelection(snapshot.text, selectionStart, selectionEnd)) return@synchronized false
        snapshot = PrivateDraftSnapshot(snapshot.text, selectionStart, selectionEnd)
        true
    }

    fun undo(): Boolean = synchronized(lock) {
        if (disposed || undo.isEmpty()) return@synchronized false
        redo.addLast(snapshot)
        snapshot = undo.removeLast()
        true
    }

    fun redo(): Boolean = synchronized(lock) {
        if (disposed || redo.isEmpty()) return@synchronized false
        undo.addLast(snapshot)
        snapshot = redo.removeLast()
        true
    }

    /** Clears the current draft and all history without disposing this buffer. */
    fun clear(): Boolean = synchronized(lock) {
        if (disposed) return@synchronized false
        erase()
        true
    }

    /** Clears all retained text and permanently rejects future mutations. */
    fun dispose() = synchronized(lock) {
        erase()
        disposed = true
    }

    private fun recordTextEdit(next: PrivateDraftSnapshot) {
        undo.addLast(snapshot)
        redo.clear()
        while (undo.size + redo.size > MAX_HISTORY_SNAPSHOTS) undo.removeFirst()
        snapshot = next
    }

    private fun erase() {
        snapshot = EMPTY
        undo.clear()
        redo.clear()
    }

    companion object {
        const val MAX_UTF16_UNITS = 16_000
        const val MAX_HISTORY_SNAPSHOTS = 20
        private val EMPTY = PrivateDraftSnapshot("", 0, 0)

        private fun validSnapshot(text: String, selectionStart: Int, selectionEnd: Int): Boolean =
            text.length <= MAX_UTF16_UNITS && validUtf16(text) && validSelection(text, selectionStart, selectionEnd)

        private fun validSelection(text: String, start: Int, end: Int): Boolean =
            start in 0..text.length && end in 0..text.length &&
                !insideSurrogatePair(text, start) && !insideSurrogatePair(text, end)

        private fun insideSurrogatePair(text: String, offset: Int): Boolean =
            offset > 0 && offset < text.length && text[offset - 1].isHighSurrogate() && text[offset].isLowSurrogate()

        private fun validUtf16(text: String): Boolean {
            var index = 0
            while (index < text.length) {
                val character = text[index]
                when {
                    character.isHighSurrogate() -> {
                        if (index + 1 >= text.length || !text[index + 1].isLowSurrogate()) return false
                        index += 2
                    }
                    character.isLowSurrogate() -> return false
                    else -> index++
                }
            }
            return true
        }
    }
}
