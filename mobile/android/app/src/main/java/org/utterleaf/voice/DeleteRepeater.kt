package org.utterleaf.voice

import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.widget.Button

/** Adds conservative held-delete repeat while retaining a normal Button click. */
internal class DeleteRepeater {
    private val states = mutableMapOf<Button, State>()

    fun attach(button: Button, enabled: Boolean, erase: () -> Unit) {
        states.remove(button)?.cancel()
        if (!enabled) {
            button.setOnTouchListener(null)
            return
        }
        val state = State(button, erase)
        states[button] = state
        button.setOnTouchListener { view, event -> state.touch(view, event) }
        button.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(v: View) = Unit
            override fun onViewDetachedFromWindow(v: View) {
                state.cancel()
                if (states[button] === state) states.remove(button)
            }
        })
    }

    fun cancel() {
        states.values.toList().forEach { it.cancel() }
        states.clear()
    }
    fun stop() { states.values.toList().forEach { it.stopGesture() } }

    private class State(private val button: Button, private val erase: () -> Unit) {
        private var cancelled = false
        private var held = false
        private var pointer = -1
        private var valid = true
        private val timeout = ViewConfiguration.getLongPressTimeout().toLong()
        private val repeat = object : Runnable {
            override fun run() {
                if (!valid || !held || cancelled || !button.isAttachedToWindow || !button.isEnabled) return
                erase()
                if (valid && held && !cancelled && button.isAttachedToWindow && button.isEnabled) button.postDelayed(this, 80L)
            }
        }
        private val hold = Runnable {
            if (valid && !cancelled && pointer >= 0 && button.isAttachedToWindow && button.isEnabled) {
                held = true
                erase()
                if (valid && held && !cancelled && button.isAttachedToWindow && button.isEnabled) button.postDelayed(repeat, 80L)
            }
        }

        fun touch(view: View, event: MotionEvent): Boolean {
            if (!valid) return true
            if (!view.isEnabled || event.pointerCount != 1 || !event.x.isFinite() || !event.y.isFinite() ||
                (event.actionMasked != MotionEvent.ACTION_DOWN && (pointer < 0 || event.getPointerId(0) != pointer))) {
                stopGesture(); return true
            }
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (event.pointerCount != 1 || !event.x.isFinite() || !event.y.isFinite()) { stopGesture(); return true }
                    view.removeCallbacks(hold); view.removeCallbacks(repeat)
                    cancelled = false; held = false; pointer = event.getPointerId(event.actionIndex)
                    view.isPressed = true; view.postDelayed(hold, timeout); return true
                }
                MotionEvent.ACTION_MOVE -> {
                    if (event.pointerCount != 1 || !event.x.isFinite() || !event.y.isFinite()) { stopGesture(); return true }
                    if (!cancelled && pointer >= 0 && event.findPointerIndex(pointer) >= 0) {
                        val index = event.findPointerIndex(pointer)
                        if (event.getX(index) < 0f || event.getX(index) >= view.width ||
                            event.getY(index) < 0f || event.getY(index) >= view.height) stopGesture()
                    }
                    return true
                }
                MotionEvent.ACTION_POINTER_DOWN -> { stopGesture(); return true }
                MotionEvent.ACTION_UP -> {
                    val inside = event.x >= 0f && event.x < view.width && event.y >= 0f && event.y < view.height
                    view.removeCallbacks(hold); view.removeCallbacks(repeat); view.isPressed = false
                    val wasHeld = held; held = false; pointer = -1
                    if (!cancelled && !wasHeld && inside) view.performClick()
                    cancelled = true
                    return true
                }
                MotionEvent.ACTION_CANCEL -> { stopGesture(); return true }
            }
            return true
        }

        fun stopGesture() {
            cancelled = true; held = false; pointer = -1
            button.removeCallbacks(hold); button.removeCallbacks(repeat); button.isPressed = false
        }

        fun cancel() { valid = false; stopGesture() }
    }
}
