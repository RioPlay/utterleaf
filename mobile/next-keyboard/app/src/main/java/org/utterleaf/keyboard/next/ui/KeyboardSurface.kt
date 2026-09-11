package org.utterleaf.keyboard.next.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
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
    var onAccentStateChanged: (Boolean) -> Unit = {}
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
    private var numberRow = false
    private var longPressEnabled = true
    private var accentSelection = false
    private var generation = 0L
    private var snapshot = KeyboardSnapshot(1f, 1f, emptyList())
    private val pointers = LinkedHashMap<Int, Pointer>()
    private val touchSlop = 0.45f
    private val accessibility = KeyboardAccessibility(this)
    private var popup: Popup? = null
    private var longPress: Runnable? = null
    private var multiplePointers = false
    private var nextPopupId = 1000

    private data class Pointer(val action: KeyAction, val x: Float, val y: Float, val generation: Long,
        val choosingAccent: Boolean, var cancelled: Boolean = false)
    private data class Popup(var pointerId: Int?, val generation: Long, val choices: List<String>,
        val bounds: List<KeyBounds>, val travel: KeyBounds, val nodeBase: Int, var selected: Int = -1)

    init {
        isFocusable = true
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        ViewCompat.setAccessibilityDelegate(this, accessibility)
        setBackgroundColor(0xff181d1b.toInt())
    }

    fun bindState(shift: Boolean, symbols: Boolean, enterLabel: String, numberRow: Boolean = false, longPressEnabled: Boolean = true) {
        if (this.shift == shift && this.symbols == symbols && this.enterLabel == enterLabel && this.numberRow == numberRow && this.longPressEnabled == longPressEnabled) return
        cancelPointers()
        this.shift = shift
        this.symbols = symbols
        this.enterLabel = enterLabel.take(32).ifBlank { "↵" }
        this.numberRow = numberRow
        this.longPressEnabled = longPressEnabled
        rebuild()
    }

    fun cancelPointers() {
        val hadAccent = popup != null || accentSelection
        longPress?.let(::removeCallbacks); longPress = null
        popup = null
        accentSelection = false
        pointers.clear()
        multiplePointers = false
        parent?.requestDisallowInterceptTouchEvent(false)
        if (hadAccent) { accessibility.invalidateRoot(); onAccentStateChanged(false) }
        invalidate()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) = rebuild(w, h)

    private fun rebuild(width: Int = this.width, height: Int = this.height) {
        cancelPointers()
        generation++
        if (width <= 0 || height <= 0) {
            snapshot = KeyboardSnapshot(width.toFloat(), height.toFloat(), emptyList())
            accessibility.invalidateRoot()
            invalidate()
            return
        }
        snapshot = if (symbols) KeyboardLayout.symbols(width.toFloat(), height.toFloat(), 56f * density, density, numberRow)
        else KeyboardLayout.standard(width.toFloat(), height.toFloat(), 56f * density, density, numberRow)
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
        popup?.let { active ->
            keyPaint.color = 0xff101813.toInt()
            drawRect.set(active.bounds.minOf { it.left }, active.bounds.minOf { it.top },
                active.bounds.maxOf { it.right }, active.bounds.maxOf { it.bottom })
            canvas.drawRoundRect(drawRect, 8f * density, 8f * density, keyPaint)
            active.bounds.forEachIndexed { index, bounds ->
                keyPaint.color = if (index == active.selected) accentColor else utilityColor
                drawRect.set(bounds.left, bounds.top, bounds.right, bounds.bottom)
                canvas.drawRoundRect(drawRect, 8f * density, 8f * density, keyPaint)
                labelPaint.color = if (index == active.selected) 0xff193017.toInt() else textColor
                labelPaint.textSize = (if (index == active.choices.lastIndex) 14f else 20f) * density
                val baseline = drawRect.centerY() - (labelPaint.ascent() + labelPaint.descent()) / 2f
                canvas.drawText(active.choices[index], drawRect.centerX(), baseline, labelPaint)
            }
        }
    }

    // The canvas owns per-key touch dispatch; ExploreByTouchHelper exposes each virtual key's ACTION_CLICK.
    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (popup != null) { routePopupTouch(event); return true }
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                    if (!accentSelection) cancelPointers()
                } else {
                    if (accentSelection) { cancelPointers(); return true }
                    multiplePointers = true
                    longPress?.let(::removeCallbacks); longPress = null
                }
                if (pointers.size >= 2) { cancelPointers(); return true }
                val index = if (event.actionMasked == MotionEvent.ACTION_DOWN) 0 else event.actionIndex
                val x = event.getX(index); val y = event.getY(index)
                val key = KeyboardLayout.resolve(snapshot, x, y)
                if (key == null) { cancelPointers(); return true }
                pointers[event.getPointerId(index)] = Pointer(key.action, x, y, generation, accentSelection)
                if (!accentSelection && !multiplePointers && longPressEnabled) scheduleLongPress(event.getPointerId(index), key)
                parent?.requestDisallowInterceptTouchEvent(true)
                invalidate()
            }
            MotionEvent.ACTION_MOVE -> {
                val pitch = snapshot.keys.firstOrNull()?.bounds?.height ?: 0f
                pointers.forEach { (id, pointer) ->
                    val index = event.findPointerIndex(id)
                    if (index < 0 || pitch <= 0f || !event.getX(index).isFinite() || !event.getY(index).isFinite() || !snapshot.keyboardBounds.contains(event.getX(index), event.getY(index)) ||
                    abs(event.getX(index) - pointer.x) > pitch * touchSlop || abs(event.getY(index) - pointer.y) > pitch * touchSlop) { pointer.cancelled = true; longPress?.let(::removeCallbacks); longPress = null }
                }
                invalidate()
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP -> {
                val index = if (event.actionMasked == MotionEvent.ACTION_UP) 0 else event.actionIndex
                val id = event.getPointerId(index)
                val pointer = pointers.remove(id)
                longPress?.let(::removeCallbacks); longPress = null
                val pitch = snapshot.keys.firstOrNull()?.bounds?.height ?: 0f
                val x = event.getX(index); val y = event.getY(index)
                val validRelease = pointer != null && pitch > 0f && x.isFinite() && y.isFinite() && snapshot.keyboardBounds.contains(x, y) &&
                    abs(x - pointer.x) <= pitch * touchSlop && abs(y - pointer.y) <= pitch * touchSlop
                if (validRelease && !pointer!!.cancelled && pointer.generation == generation) {
                    if (pointer.choosingAccent) {
                        val key = snapshot.keys.firstOrNull { it.action == pointer.action }
                        if (key == null || !showAlternates(key, null)) cancelPointers()
                    } else onKey(pointer.action)
                } else if (pointer?.choosingAccent == true) cancelPointers()
                if (pointers.isEmpty()) parent?.requestDisallowInterceptTouchEvent(false)
                invalidate()
            }
            MotionEvent.ACTION_CANCEL -> cancelPointers()
        }
        return true
    }

    internal fun keyBounds(action: KeyAction): KeyBounds? = snapshot.keys.firstOrNull { it.action == action }?.bounds
    internal fun keyBounds(label: String): KeyBounds? = snapshot.keys.firstOrNull { it.label == label }?.bounds
    internal fun alternateBounds(label: String): KeyBounds? = popup?.let { active ->
        active.choices.indexOfFirst { it == label }.takeIf { it >= 0 }?.let(active.bounds::get)
    }
    internal val hasAlternatePopup: Boolean get() = popup != null
    internal fun alternateVirtualId(label: String): Int? = popup?.let { active ->
        active.choices.indexOf(label).takeIf { it >= 0 }?.let { active.nodeBase + it }
    }

    /** Opens an alternate picker without requiring a held pointer. */
    fun openAlternatesFor(base: String): Boolean {
        val key = snapshot.keys.firstOrNull { it.label.equals(base, ignoreCase = true) } ?: return false
        return showAlternates(key, null)
    }

    /** Starts the visible base-key picker used by the Accents action. */
    fun beginAccentSelection(): Boolean {
        if (accentSelection || popup != null) { cancelPointers(); return false }
        if (snapshot.keys.none { AlternateCharacters.forBase(it.action.value.ifBlank { it.label }).isNotEmpty() }) return false
        cancelPointers()
        accentSelection = true
        onAccentStateChanged(true)
        announceForAccessibility(context.getString(R.string.next_choose_accent))
        accessibility.invalidateRoot(); invalidate()
        return true
    }

    private fun scheduleLongPress(pointerId: Int, key: KeyGeometry) {
        val choices = AlternateCharacters.forBase(key.action.value.ifBlank { key.label })
        if (choices.isEmpty()) return
        val pointer = pointers[pointerId] ?: return
        lateinit var task: Runnable
        task = Runnable {
            if (longPress === task && pointers.size == 1 && pointers[pointerId] === pointer &&
                !pointer.cancelled && !multiplePointers && pointer.generation == generation) showAlternates(key, pointerId)
        }
        longPress = task; postDelayed(task, ViewConfiguration.getLongPressTimeout().toLong())
    }

    private fun showAlternates(key: KeyGeometry, pointerId: Int?): Boolean {
        val values = AlternateCharacters.forBase(key.action.value.ifBlank { key.label })
        if (values.isEmpty()) return false
        val choices = values.map(::alternateCase) + context.getString(R.string.next_key_cancel)
        val anchor = key.bounds
        val gap = 4f * density; val minimum = 48f * density
        val availableWidth = snapshot.width; val availableHeight = snapshot.height
        val maximumColumns = minOf(choices.size, maxOf(1, ((availableWidth + gap) / (minimum + gap)).toInt()))
        val rows = (choices.size + maximumColumns - 1) / maximumColumns
        val columns = (choices.size + rows - 1) / rows
        val width = minimum
        val height = minimum
        val totalWidth = columns * width + (columns - 1) * gap
        var left = (anchor.left + anchor.right - totalWidth) / 2f
        left = left.coerceIn(0f, (availableWidth - totalWidth).coerceAtLeast(0f))
        val totalHeight = rows * height + (rows - 1) * gap
        if (totalHeight > availableHeight || totalWidth > availableWidth) return false
        val top = if (anchor.top >= totalHeight + gap) anchor.top - totalHeight - gap else (anchor.bottom + gap).coerceAtMost((availableHeight - totalHeight).coerceAtLeast(0f))
        val bounds = choices.indices.map { index ->
            val row = index / columns; val column = index % columns
            val x = left + column * (width + gap); val y = top + row * (height + gap)
            KeyBounds(x, y, x + width, y + height)
        }
        val travel = KeyBounds(minOf(anchor.left, bounds.minOf { it.left }), minOf(anchor.top, bounds.minOf { it.top }),
            maxOf(anchor.right, bounds.maxOf { it.right }), maxOf(anchor.bottom, bounds.maxOf { it.bottom }))
        cancelPointers()
        if (nextPopupId > Int.MAX_VALUE - 16) nextPopupId = 1000
        nextPopupId += 16
        popup = Popup(pointerId, generation, choices, bounds, travel, nextPopupId)
        onAccentStateChanged(true)
        accessibility.invalidateRoot(); invalidate()
        return true
    }

    private fun routePopupTouch(event: MotionEvent) {
        val active = popup ?: return
        when (event.actionMasked) {
            MotionEvent.ACTION_POINTER_DOWN, MotionEvent.ACTION_POINTER_UP, MotionEvent.ACTION_CANCEL -> cancelPointers()
            MotionEvent.ACTION_DOWN -> {
                val selected = active.bounds.indexOfFirst { it.contains(event.x, event.y) }
                if (active.pointerId != null || selected < 0) { cancelPointers(); return }
                active.pointerId = event.getPointerId(0); active.selected = selected
                parent?.requestDisallowInterceptTouchEvent(true); invalidate()
            }
            MotionEvent.ACTION_MOVE -> {
                val index = active.pointerId?.let(event::findPointerIndex) ?: return
                if (index < 0 || !active.travel.contains(event.getX(index), event.getY(index))) { cancelPointers(); return }
                active.selected = active.bounds.indexOfFirst { it.contains(event.getX(index), event.getY(index)) }
                invalidate()
            }
            MotionEvent.ACTION_UP -> {
                if (active.pointerId != event.getPointerId(0)) { cancelPointers(); return }
                chooseAlternate(active, active.bounds.indexOfFirst { it.contains(event.x, event.y) })
            }
        }
    }

    private fun chooseAlternate(active: Popup, index: Int) {
        val value = if (popup === active && active.generation == generation && index in 0 until active.choices.lastIndex)
            active.choices[index] else null
        cancelPointers()
        if (value != null) onKey(KeyAction(KeyAction.Kind.TEXT, value))
    }

    private fun alternateCase(value: String): String = if (shift) value.uppercase(Locale.ROOT) else value

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
            popup?.let { active ->
                val index = active.bounds.indexOfFirst { it.contains(x, y) }
                return if (index >= 0) active.nodeBase + index else INVALID_ID
            }
            val key = snapshot.keys.firstOrNull { it.bounds.contains(x, y) } ?: return INVALID_ID
            return snapshot.keys.indexOf(key) + 1
        }

        override fun getVisibleVirtualViews(virtualViewIds: MutableList<Int>) {
            val active = popup
            if (active == null) snapshot.keys.indices.forEach { virtualViewIds += it + 1 }
            else active.choices.indices.forEach { virtualViewIds += active.nodeBase + it }
        }

        override fun onPopulateNodeForVirtualView(virtualViewId: Int, node: AccessibilityNodeInfoCompat) {
            val active = popup
            val popupIndex = virtualViewId - (active?.nodeBase ?: 0)
            if (active != null && popupIndex in active.choices.indices) {
                node.text = active.choices[popupIndex]; node.contentDescription = active.choices[popupIndex]
                node.className = "android.widget.Button"; node.isClickable = true
                node.addAction(AccessibilityNodeInfoCompat.ACTION_CLICK)
                val bounds = active.bounds[popupIndex]
                node.setBoundsInParent(Rect(bounds.left.toInt(), bounds.top.toInt(), bounds.right.toInt(), bounds.bottom.toInt()))
                return
            }
            val key = if (active == null) snapshot.keys.getOrNull(virtualViewId - 1) else null
            if (key == null) {
                node.text = context.getString(R.string.next_key_unavailable)
                node.isEnabled = false; node.isVisibleToUser = false
                node.setBoundsInParent(Rect(0, 0, 1, 1)); return
            }
            node.text = if (shift && key.action.kind == KeyAction.Kind.TEXT) key.label.uppercase(Locale.ROOT) else key.label
            node.contentDescription = semanticLabel(key)
            node.className = "android.widget.Button"
            node.isClickable = true
            node.isCheckable = key.action.kind == KeyAction.Kind.SHIFT
            node.isChecked = key.action.kind == KeyAction.Kind.SHIFT && shift
            node.addAction(AccessibilityNodeInfoCompat.ACTION_CLICK)
            if (longPressEnabled && AlternateCharacters.forBase(key.action.value.ifBlank { key.label }).isNotEmpty()) node.addAction(AccessibilityNodeInfoCompat.ACTION_LONG_CLICK)
            node.setBoundsInParent(Rect(
                key.bounds.left.toInt(), key.bounds.top.toInt(), key.bounds.right.toInt(), key.bounds.bottom.toInt()
            ))
        }

        override fun onPopulateEventForVirtualView(virtualViewId: Int, event: AccessibilityEvent) {
            popup?.let { active ->
                active.choices.getOrNull(virtualViewId - active.nodeBase)?.let { event.contentDescription = it }
                return
            }
            snapshot.keys.getOrNull(virtualViewId - 1)?.let { event.contentDescription = semanticLabel(it) }
        }

        override fun onPerformActionForVirtualView(virtualViewId: Int, action: Int, arguments: android.os.Bundle?): Boolean {
            popup?.let { active ->
                val index = virtualViewId - active.nodeBase
                if (index !in active.choices.indices || action != AccessibilityNodeInfoCompat.ACTION_CLICK) return false
                sendEventForVirtualView(virtualViewId, AccessibilityEvent.TYPE_VIEW_CLICKED)
                chooseAlternate(active, index); return true
            }
            val key = snapshot.keys.getOrNull(virtualViewId - 1) ?: return false
            if (action == AccessibilityNodeInfoCompat.ACTION_LONG_CLICK) return longPressEnabled && openAlternatesFor(key.action.value.ifBlank { key.label })
            if (action != AccessibilityNodeInfoCompat.ACTION_CLICK) return false
            sendEventForVirtualView(virtualViewId, AccessibilityEvent.TYPE_VIEW_CLICKED)
            if (accentSelection) {
                if (!openAlternatesFor(key.action.value.ifBlank { key.label })) cancelPointers()
            } else onKey(key.action)
            return true
        }
    }
}
