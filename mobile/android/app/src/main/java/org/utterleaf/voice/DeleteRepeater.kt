package org.utterleaf.voice

import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.widget.Button

/** Adds conservative held-delete repeat while retaining a normal Button click. */
internal class DeleteRepeater {
    private val states = mutableMapOf<Button, State>()

    fun attach(button: Button, enabled: Boolean, selection: BackspaceSelection? = null,
               selectionUnavailable: () -> Unit = {}, erase: () -> Unit) {
        states.remove(button)?.cancel()
        if (!enabled && selection == null) {
            button.setOnTouchListener(null)
            return
        }
        val state = State(button, erase, enabled, selection, selectionUnavailable)
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

    private class State(private val button: Button, private val erase: () -> Unit, private val repeatEnabled: Boolean,
                        private val selection: BackspaceSelection?, private val selectionUnavailable: () -> Unit) {
        private var cancelled = false
        private var held = false
        private var pointer = -1
        private var startX = 0f
        private var startY = 0f
        private var cursorX = 0f
        private var selecting = false
        private var selectedUnits = 0
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
                    startX = event.x; startY = event.y; cursorX = startX; selecting = false; selectedUnits = 0
                    view.isPressed = true; if (repeatEnabled) view.postDelayed(hold, timeout); return true
                }
                MotionEvent.ACTION_MOVE -> {
                    if (event.pointerCount != 1 || !event.x.isFinite() || !event.y.isFinite()) { stopGesture(); return true }
                    if (selecting) return moveSelection(view, event)
                    if (!cancelled && pointer >= 0 && event.findPointerIndex(pointer) >= 0) {
                        val index = event.findPointerIndex(pointer)
                        val x = event.getX(index); val y = event.getY(index)
                        if (held) {
                            if (x < 0f || x >= view.width || y < 0f || y >= view.height) stopGesture()
                            return true
                        }
                        val touchSlop = ViewConfiguration.get(view.context).scaledTouchSlop
                        if (kotlin.math.abs(y - startY) > touchSlop &&
                            kotlin.math.abs(y - startY) >= kotlin.math.abs(x - startX)) stopGesture()
                        else if (x - startX < -touchSlop && selection != null) {
                            if (selection.begin()) {
                                selecting = true; cursorX = startX
                                view.removeCallbacks(hold); view.removeCallbacks(repeat)
                                return moveSelection(view, event)
                            }
                            stopGesture()
                        } else if (x < 0f || x >= view.width || y < 0f || y >= view.height) stopGesture()
                    }
                    return true
                }
                MotionEvent.ACTION_POINTER_DOWN -> { stopGesture(); return true }
                MotionEvent.ACTION_UP -> {
                    val inside = event.x >= 0f && event.x < view.width && event.y >= 0f && event.y < view.height
                    view.removeCallbacks(hold); view.removeCallbacks(repeat); view.isPressed = false
                    val wasHeld = held; val wasSelecting = selecting; held = false; pointer = -1
                    if (wasSelecting) {
                        val validBand = kotlin.math.abs(event.y - startY) <= Ui.dp(view.context, 48)
                        if (!cancelled && validBand && selectedUnits > 0) {
                            if (!selection!!.finish()) {
                                selection.cancel()
                                selectionUnavailable()
                            }
                        } else selection?.cancel()
                    } else if (!cancelled && !wasHeld && inside) view.performClick()
                    cancelled = true; selecting = false; selectedUnits = 0
                    return true
                }
                MotionEvent.ACTION_CANCEL -> { stopGesture(); return true }
            }
            return true
        }

        fun stopGesture() {
            if (selecting) selection?.cancel()
            cancelled = true; held = false; pointer = -1
            selecting = false; selectedUnits = 0
            button.removeCallbacks(hold); button.removeCallbacks(repeat); button.isPressed = false
        }

        fun cancel() { valid = false; stopGesture() }

        private fun moveSelection(view: View, event: MotionEvent): Boolean {
            val index = event.findPointerIndex(pointer)
            if (index < 0) { stopGesture(); return true }
            val x = event.getX(index); val y = event.getY(index)
            if (!x.isFinite() || !y.isFinite() || kotlin.math.abs(y - startY) > Ui.dp(view.context, 48)) {
                stopGesture(); return true
            }
            val step = maxOf(ViewConfiguration.get(view.context).scaledTouchSlop, Ui.dp(view.context, 16)).toFloat()
            val requested = ((x - cursorX) / step).toInt().coerceIn(-64, 64)
            if (requested == 0) return true
            val count = if (requested < 0) minOf(-requested, 256 - selectedUnits) else minOf(requested, selectedUnits)
            if (count <= 0) return true
            val left = requested < 0
            repeat(count) {
                if (!selection!!.move(left)) { stopGesture(); return true }
                selectedUnits += if (left) 1 else -1
            }
            cursorX += (if (left) -count else count) * step
            return true
        }
    }
}
