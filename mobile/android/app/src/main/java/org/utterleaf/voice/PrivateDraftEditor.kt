package org.utterleaf.voice

import android.content.Context
import android.os.Build
import android.os.Bundle
import android.os.Parcelable
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.util.SparseArray
import android.view.ActionMode
import android.view.ContentInfo
import android.view.ContextMenu
import android.view.DragEvent
import android.view.KeyEvent
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewStructure
import android.view.accessibility.AccessibilityNodeInfo
import android.view.autofill.AutofillValue
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.view.textclassifier.TextClassifier
import android.widget.EditText

/**
 * An owned draft editor whose visible text is a projection of [PrivateDraftBuffer].
 *
 * Text mutation is deliberately unavailable through the platform EditText paths.
 * Utterleaf's on-screen keys call this controller instead. Hardware typing is not
 * supported while this surface is open.
 */
class PrivateDraftEditor(
    context: Context,
    private val buffer: PrivateDraftBuffer = PrivateDraftBuffer(),
    private val onChanged: (PrivateDraftSnapshot) -> Unit = {},
) {
    private var syncing = false
    private var rejectingExternalEdit = false
    private var disposed = false

    val view: EditText = privateDraftEditText(context).apply {
        hint = "Private draft"
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or
            InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        imeOptions = EditorInfo.IME_FLAG_NO_EXTRACT_UI or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
        isSaveEnabled = false
        isSaveFromParentEnabled = false
        showSoftInputOnFocus = false
        importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        if (Build.VERSION.SDK_INT >= 30) {
            importantForContentCapture = View.IMPORTANT_FOR_CONTENT_CAPTURE_NO_EXCLUDE_DESCENDANTS
        }
        setAutofillHints()
        setTextClassifier(TextClassifier.NO_OP)
        setTextIsSelectable(true)
        isLongClickable = false
        customSelectionActionModeCallback = REJECT_ACTION_MODE
        customInsertionActionModeCallback = REJECT_ACTION_MODE
        keyListener = null
    }

    val current: PrivateDraftSnapshot get() = buffer.current
    val canUndo: Boolean get() = buffer.canUndo
    val canRedo: Boolean get() = buffer.canRedo
    val isDisposed: Boolean get() = disposed

    init {
        (view as PrivateDraftEditText).selectionChanged = { start, end ->
            if (!syncing && !rejectingExternalEdit && !disposed) {
                if (buffer.setSelection(start, end)) notifyChanged() else syncView()
            }
        }
        view.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(text: CharSequence?, start: Int, count: Int, after: Int) {
                if (!syncing) rejectingExternalEdit = true
            }
            override fun onTextChanged(text: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(text: Editable?) {
                if (rejectingExternalEdit) {
                    rejectingExternalEdit = false
                    syncView()
                }
            }
        })
        syncView()
    }

    /** Inserts text at the private selection. Rejection leaves text and selection unchanged. */
    fun replace(value: String): Boolean = mutate { buffer.replaceSelection(value) }

    /** Deletes the selection or the preceding Unicode code point. */
    fun erase(): Boolean {
        val state = buffer.current
        if (state.selectionStart != state.selectionEnd) return replace("")
        val cursor = state.selectionEnd
        if (cursor == 0) return !disposed
        val previous = Character.offsetByCodePoints(state.text, cursor, -1)
        val next = state.text.removeRange(previous, cursor)
        return mutate { buffer.acceptExternalEdit(next, previous, previous) }
    }

    /** Handles the navigation and forward-delete keys exposed by the restricted keyboard. */
    fun navigate(keyCode: Int, select: Boolean = false): Boolean {
        if (disposed) return false
        if (keyCode == KeyEvent.KEYCODE_FORWARD_DEL) return eraseForward()
        val state = buffer.current
        val anchor = state.selectionStart
        val extent = state.selectionEnd
        val destination = destination(state.text, anchor, extent, keyCode, select) ?: return false
        return mutate { buffer.setSelection(if (select) anchor else destination, destination) }
    }

    /** Only local, clipboard-free editor commands are accepted. */
    fun action(action: EditorAction): Boolean = when (action) {
        EditorAction.UNDO -> mutate { buffer.undo() }
        EditorAction.REDO -> mutate { buffer.redo() }
        EditorAction.SELECT_ALL -> mutate {
            val state = buffer.current
            buffer.setSelection(0, state.text.length)
        }
        EditorAction.CUT, EditorAction.COPY, EditorAction.PASTE -> false
    }

    fun clearDraft(): Boolean = mutate { buffer.clear() }

    fun dispose() {
        if (disposed) return
        disposed = true
        buffer.dispose()
        syncView()
        view.clearFocus()
    }

    private fun eraseForward(): Boolean {
        val state = buffer.current
        if (state.selectionStart != state.selectionEnd) return replace("")
        val cursor = state.selectionEnd
        if (cursor == state.text.length) return true
        val next = Character.offsetByCodePoints(state.text, cursor, 1)
        val updated = state.text.removeRange(cursor, next)
        return mutate { buffer.acceptExternalEdit(updated, cursor, cursor) }
    }

    private fun mutate(operation: () -> Boolean): Boolean {
        if (disposed || !operation()) return false
        syncView()
        notifyChanged()
        return true
    }

    private fun notifyChanged() = onChanged(buffer.current)

    private fun syncView() {
        val state = buffer.current
        syncing = true
        try {
            if (view.text.toString() != state.text) view.setText(state.text)
            view.setSelection(state.selectionStart, state.selectionEnd)
        } finally {
            syncing = false
        }
    }

    private fun destination(text: String, anchor: Int, extent: Int, keyCode: Int, select: Boolean): Int? {
        if (!select && anchor != extent) {
            return when (keyCode) {
                KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_MOVE_HOME -> minOf(anchor, extent)
                KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_MOVE_END -> maxOf(anchor, extent)
                else -> null
            }
        }
        return when (keyCode) {
            KeyEvent.KEYCODE_DPAD_LEFT -> if (extent == 0) 0 else Character.offsetByCodePoints(text, extent, -1)
            KeyEvent.KEYCODE_DPAD_RIGHT -> if (extent == text.length) text.length else Character.offsetByCodePoints(text, extent, 1)
            KeyEvent.KEYCODE_MOVE_HOME -> lineStart(text, extent)
            KeyEvent.KEYCODE_MOVE_END -> lineEnd(text, extent)
            KeyEvent.KEYCODE_DPAD_UP -> vertical(text, extent, -1)
            KeyEvent.KEYCODE_DPAD_DOWN -> vertical(text, extent, 1)
            else -> null
        }
    }

    private fun lineStart(text: String, offset: Int): Int =
        if (offset == 0) 0 else text.lastIndexOf('\n', offset - 1).let { if (it < 0) 0 else it + 1 }

    private fun lineEnd(text: String, offset: Int): Int =
        text.indexOf('\n', offset).let { if (it < 0) text.length else it }

    private fun vertical(text: String, offset: Int, direction: Int): Int {
        val start = lineStart(text, offset)
        val column = text.codePointCount(start, offset)
        val adjacentStart: Int
        val adjacentEnd: Int
        if (direction < 0) {
            if (start == 0) return offset
            adjacentEnd = start - 1
            adjacentStart = lineStart(text, adjacentEnd)
        } else {
            val end = lineEnd(text, offset)
            if (end == text.length) return offset
            adjacentStart = end + 1
            adjacentEnd = lineEnd(text, adjacentStart)
        }
        val available = text.codePointCount(adjacentStart, adjacentEnd)
        return Character.offsetByCodePoints(text, adjacentStart, minOf(column, available))
    }

    companion object {
        private val REJECT_ACTION_MODE = object : ActionMode.Callback {
            override fun onCreateActionMode(mode: ActionMode?, menu: Menu?): Boolean = false
            override fun onPrepareActionMode(mode: ActionMode?, menu: Menu?): Boolean = false
            override fun onActionItemClicked(mode: ActionMode?, item: MenuItem?): Boolean = false
            override fun onDestroyActionMode(mode: ActionMode?) = Unit
        }
    }
}

