package org.utterleaf.keyboard.next.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View
import androidx.core.view.ViewCompat
import androidx.customview.widget.ExploreByTouchHelper
import androidx.core.view.accessibility.AccessibilityNodeInfoCompat
import android.view.accessibility.AccessibilityEvent
import java.util.Collections
import kotlin.math.abs
import java.util.Locale
import org.utterleaf.keyboard.next.R

/** Canvas keyboard with one immutable geometry shared by drawing, touch, and TalkBack nodes. */
class KeyboardSurface @JvmOverloads constructor(context: Context, onKey: (KeyAction) -> Unit = {}) : View(context) {
    var onKey: (KeyAction) -> Unit = onKey
    private val density = resources.displayMetrics.density
    private val keyPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private val drawRect = RectF()
    private val keyColor = 0xff303a35.toInt()
    private val utilityColor = 0xff25342c.toInt()
    private val textColor = 0xffeff5ed.toInt()
    private val accentColor = 0xffc4e7ac.toInt()
    private var symbols = false
    private var shift = false
    private var enterLabel = "↵"
    private var generation = 0L
    private var snapshot = KeyboardSnapshot(1f, 1f, emptyList())
    private val pointers = LinkedHashMap<Int, Pointer>()
    private val touchSlop = 0.45f
    private val accessibility = KeyboardAccessibility(this)

    private data class Pointer(val action: KeyAction, val x: Float, val y: Float, val generation: Long, var cancelled: Boolean = false)

    init {
        isFocusable = true
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        ViewCompat.setAccessibilityDelegate(this, accessibility)
        setBackgroundColor(0xff181d1b.toInt())
    }

    fun bindState(shift: Boolean, symbols: Boolean, enterLabel: String) {
        if (this.shift == shift && this.symbols == symbols && this.enterLabel == enterLabel) return
        cancelPointers()
        this.shift = shift
        this.symbols = symbols
        this.enterLabel = enterLabel.take(32).ifBlank { "↵" }
        rebuild()
    }

    fun cancelPointers() {
        pointers.clear()
        parent?.requestDisallowInterceptTouchEvent(false)
        invalidate()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) = rebuild(w, h)

    private fun rebuild(width: Int = measuredWidth, height: Int = measuredHeight) {
        cancelPointers()
        generation++
        if (width <= 0 || height <= 0) {
            snapshot = KeyboardSnapshot(width.toFloat(), height.toFloat(), emptyList())
            accessibility.invalidateRoot()
            invalidate()
            return
        }
        snapshot = if (symbols) KeyboardLayout.symbols(width.toFloat(), height.toFloat(), 56f * density, density)
        else KeyboardLayout.standard(width.toFloat(), height.toFloat(), 56f * density, density)
        if (enterLabel != "↵") {
            val index = snapshot.keys.indexOfFirst { it.action.kind == KeyAction.Kind.ENTER }
            if (index >= 0) snapshot = snapshot.copy(keys = Collections.unmodifiableList(snapshot.keys.toMutableList().also { it[index] = it[index].copy(label = enterLabel) }))
        }
        accessibility.invalidateRoot()
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        snapshot.keys.forEach { key ->
            val pressed = pointers.values.any { !it.cancelled && it.action == key.action }
            keyPaint.color = if (pressed) accentColor else if (key.utility) utilityColor else keyColor
            if (key.action.kind == KeyAction.Kind.ENTER) keyPaint.color = accentColor
            drawRect.set(key.bounds.left, key.bounds.top, key.bounds.right, key.bounds.bottom)
            canvas.drawRoundRect(drawRect, 8f * density, 8f * density, keyPaint)
            labelPaint.color = if (pressed || key.action.kind == KeyAction.Kind.ENTER) 0xff193017.toInt() else textColor
            labelPaint.textSize = (if (key.label.length > 4) 14f else 20f) * density
            val label = if (shift && key.action.kind == KeyAction.Kind.TEXT) key.label.uppercase(Locale.ROOT) else key.label
            val baseline = drawRect.centerY() - (labelPaint.ascent() + labelPaint.descent()) / 2f
            canvas.drawText(label, drawRect.centerX(), baseline, labelPaint)
        }
    }

