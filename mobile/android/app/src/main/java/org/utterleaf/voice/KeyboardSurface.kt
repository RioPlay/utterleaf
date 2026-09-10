package org.utterleaf.voice

import android.content.Context
import android.graphics.Rect
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.widget.FrameLayout
import kotlin.math.abs

/** Recognizes only Shift-first + Space chords; other multitouch remains cancelled. */
class KeyboardSurface(context: Context) : FrameLayout(context) {
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
    init { isMotionEventSplittingEnabled = false }

    internal fun bindSelection(shift: View?, space: View, action: (Boolean) -> Unit) {
        shiftKey = shift; spaceKey = space; select = action
    }
    internal fun cancelSelection() {
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
    override fun dispatchTouchEvent(event: MotionEvent): Boolean {
        val action = event.actionMasked
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
    override fun onDetachedFromWindow() { cancelSelection(); super.onDetachedFromWindow() }
}