/** Platform-facing view with every non-Utterleaf mutation/import route closed. */
private open class PrivateDraftEditText(context: Context) : EditText(context) {
    var selectionChanged: ((Int, Int) -> Unit)? = null

    override fun onSelectionChanged(selStart: Int, selEnd: Int) {
        super.onSelectionChanged(selStart, selEnd)
        selectionChanged?.invoke(selStart, selEnd)
    }

    override fun onCreateInputConnection(outAttrs: EditorInfo): InputConnection? = null
    override fun onCheckIsTextEditor(): Boolean = false
    override fun onTextContextMenuItem(id: Int): Boolean = false
    override fun showContextMenu(): Boolean = false
    override fun showContextMenu(x: Float, y: Float): Boolean = false
    override fun onCreateContextMenu(menu: ContextMenu) = Unit
    override fun onKeyShortcut(keyCode: Int, event: KeyEvent): Boolean = true
    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean = true
    override fun onKeyUp(keyCode: Int, event: KeyEvent): Boolean = true
    override fun onDragEvent(event: DragEvent): Boolean = false

    override fun getAutofillType(): Int = View.AUTOFILL_TYPE_NONE
    override fun getAutofillValue(): AutofillValue? = null
    override fun autofill(value: AutofillValue) = Unit
    override fun autofill(values: SparseArray<AutofillValue>) = Unit