    // The canvas owns per-key touch dispatch; ExploreByTouchHelper exposes each virtual key's ACTION_CLICK.
    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                if (event.actionMasked == MotionEvent.ACTION_DOWN) cancelPointers()
                if (pointers.size >= 2) { cancelPointers(); return true }
                val index = if (event.actionMasked == MotionEvent.ACTION_DOWN) 0 else event.actionIndex
                val x = event.getX(index); val y = event.getY(index)
                val key = KeyboardLayout.resolve(snapshot, x, y)
                if (key == null) { cancelPointers(); return true }
                pointers[event.getPointerId(index)] = Pointer(key.action, x, y, generation)
                parent?.requestDisallowInterceptTouchEvent(true)
                invalidate()
            }
            MotionEvent.ACTION_MOVE -> {
                val pitch = snapshot.keys.firstOrNull()?.bounds?.height ?: 0f
                pointers.forEach { (id, pointer) ->
                    val index = event.findPointerIndex(id)
                    if (index < 0 || pitch <= 0f || !event.getX(index).isFinite() || !event.getY(index).isFinite() || !snapshot.keyboardBounds.contains(event.getX(index), event.getY(index)) ||
                        abs(event.getX(index) - pointer.x) > pitch * touchSlop || abs(event.getY(index) - pointer.y) > pitch * touchSlop) pointer.cancelled = true
                }
                invalidate()
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP -> {
                val index = if (event.actionMasked == MotionEvent.ACTION_UP) 0 else event.actionIndex
                val id = event.getPointerId(index)
                val pointer = pointers.remove(id)
                val pitch = snapshot.keys.firstOrNull()?.bounds?.height ?: 0f
                val x = event.getX(index); val y = event.getY(index)
                val validRelease = pointer != null && pitch > 0f && x.isFinite() && y.isFinite() && snapshot.keyboardBounds.contains(x, y) &&
                    abs(x - pointer.x) <= pitch * touchSlop && abs(y - pointer.y) <= pitch * touchSlop
                if (validRelease && !pointer!!.cancelled && pointer.generation == generation) onKey(pointer.action)
                if (pointers.isEmpty()) parent?.requestDisallowInterceptTouchEvent(false)
                invalidate()
            }
            MotionEvent.ACTION_CANCEL -> cancelPointers()
        }
        return true
    }

    internal fun keyBounds(action: KeyAction): KeyBounds? = snapshot.keys.firstOrNull { it.action == action }?.bounds
    internal fun keyBounds(label: String): KeyBounds? = snapshot.keys.firstOrNull { it.label == label }?.bounds

    private fun semanticLabel(key: KeyGeometry): String = when (key.action.kind) {
        KeyAction.Kind.SHIFT -> context.getString(R.string.next_key_shift)
        KeyAction.Kind.BACKSPACE -> context.getString(R.string.next_key_backspace)
        KeyAction.Kind.SPACE -> context.getString(R.string.next_key_space)
        KeyAction.Kind.ENTER -> if (enterLabel == "↵" || enterLabel.isBlank()) context.getString(R.string.next_key_enter) else enterLabel
        KeyAction.Kind.SYMBOLS -> if (symbols) context.getString(R.string.next_key_letters) else context.getString(R.string.next_key_symbols)
        KeyAction.Kind.TEXT -> if (shift) key.label.uppercase(Locale.ROOT) else key.label
        else -> key.label
    }

    override fun dispatchHoverEvent(event: MotionEvent): Boolean = accessibility.dispatchHoverEvent(event) || super.dispatchHoverEvent(event)
    override fun dispatchKeyEvent(event: android.view.KeyEvent): Boolean = accessibility.dispatchKeyEvent(event) || super.dispatchKeyEvent(event)
    override fun onFocusChanged(focused: Boolean, direction: Int, previouslyFocusedRect: Rect?) {
        super.onFocusChanged(focused, direction, previouslyFocusedRect)
        accessibility.onFocusChanged(focused, direction, previouslyFocusedRect)
    }
    override fun onVisibilityChanged(changedView: View, visibility: Int) {
        super.onVisibilityChanged(changedView, visibility)
        if (visibility != VISIBLE) cancelPointers()
    }
    override fun onDetachedFromWindow() { cancelPointers(); super.onDetachedFromWindow() }

    private inner class KeyboardAccessibility(private val host: KeyboardSurface) : ExploreByTouchHelper(host) {
        override fun getVirtualViewAt(x: Float, y: Float): Int {
            val key = snapshot.keys.firstOrNull { it.bounds.contains(x, y) } ?: return INVALID_ID
            return snapshot.keys.indexOf(key) + 1
        }

        override fun getVisibleVirtualViews(virtualViewIds: MutableList<Int>) {
            snapshot.keys.indices.forEach { virtualViewIds += it + 1 }
        }

        override fun onPopulateNodeForVirtualView(virtualViewId: Int, node: AccessibilityNodeInfoCompat) {
            val key = snapshot.keys.getOrNull(virtualViewId - 1) ?: return
            node.text = if (shift && key.action.kind == KeyAction.Kind.TEXT) key.label.uppercase(Locale.ROOT) else key.label
            node.contentDescription = semanticLabel(key)
            node.className = "android.widget.Button"
            node.isClickable = true
            node.isCheckable = key.action.kind == KeyAction.Kind.SHIFT
            node.isChecked = key.action.kind == KeyAction.Kind.SHIFT && shift
            node.addAction(AccessibilityNodeInfoCompat.ACTION_CLICK)
            node.setBoundsInParent(Rect(
                key.bounds.left.toInt(), key.bounds.top.toInt(), key.bounds.right.toInt(), key.bounds.bottom.toInt()
            ))
        }

        override fun onPopulateEventForVirtualView(virtualViewId: Int, event: AccessibilityEvent) {
            snapshot.keys.getOrNull(virtualViewId - 1)?.let { event.contentDescription = semanticLabel(it) }
        }

        override fun onPerformActionForVirtualView(virtualViewId: Int, action: Int, arguments: android.os.Bundle?): Boolean {
            if (action != AccessibilityNodeInfoCompat.ACTION_CLICK) return false
            val key = snapshot.keys.getOrNull(virtualViewId - 1) ?: return false
            onKey(key.action)
            sendEventForVirtualView(virtualViewId, AccessibilityEvent.TYPE_VIEW_CLICKED)
            return true
        }
    }
}
