package org.utterleaf.voice

import android.content.Context
import android.graphics.Rect
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.widget.FrameLayout
import kotlin.math.abs

/** Recognizes conservative chords and two ordinary typing keys without splitting child events. */
class KeyboardSurface(context: Context) : FrameLayout(context) {
    internal val modifiers = ModifierChords(this)
    private var shiftKey: View? = null
    private var spaceKey: View? = null
    private var select: ((Boolean) -> Unit)? = null
    private var shiftPointer = -1
    private var spacePointer = -1
    private var consumed = false
    private var stopped = false
    private var cursorX = 0f
    private var startY = 0f
    private val step = maxOf(ViewConfiguration.get(context).scaledTouchSlop, Ui.dp(context, 16)).toFloat()
    private val ordinaryKeys = mutableListOf<View>()
    private var rolloverEligible: (View) -> Boolean = { true }
    private var candidate: Candidate? = null
    private var rollover: Rollover? = null
    init { isMotionEventSplittingEnabled = false }

    internal fun bindSelection(shift: View?, space: View, action: (Boolean) -> Unit) {
        shiftKey = shift; spaceKey = space; select = action
    }
    /** Register only literal text keys. Modifiers, space and utility buttons keep their own routing. */
    internal fun registerOrdinaryKey(key: View) { ordinaryKeys.add(key) }
    internal fun clearOrdinaryKeys() { ordinaryKeys.clear() }
    internal fun bindRolloverEligibility(eligible: (View) -> Boolean) { rolloverEligible = eligible }
    /** Layout/session changes must never release a previously captured ordinary tap. */
    internal fun cancelRollover() {
        candidate = null
        rollover?.let { active -> active.cancelled = true; active.queue.forEach { it.key.isPressed = false } }
    }
    internal fun cancelSelection() {
        modifiers.reset()
        shiftPointer = -1; spacePointer = -1; stopped = true
        shiftKey = null; spaceKey = null; select = null
        parent?.requestDisallowInterceptTouchEvent(false)
    }
    private fun inside(key: View?, x: Float, y: Float): Boolean {
        if (key == null || !key.isEnabled || !key.isAttachedToWindow) return false
        val rect = Rect(0, 0, key.width, key.height)
        offsetDescendantRectToMyCoords(key, rect)
        return x.isFinite() && y.isFinite() && rect.contains(x.toInt(), y.toInt())
    }
    private fun bounds(key: View): Rect? {
        if (!key.isAttachedToWindow || !key.isEnabled || key.width <= 0 || key.height <= 0) return null
        return Rect(0, 0, key.width, key.height).also { offsetDescendantRectToMyCoords(key, it) }
    }
    private fun ordinaryAt(x: Float, y: Float): Candidate? {
        val key = ordinaryKeys.firstOrNull { inside(it, x, y) } ?: return null
        return bounds(key)?.let { Candidate(key, -1, it) }
    }
    private fun cancelChildren(event: MotionEvent) {
        val cancel = MotionEvent.obtain(event).apply { action = MotionEvent.ACTION_CANCEL }
        try { super.dispatchTouchEvent(cancel) } finally { cancel.recycle() }
    }
    private data class Candidate(val key: View, val pointer: Int, val bounds: Rect, var cancelled: Boolean = false)
    private class Press(val key: View, val pointer: Int, val bounds: Rect, var cancelled: Boolean = false)
    private class Rollover(first: Press, second: Press) {
        val queue = mutableListOf(first, second)
        val active = linkedMapOf(first.pointer to first, second.pointer to second)
        var cancelled = false
    }
    private fun valid(press: Press) = bounds(press.key) == press.bounds
    private fun drain(active: Rollover) {
        while (active.queue.isNotEmpty() && !active.active.containsValue(active.queue.first())) {
            val press = active.queue.removeAt(0)
            press.key.isPressed = false
            if (!active.cancelled && !press.cancelled && valid(press) && press.key.isAttachedToWindow && press.key.isEnabled) press.key.performClick()
        }
    }