    override fun performAccessibilityAction(action: Int, arguments: Bundle?): Boolean {
        if (action == AccessibilityNodeInfo.ACTION_SET_TEXT || action == AccessibilityNodeInfo.ACTION_COPY ||
            action == AccessibilityNodeInfo.ACTION_CUT || action == AccessibilityNodeInfo.ACTION_PASTE) return false
        return super.performAccessibilityAction(action, arguments)
    }

    override fun dispatchProvideStructure(structure: ViewStructure) = redact(structure)
    override fun dispatchProvideAutofillStructure(structure: ViewStructure, flags: Int) = redact(structure)
    override fun onProvideAutofillStructure(structure: ViewStructure, flags: Int) = redact(structure)
    override fun onProvideAutofillVirtualStructure(structure: ViewStructure, flags: Int) = redact(structure)
    override fun onProvideContentCaptureStructure(structure: ViewStructure, flags: Int) = redact(structure)

    private fun redact(structure: ViewStructure) {
        structure.setText("")
        structure.setHint("")
        structure.setChildCount(0)
    }

    // TextView's implementation can create a state object containing draft text
    // and selection. This editor deliberately supplies no state to its parent.
    @android.annotation.SuppressLint("MissingSuperCall")
    override fun onSaveInstanceState(): Parcelable = BaseSavedState.EMPTY_STATE
    override fun onRestoreInstanceState(state: Parcelable?) = super.onRestoreInstanceState(BaseSavedState.EMPTY_STATE)
    override fun dispatchSaveInstanceState(container: SparseArray<Parcelable>) = Unit
    override fun dispatchRestoreInstanceState(container: SparseArray<Parcelable>) = Unit
}

private fun privateDraftEditText(context: Context): PrivateDraftEditText =
    if (Build.VERSION.SDK_INT >= 31) PrivateDraftEditText31(context) else PrivateDraftEditText(context)

@android.annotation.TargetApi(31)
private class PrivateDraftEditText31(context: Context) : PrivateDraftEditText(context) {
    override fun onReceiveContent(payload: ContentInfo): ContentInfo = payload
}
