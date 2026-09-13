package org.utterleaf.voice

import android.app.Activity
import android.os.Bundle
import android.text.InputType
import android.view.KeyEvent
import android.view.inputmethod.EditorInfo
import android.widget.EditText

/** One editor contract per activity launch; instrumentation never shares its EditorInfo session. */
class KeyboardEditorContractActivity : Activity() {
    lateinit var editor: EditText
        private set
    var action = EditorInfo.IME_ACTION_NONE
        private set
    var rawKey = KeyEvent.KEYCODE_UNKNOWN
        private set

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val options = intent.getIntExtra("ime_options", EditorInfo.IME_ACTION_DONE)
        val raw = intent.getBooleanExtra("raw", false)
        val multiline = intent.getBooleanExtra("multiline", false)
        val password = intent.getBooleanExtra("password", false)
        editor = EditText(this).apply {
            inputType = if (raw) InputType.TYPE_NULL else InputType.TYPE_CLASS_TEXT or
                if (password) InputType.TYPE_TEXT_VARIATION_PASSWORD else
                if (multiline) InputType.TYPE_TEXT_FLAG_MULTI_LINE else 0
            setSingleLine(!multiline)
            imeOptions = options
            setOnEditorActionListener { _, value, _ -> action = value; true }
            setOnKeyListener { _, code, event ->
                if (raw && event.action == KeyEvent.ACTION_DOWN) rawKey = code
                false
            }
        }
        setContentView(editor)
    }
}
