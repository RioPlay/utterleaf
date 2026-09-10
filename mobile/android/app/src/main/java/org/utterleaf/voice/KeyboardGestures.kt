package org.utterleaf.voice

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.widget.Button
import android.widget.FrameLayout
import kotlin.math.abs

/** Owns one physical gesture; accessible click/long-click actions stay on the buttons. */
internal class KeyboardGestures(private val root: FrameLayout) {
    private val slop = ViewConfiguration.get(root.context).scaledTouchSlop
    private val step = maxOf(slop.toFloat(), Ui.dp(root.context, 16).toFloat())
    private var generation = 0
    private var active: Press? = null

    fun attachSpace(button: Button, move: (left: Boolean) -> Unit) = bind(button, move = move)
    fun attachLetter(button: Button, choices: () -> List<String>, choose: (String) -> Unit) = bind(button, choices, choose)

    private fun bind(button: Button, choices: (() -> List<String>)? = null,
                     choose: ((String) -> Unit)? = null, move: ((Boolean) -> Unit)? = null) {
        val token = generation
        button.setOnTouchListener { _, event ->
            if (token != generation || !button.isEnabled) return@setOnTouchListener true
            if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                end()
                if (event.pointerCount == 1 && event.rawX.isFinite() && event.rawY.isFinite()) {
                    active = Press(button, event.getPointerId(0), event.rawX, event.rawY, choices, move)
                    button.isPressed = true
                    active?.let { if (choices != null) button.postDelayed(it.open, ViewConfiguration.getLongPressTimeout().toLong()) }
                }
            } else {
                val press = active
                if (press == null || press.button !== button) return@setOnTouchListener true
                if (event.actionMasked == MotionEvent.ACTION_CANCEL || event.pointerCount != 1 ||
                    event.actionMasked == MotionEvent.ACTION_POINTER_DOWN || event.getPointerId(0) != press.pointer ||
                    !event.rawX.isFinite() || !event.rawY.isFinite()) {
                    end()
                } else when (event.actionMasked) {
                    MotionEvent.ACTION_MOVE -> press.slide(event.rawX, event.rawY)
                    MotionEvent.ACTION_UP -> {
                        press.slide(event.rawX, event.rawY)
                        val value = press.overlay?.selection(event.rawX, event.rawY)
                        val tap = !press.cancelled && !press.dragging && press.overlay == null
                        end() // Remove callbacks/overlay before any editor mutation or rerender.
                        if (!press.cancelled && value != null) {
                            button.performHapticFeedback(android.view.HapticFeedbackConstants.KEYBOARD_TAP)
                            choose?.invoke(value)
                        }
                        else if (tap) button.performClick()
                    }
                }
            }
            true
        }
    }

    private fun end() {
        val old = active ?: return
        active = null
        old.button.removeCallbacks(old.open)
        old.button.isPressed = false
        old.button.parent?.requestDisallowInterceptTouchEvent(false)
        old.overlay?.let { root.removeView(it) }
    }

    /** Rebuilt/detached panels invalidate even a fresh DOWN on an old button. */
    fun cancel() { end(); generation++ }

    private inner class Press(val button: Button, val pointer: Int, val downX: Float, val downY: Float,
                              val choices: (() -> List<String>)?, val move: ((Boolean) -> Unit)?) {
        var cancelled = false
        var dragging = false
        var cursorX = downX
        var overlay: AlternateStrip? = null
        val open = Runnable {
            if (active === this && !cancelled && root.isAttachedToWindow && root.width > 0 && root.height > 0) {
                val values = choices?.invoke().orEmpty()
                if (values.isNotEmpty()) {
                    button.isPressed = false
                    button.parent?.requestDisallowInterceptTouchEvent(true)
                    overlay = AlternateStrip(root, button, values, downX, downY)
                    // Explicit bounds prevent a wrap-content IME growing on hold.
                    root.addView(overlay, FrameLayout.LayoutParams(root.width, root.height))
                    button.performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS)
                }
            }
        }
        fun slide(x: Float, y: Float) {
            if (cancelled) return
            overlay?.let { it.selection(x, y); return }
            val dx = x - downX; val dy = y - downY
            if (move == null) {
                if (abs(dx) > slop || abs(dy) > slop) {
                    button.removeCallbacks(open)
                    // Finger drift inside a key cancels the hold timer, not the tap.
                    val origin = IntArray(2); button.getLocationOnScreen(origin)
                    if (x < origin[0] - slop || x > origin[0] + button.width + slop ||
                        y < origin[1] - slop || y > origin[1] + button.height + slop) {
                        cancelled = true; button.isPressed = false
                    }
                }
                return
            }
            if ((!dragging && abs(dy) > slop && abs(dy) >= abs(dx)) || abs(dy) > Ui.dp(root.context, 48)) {
                cancelled = true; button.isPressed = false; return
            }
            if (!dragging && abs(dx) > slop && abs(dx) > abs(dy)) {
                dragging = true; button.isPressed = false
                button.parent?.requestDisallowInterceptTouchEvent(true)
            }
            if (dragging) {
                val count = ((x - cursorX) / step).coerceIn(-64f, 64f).toInt()
                repeat(abs(count)) { move.invoke(count < 0) }
                cursorX += count * step
            }
        }
    }
}

