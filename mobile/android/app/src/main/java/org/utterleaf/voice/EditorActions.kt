package org.utterleaf.voice

import android.view.inputmethod.InputConnection

enum class EditorAction(val label: String, val menuId: Int) {
    UNDO("Undo", android.R.id.undo), REDO("Redo", android.R.id.redo),
    SELECT_ALL("Select all", android.R.id.selectAll), CUT("Cut", android.R.id.cut),
    COPY("Copy", android.R.id.copy), PASTE("Paste", android.R.id.paste)
}

/** Explicit editor commands only: no clipboard reads, history or terminal shortcut fallback. */
object EditorActions {
    /** One host action attempt only. Refusal or a broken connection never falls back to text or keys. */
    internal fun performImeAction(connection: InputConnection?, action: Int): Boolean {
        if (connection == null) return false
        return try { connection.performEditorAction(action) } catch (_: RuntimeException) { false }
    }

    fun perform(connection: InputConnection?, action: EditorAction, inputType: Int?): Boolean {
        return perform(connection, action, EditorCapabilities.resolve(inputType))
    }

    internal fun perform(connection: InputConnection?, action: EditorAction,
                         capabilities: EditorCapabilities): Boolean {
        if (connection == null || !capabilities.knownEditable) return false
        if (action == EditorAction.COPY && !capabilities.clipboard.copy) return false
        if (action == EditorAction.CUT && !capabilities.clipboard.cut) return false
        if (action == EditorAction.PASTE && !capabilities.clipboard.paste) return false
        return try { connection.performContextMenuAction(action.menuId) } catch (_: RuntimeException) { false }
    }
}
