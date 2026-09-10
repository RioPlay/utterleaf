package org.utterleaf.voice

import android.os.SystemClock
import android.view.InputDevice
import android.view.KeyCharacterMap
import android.view.KeyEvent
import android.view.inputmethod.InputConnection

/** Stateless key dispatch. Acceptance is not proof that an editor handled a key. */
object TerminalInput {
    private val SOFT_FLAGS = KeyEvent.FLAG_SOFT_KEYBOARD or KeyEvent.FLAG_KEEP_TOUCH_MODE

    private fun modifiers(ctrl: Boolean, alt: Boolean, shift: Boolean = false): Int =
        KeyEvent.normalizeMetaState((if (ctrl) KeyEvent.META_CTRL_ON else 0) or
            (if (alt) KeyEvent.META_ALT_ON else 0) or (if (shift) KeyEvent.META_SHIFT_ON else 0))

    private fun deliver(connection: InputConnection, event: KeyEvent): Boolean =
        try { connection.sendKeyEvent(event) } catch (_: RuntimeException) { false }

    fun send(connection: InputConnection?, keyCode: Int, ctrl: Boolean = false,
             alt: Boolean = false, shift: Boolean = false): Boolean {
        if (connection == null || keyCode <= KeyEvent.KEYCODE_UNKNOWN || keyCode > KeyEvent.getMaxKeyCode()) return false
        val now = SystemClock.uptimeMillis()
        val meta = modifiers(ctrl, alt, shift)
        val down = deliver(connection, KeyEvent(now, now, KeyEvent.ACTION_DOWN, keyCode, 0, meta,
            KeyCharacterMap.VIRTUAL_KEYBOARD, 0, SOFT_FLAGS, InputDevice.SOURCE_KEYBOARD))
        // Do not short-circuit: release must be attempted even if key-down failed.
        val up = deliver(connection, KeyEvent(now, SystemClock.uptimeMillis(), KeyEvent.ACTION_UP,
            keyCode, 0, meta, KeyCharacterMap.VIRTUAL_KEYBOARD, 0, SOFT_FLAGS, InputDevice.SOURCE_KEYBOARD))
        return down && up
    }

    /** TextView selection tracks a pressed Shift key in its editable meta state. */
    fun select(connection: InputConnection?, keyCode: Int): Boolean {
        if (connection == null || keyCode !in listOf(KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT,
                KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_MOVE_HOME, KeyEvent.KEYCODE_MOVE_END)) return false
        val now = SystemClock.uptimeMillis()
        fun shift(action: Int) = deliver(connection, KeyEvent(now, SystemClock.uptimeMillis(), action,
            KeyEvent.KEYCODE_SHIFT_LEFT, 0, if (action == KeyEvent.ACTION_DOWN) KeyEvent.META_SHIFT_ON else 0,
            KeyCharacterMap.VIRTUAL_KEYBOARD, 0, SOFT_FLAGS, InputDevice.SOURCE_KEYBOARD))
        val pressed = shift(KeyEvent.ACTION_DOWN)
        val moved = if (pressed) send(connection, keyCode, shift = true) else false
        val released = shift(KeyEvent.ACTION_UP)
        return pressed && moved && released
    }

    fun printable(connection: InputConnection?, text: String, ctrl: Boolean = false,
                  alt: Boolean = false, forceKeyEvents: Boolean = false): Boolean {
        if (connection == null || text.isEmpty()) return false
        if (!ctrl && !alt && !forceKeyEvents) return try { connection.commitText(text, 1) } catch (_: RuntimeException) { false }
        // Modified multi-character/Unicode input must never silently lose modifiers.
        if (text.length != 1 || text[0] !in ' '..'~') return false
        val events = try { KeyCharacterMap.load(KeyCharacterMap.VIRTUAL_KEYBOARD).getEvents(text.toCharArray()) }
                     catch (_: RuntimeException) { return false }
        if (events == null || events.isEmpty()) return false
        // Validate the entire sequence before dispatching any part of it.
        val held = mutableSetOf<Int>()
        for (event in events) {
            if (event.keyCode == KeyEvent.KEYCODE_UNKNOWN) return false
            when (event.action) {
                KeyEvent.ACTION_DOWN -> if (!held.add(event.keyCode)) return false
                KeyEvent.ACTION_UP -> if (!held.remove(event.keyCode)) return false
                else -> return false
            }
        }
        if (held.isNotEmpty()) return false
        val extraMeta = modifiers(ctrl, alt)
        var accepted = true
        for (event in events) {
            val copy = KeyEvent(event.downTime, event.eventTime, event.action, event.keyCode,
                event.repeatCount, KeyEvent.normalizeMetaState(event.metaState or extraMeta),
                KeyCharacterMap.VIRTUAL_KEYBOARD, event.scanCode, event.flags or SOFT_FLAGS,
                InputDevice.SOURCE_KEYBOARD)
            if (!deliver(connection, copy)) accepted = false
        }
        return accepted
    }
}
