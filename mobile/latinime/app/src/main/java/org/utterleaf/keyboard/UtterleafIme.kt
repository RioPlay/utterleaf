package org.utterleaf.keyboard

import android.view.WindowManager
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import com.android.inputmethod.latin.R
import com.android.inputmethod.latin.LatinIME

/** Experimental entry point; all keyboard composition remains in LatinIME. */
class UtterleafIme : LatinIME() {
    private var keyboardRoot: View? = null

    override fun setInputView(view: View) {
        super.setInputView(view)
        keyboardRoot = view
        applyBottomSpace()
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        applyBottomSpace()
    }

    private fun applyBottomSpace() {
        val frame = keyboardRoot?.findViewById<View>(R.id.main_keyboard_frame) ?: return
        val space = (ComfortPreferences(this).read().bottomSpaceDp * resources.displayMetrics.density).toInt()
        if (frame.paddingBottom != space) {
            frame.setPadding(frame.paddingLeft, frame.paddingTop, frame.paddingRight, space)
        }
    }

    override fun getCurrentInputConnection(): InputConnection? {
        val connection = super.getCurrentInputConnection() ?: return null
        return if (EditorPrivacy.allowsContext(currentInputEditorInfo?.inputType ?: 0)) connection
        else SensitiveInputConnection(connection)
    }

    override fun onCreate() {
        super.onCreate()
        window?.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
    }

    override fun onDestroy() {
        keyboardRoot = null
        super.onDestroy()
    }
}
