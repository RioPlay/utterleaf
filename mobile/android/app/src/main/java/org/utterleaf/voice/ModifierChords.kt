package org.utterleaf.voice

import android.graphics.Rect
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.widget.Button

/** Ctrl/Alt are physically held locally; each emitted key carries its own modifiers. */
internal class ModifierChords(private val root: KeyboardSurface) {
    private val keys = mutableListOf<Button>()
    private var control: Button? = null
    private var alternate: Button? = null
    private var changed: (Boolean, Boolean) -> Unit = { _, _ -> }
    private val fingers = mutableMapOf<Int, Button>()
    private var active = false
    private var cancelled = false
    private var used = false
    private var repeatKey: Button? = null
    private var repeatTask: Runnable? = null
    var repeatEnabled = true

    fun key(button: Button) { keys.add(button) }
    fun bind(ctrl: Button?, alt: Button?, update: (Boolean, Boolean) -> Unit) {
        control = ctrl; alternate = alt; changed = update
    }
    private fun inside(key: View, x: Float, y: Float): Boolean {
        if (!key.isAttachedToWindow || !key.isEnabled || !x.isFinite() || !y.isFinite()) return false
        val rect = Rect(0, 0, key.width, key.height)
        root.offsetDescendantRectToMyCoords(key, rect)
        return rect.contains(x.toInt(), y.toInt())
    }
    private fun modifier(key: Button) = key === control || key === alternate
    private fun update() = changed(fingers.values.any { it === control }, fingers.values.any { it === alternate })
    private fun stopRepeat() {
        repeatTask?.let { root.removeCallbacks(it) }; repeatTask = null
        repeatKey?.isPressed = false; repeatKey = null
    }
    private fun abort() {
        cancelled = true; stopRepeat(); fingers.clear(); changed(false, false)
    }
    fun reset() {
        abort(); keys.clear(); control = null; alternate = null; changed = { _, _ -> }
        // Consume the remainder of an interrupted chord until a fresh DOWN.
    }
    private fun fire(key: Button) {
        key.performClick()
        if (!active || cancelled || !key.isAttachedToWindow) return
        if (!repeatEnabled || key.contentDescription !in listOf("Delete", "Forward delete", "Delete to right")) return
        repeatKey = key
        val task = object : Runnable {
            override fun run() {
                if (!active || cancelled || repeatKey !== key || !key.isAttachedToWindow || !key.isEnabled) return
                key.performClick()
                if (active && !cancelled && repeatKey === key) root.postDelayed(this, 80)
            }
        }
        repeatTask = task; root.postDelayed(task, ViewConfiguration.getLongPressTimeout().toLong())
    }
    /** Null lets normal typing and the existing Shift-space gesture handle the event. */
    fun dispatch(event: MotionEvent): Boolean? {
        val action = event.actionMasked
        if (action == MotionEvent.ACTION_DOWN) {
            abort(); active = false
            val key = listOfNotNull(control, alternate).firstOrNull { inside(it, event.x, event.y) } ?: return null
            active = true; cancelled = false; used = false
            fingers[event.getPointerId(0)] = key; update()
            root.parent?.requestDisallowInterceptTouchEvent(true)
            return true
        }
        if (!active) return null
        if (action == MotionEvent.ACTION_CANCEL) abort()
        if (!cancelled) {
            // Moving off either key cancels the chord instead of changing its meaning.
            if (fingers.any { (id, key) ->
                    val i = event.findPointerIndex(id)
                    i < 0 || !inside(key, event.getX(i), event.getY(i)) }) abort()
            if (!cancelled && action == MotionEvent.ACTION_POINTER_DOWN) {
                val i = event.actionIndex
                val key = keys.firstOrNull { inside(it, event.getX(i), event.getY(i)) }
                if (key == null || fingers.values.any { it === key } ||
                    (!modifier(key) && fingers.values.any { !modifier(it) })) abort()
                else {
                    used = true; fingers[event.getPointerId(i)] = key; update()
                    if (!modifier(key)) { key.isPressed = true; fire(key) }
                }
            }
            if (!cancelled && (action == MotionEvent.ACTION_POINTER_UP || action == MotionEvent.ACTION_UP)) {
                val key = fingers.remove(event.getPointerId(event.actionIndex))
                if (key != null && modifier(key) && used) abort()
                else {
                    stopRepeat(); update()
                    if (!used && key != null) key.performClick() // Tap-to-arm remains accessible.
                }
            }
        }
        if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
            abort(); active = false; root.parent?.requestDisallowInterceptTouchEvent(false)
        }
        return true
    }
}