    private fun dispatchRollover(event: MotionEvent): Boolean {
        val active = rollover ?: return false
        val action = event.actionMasked
        if (action == MotionEvent.ACTION_CANCEL) active.cancelled = true
        active.active.values.toList().forEach { press ->
            val index = event.findPointerIndex(press.pointer)
            if (index >= 0 && (!event.getX(index).isFinite() || !event.getY(index).isFinite() ||
                    !press.bounds.contains(event.getX(index).toInt(), event.getY(index).toInt()) || !valid(press))) {
                press.cancelled = true; press.key.isPressed = false
            }
        }
        if (action == MotionEvent.ACTION_POINTER_DOWN) {
            val id = event.getPointerId(event.actionIndex)
            val next = ordinaryAt(event.getX(event.actionIndex), event.getY(event.actionIndex))
            if (active.active.size >= 2 || active.active.containsKey(id) || active.queue.size >= 32 || next == null || !rolloverEligible(next.key)) active.cancelled = true
            else {
                val press = Press(next.key, id, next.bounds)
                press.key.isPressed = true; active.active[id] = press; active.queue.add(press)
            }
        }
        if (action == MotionEvent.ACTION_POINTER_UP || action == MotionEvent.ACTION_UP) {
            active.active.remove(event.getPointerId(event.actionIndex))?.key?.isPressed = false
            drain(active)
        }
        if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
            active.queue.forEach { it.key.isPressed = false }
            rollover = null
        }
        return true
    }
    override fun dispatchTouchEvent(event: MotionEvent): Boolean {
        if (rollover != null) {
            if (event.actionMasked != MotionEvent.ACTION_DOWN) return dispatchRollover(event)
            rollover = null // A cancelled/rebuilt stream must not block the next physical gesture.
        }
        val action = event.actionMasked
        if (action == MotionEvent.ACTION_DOWN) candidate = null
        modifiers.dispatch(event)?.let { return it }
        if (action == MotionEvent.ACTION_DOWN) {
            ordinaryAt(event.x, event.y)?.let { candidate = it.copy(pointer = event.getPointerId(0)) }
        } else {
            candidate?.let { first ->
                val index = event.findPointerIndex(first.pointer)
                if (index < 0 || !first.bounds.contains(event.getX(index).toInt(), event.getY(index).toInt()) ||
                    bounds(first.key) != first.bounds) first.cancelled = true
                if (action == MotionEvent.ACTION_POINTER_DOWN && event.pointerCount == 2 &&
                    event.getPointerId(event.actionIndex) != first.pointer && !first.cancelled && rolloverEligible(first.key)) {
                    val second = ordinaryAt(event.getX(event.actionIndex), event.getY(event.actionIndex))
                    if (second != null && rolloverEligible(second.key)) {
                        candidate = null
                        rollover = Rollover(Press(first.key, first.pointer, first.bounds),
                            Press(second.key, event.getPointerId(event.actionIndex), second.bounds))
                        cancelChildren(event) // Cancels the pending hold before an overlap can open alternates.
                        rollover?.active?.values?.forEach { it.key.isPressed = true }
                        return true // This POINTER_DOWN created the initial pair; later downs extend it.
                    }
                }
                if (action == MotionEvent.ACTION_POINTER_DOWN) candidate = null // Never resurrect a vetoed physical stream.
                if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) candidate = null
            }
        }
        if (action == MotionEvent.ACTION_DOWN) {
            consumed = false; stopped = false; spacePointer = -1
            shiftPointer = if (inside(shiftKey, event.x, event.y)) event.getPointerId(0) else -1
        }
        if (!consumed && shiftPointer >= 0) {
            val index = event.findPointerIndex(shiftPointer)
            if (index < 0 || !inside(shiftKey, event.getX(index), event.getY(index))) shiftPointer = -1
            if (action == MotionEvent.ACTION_POINTER_DOWN && event.pointerCount == 2 && shiftPointer >= 0 &&
                inside(spaceKey, event.getX(event.actionIndex), event.getY(event.actionIndex))) {
                spacePointer = event.getPointerId(event.actionIndex)
                cursorX = event.getX(event.actionIndex); startY = event.getY(event.actionIndex)
                consumed = true
                val cancel = MotionEvent.obtain(event).apply { setAction(MotionEvent.ACTION_CANCEL) }
                try { super.dispatchTouchEvent(cancel) } finally { cancel.recycle() }
                parent?.requestDisallowInterceptTouchEvent(true)
            }
        }
        if (!consumed) return super.dispatchTouchEvent(event)
        if (!stopped) {
            val s = event.findPointerIndex(shiftPointer); val p = event.findPointerIndex(spacePointer)
            if (action == MotionEvent.ACTION_CANCEL || action == MotionEvent.ACTION_POINTER_UP ||
                action == MotionEvent.ACTION_UP || event.pointerCount != 2 || s < 0 || p < 0 ||
                !inside(shiftKey, event.getX(s), event.getY(s))) stopped = true
            else if (action == MotionEvent.ACTION_MOVE) {
                val x = event.getX(p); val y = event.getY(p)
                if (!x.isFinite() || !y.isFinite() || abs(y - startY) > Ui.dp(context, 48)) stopped = true
                else {
                    val count = ((x - cursorX) / step).coerceIn(-64f, 64f).toInt()
                    repeat(abs(count)) { select?.invoke(count < 0) }
                    cursorX += count * step
                }
            }
        }
        if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
            consumed = false; shiftPointer = -1; spacePointer = -1
            parent?.requestDisallowInterceptTouchEvent(false)
        }
        return true // Neither finger's release becomes a Shift click or a space.
    }
    override fun onDetachedFromWindow() { cancelRollover(); ordinaryKeys.clear(); cancelSelection(); super.onDetachedFromWindow() }
}