/** Drawn inside the secure IME, never a separate popup window. */
internal class AlternateStrip(private val host: FrameLayout, anchor: View,
                              private val values: List<String>, downX: Float, downY: Float) : View(host.context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    val cells: List<RectF>
    private val anchorBounds: RectF
    private val origin = IntArray(2).also { host.getLocationOnScreen(it) }
    private val hostWidth = host.width
    private val hostHeight = host.height
    var selectedIndex: Int
        private set
    init {
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
        val position = IntArray(2); anchor.getLocationOnScreen(position)
        anchorBounds = RectF((position[0] - origin[0]).toFloat(), (position[1] - origin[1]).toFloat(),
            (position[0] - origin[0] + anchor.width).toFloat(), (position[1] - origin[1] + anchor.height).toFloat())
        val margin = Ui.dp(context, 4).toFloat(); val gap = Ui.dp(context, 2).toFloat()
        val cellWidth = minOf(Ui.dp(context, 44).toFloat(), (host.width - margin * 2 - gap * (values.size - 1)) / values.size)
        val cellHeight = minOf(Ui.dp(context, 48).toFloat(), host.height - margin * 2)
        val total = values.size * cellWidth + (values.size - 1) * gap
        val left = (anchorBounds.centerX() - total / 2).coerceIn(margin, maxOf(margin, host.width - margin - total))
        val top = (anchorBounds.top - cellHeight - margin).coerceIn(margin, maxOf(margin, host.height - margin - cellHeight))
        cells = values.indices.map { index ->
            val x = left + index * (cellWidth + gap)
            RectF(x, top, x + cellWidth, top + cellHeight)
        }
        selectedIndex = cells.indices.minBy { abs(cells[it].centerX() - (downX - origin[0])) }
        selection(downX, downY)
    }
    /** The band between the strip and original key allows a horizontal finger slide. */
    fun selection(rawX: Float, rawY: Float): String? {
        val currentOrigin = IntArray(2); host.getLocationOnScreen(currentOrigin)
        val x = rawX - origin[0]; val y = rawY - origin[1]
        val margin = Ui.dp(context, 8)
        selectedIndex = if (!currentOrigin.contentEquals(origin) || host.width != hostWidth || host.height != hostHeight ||
            x < cells.first().left - margin || x > cells.last().right + margin ||
            y < cells.first().top - margin || y > maxOf(cells.first().bottom, anchorBounds.bottom) + margin) -1
        else cells.indices.minBy { abs(cells[it].centerX() - x) }
        invalidate()
        return values.getOrNull(selectedIndex)
    }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        cells.forEachIndexed { index, rect ->
            paint.color = if (index == selectedIndex) Color.rgb(162, 223, 179) else Color.rgb(36, 50, 45)
            canvas.drawRoundRect(rect, Ui.dp(context, 6).toFloat(), Ui.dp(context, 6).toFloat(), paint)
            paint.textSize = 22 * resources.displayMetrics.scaledDensity
            val width = paint.measureText(values[index])
            if (width > rect.width() - Ui.dp(context, 4)) paint.textSize *= (rect.width() - Ui.dp(context, 4)) / width
            paint.color = if (index == selectedIndex) Color.rgb(16, 41, 27) else Color.WHITE
            canvas.drawText(values[index], rect.centerX(), rect.centerY() - (paint.ascent() + paint.descent()) / 2, paint)
        }
    }
}
