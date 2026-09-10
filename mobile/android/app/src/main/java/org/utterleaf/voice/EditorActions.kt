package org.utterleaf.voice

import android.text.InputType
import android.view.inputmethod.InputConnection

enum class EditorAction(val label: String, val menuId: Int) {
    UNDO("Undo", android.R.id.undo), REDO("Redo", android.R.id.redo),
    SELECT_ALL("Select all", android.R.id.selectAll), CUT("Cut", android.R.id.cut),
    COPY("Copy", android.R.id.copy), PASTE("Paste", android.R.id.paste)
}

/** Explicit editor commands only: no clipboard reads, history or terminal shortcut fallback. */
object EditorActions {
    fun perform(connection: InputConnection?, action: EditorAction, inputType: Int?): Boolean {
        if (connection == null || inputType == null || inputType == InputType.TYPE_NULL) return false
        val cls = inputType and InputType.TYPE_MASK_CLASS
        val variation = inputType and InputType.TYPE_MASK_VARIATION
        val password = (cls == InputType.TYPE_CLASS_NUMBER && variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD) ||
            (cls == InputType.TYPE_CLASS_TEXT && variation in listOf(InputType.TYPE_TEXT_VARIATION_PASSWORD,
                InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD, InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD))
        if (password && action in listOf(EditorAction.COPY, EditorAction.CUT)) return false
        return try { connection.performContextMenuAction(action.menuId) } catch (_: RuntimeException) { false }
    }
}
