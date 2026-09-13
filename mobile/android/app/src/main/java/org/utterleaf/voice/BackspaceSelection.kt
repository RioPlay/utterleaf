package org.utterleaf.voice

import android.view.KeyEvent
import android.view.inputmethod.InputConnection

/** A deliberately narrow editor contract for Backspace's selection preview. */
interface BackspaceSelection {
    /** Begins only from a current, confirmed collapsed caret. */
    fun begin(): Boolean
    /** Extends or shrinks by one editor-owned navigation unit. */
    fun move(left: Boolean): Boolean
    /** Deletes the editor-confirmed nonempty preview once. */
    fun finish(): Boolean
    /** Restores the captured caret only while this session still owns it. */
    fun cancel()
}

/**
 * Host-editor implementation. It deliberately observes only selection offsets supplied by the
 * editor; it never asks for surrounding or selected text. Shift-arrow leaves grapheme boundaries
 * to the editor. A final delete is refused until the editor has reported a backward selection
 * anchored at the original caret.
 */
internal class HostBackspaceSelection(
    private val current: () -> Boolean,
    private val connection: () -> InputConnection?,
    private val selection: () -> Pair<Int, Int>,
) : BackspaceSelection {
    private var captured: InputConnection? = null
    private var origin = -1
    private var extent = -1
    private var active = false
    private var confirmed = false
    private var invalid = false
    private var desiredUnits = 0
    private var confirmedUnits = 0
    private var pendingLeft: Boolean? = null

    fun update(start: Int, end: Int) {
        if (!active) return
        val input = captured
        if (!current() || input == null || input !== connection() || start < 0 || end < 0) {
            invalid = true; confirmed = false
            return
        }
        // Editor selections preserve anchor/extent order; either endpoint may be the origin.
        val nextExtent = when {
            start == origin && end in 0..origin -> end
            end == origin && start in 0..origin -> start
            start == origin && end == origin -> origin
            else -> { invalid = true; confirmed = false; return }
        }
        val direction = pendingLeft
        if (direction == null) {
            if (nextExtent != extent) invalid = true
        } else if (direction) {
            when {
                nextExtent < extent -> {
                    confirmedUnits++
                    if (nextExtent == 0) desiredUnits = confirmedUnits // Offset zero is a confirmed host boundary.
                }
                nextExtent == extent -> desiredUnits = confirmedUnits // Editor boundary: discard queued overshoot.
                else -> invalid = true
            }
        } else {
            when {
                nextExtent > extent -> confirmedUnits = maxOf(0, confirmedUnits - 1)
                nextExtent == extent -> desiredUnits = confirmedUnits
                else -> invalid = true
            }
        }
        extent = nextExtent
        pendingLeft = null
        if (!invalid) pump()
        confirmed = !invalid && pendingLeft == null && desiredUnits == confirmedUnits && extent < origin
    }

    override fun begin(): Boolean {
        if (active || !current()) return false
        val (start, end) = selection()
        val input = connection() ?: return false
        if (start < 0 || start != end) return false
        captured = input; origin = start; extent = start; active = true; confirmed = false; invalid = false
        desiredUnits = 0; confirmedUnits = 0; pendingLeft = null
        return true
    }

    override fun move(left: Boolean): Boolean {
        val input = captured ?: return false
        if (!active || invalid || !current() || input !== connection()) return false
        desiredUnits = if (left) desiredUnits + 1 else maxOf(0, desiredUnits - 1)
        confirmed = false
        if (!left && pendingLeft == true && desiredUnits <= confirmedUnits) {
            // The outstanding left request has not been confirmed. Restoring the origin is safer
            // than issuing a right request that could cross it in an editor with delayed callbacks.
            cancel()
            return false
        }
        return pump()
    }

    override fun finish(): Boolean {
        val input = captured ?: return false
        if (!active || invalid || !current() || !confirmed || pendingLeft != null ||
            desiredUnits != confirmedUnits || input !== connection()) return false
        val committed = try { input.commitText("", 1) } catch (_: RuntimeException) { false }
        if (committed) reset()
        return committed
    }

    override fun cancel() {
        val input = captured
        if (active && input != null && current() && input === connection() && origin >= 0) {
            try { input.setSelection(origin, origin) } catch (_: RuntimeException) { }
        }
        reset()
    }

    private fun reset() {
        active = false; confirmed = false; invalid = false; captured = null; origin = -1; extent = -1
        desiredUnits = 0; confirmedUnits = 0; pendingLeft = null
    }

    /** Keeps one native navigation request in flight so confirmations cannot be mistaken for later moves. */
    private fun pump(): Boolean {
        if (invalid || pendingLeft != null || desiredUnits == confirmedUnits) return !invalid
        val input = captured ?: return false
        if (!active || !current() || input !== connection()) {
            invalid = true; confirmed = false
            return false
        }
        val left = desiredUnits > confirmedUnits
        if (!left && confirmedUnits == 0) return true
        pendingLeft = left
        // The receiving editor owns all Unicode and composition boundaries.
        val accepted = TerminalInput.select(input,
            if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT)
        if (!accepted) {
            pendingLeft = null; invalid = true; confirmed = false
        }
        return accepted
    }
}
