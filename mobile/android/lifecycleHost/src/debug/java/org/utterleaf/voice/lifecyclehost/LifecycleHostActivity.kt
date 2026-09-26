package org.utterleaf.voice.lifecyclehost

import android.app.Activity
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.LinearLayout

/** Disposable editor owned by a package and process separate from the debug IME. */
class LifecycleHostActivity : Activity() {
    lateinit var editor: EditText
        private set

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        editor = EditText(this).apply {
            hint = "Synthetic lifecycle host editor"
            contentDescription = "Synthetic lifecycle host editor"
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_DONE
            setSingleLine(true)
            isSaveEnabled = false
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val padding = (24 * resources.displayMetrics.density).toInt()
            setPadding(padding, padding * 3, padding, padding)
            addView(editor, LinearLayout.LayoutParams(-1, -2))
        })
    }
}
