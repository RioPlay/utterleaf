package org.utterleaf.voice

import android.app.Activity
import android.os.Bundle
import android.text.InputType
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.LinearLayout

/** Synthetic editor for instrumentation. Never packaged in a release APK. */
class KeyboardTestActivity : Activity() {
    lateinit var editor: EditText
        private set
    lateinit var password: EditText
        private set
    var lastEditorAction = EditorInfo.IME_ACTION_NONE
        private set

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        editor = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_DONE
            hint = "Synthetic keyboard test"
            setOnEditorActionListener { _, action, _ ->
                lastEditorAction = action
                true
            }
        }
        password = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            imeOptions = EditorInfo.IME_ACTION_DONE
            hint = "Synthetic password test"
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(editor)
            addView(password)
        })
    }
}
