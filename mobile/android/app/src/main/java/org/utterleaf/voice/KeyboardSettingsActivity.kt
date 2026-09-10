package org.utterleaf.voice

import android.app.Activity
import android.app.AlertDialog
import android.os.Bundle
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ScrollView

class KeyboardSettingsActivity : Activity() {
    private var options = KeyboardOptions()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        options = KeyboardOptions.load(this)
        render()
        window.decorView.setOnApplyWindowInsetsListener { view, insets ->
            view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop,
                insets.systemWindowInsetRight, insets.systemWindowInsetBottom); insets
        }
    }
    private fun render() {
        val column = Ui.column(this)
        column.addView(Ui.title(this, "Keyboard preferences"))
        column.addView(Ui.text(this, "Changes save on this device and apply when you reopen the keyboard. No typing history is stored."))
        val preview = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        fun updatePreview() {
            preview.removeAllViews()
            preview.addView(TypingPanel(this, options, { true }, {}, {}, {}, {}, {}, {}).apply {
                reset(false, false, "Enter")
            }.view)
        }
        fun toggle(label: String, checked: Boolean, update: (Boolean) -> Unit) {
            column.addView(CheckBox(this).apply {
                text = label; textSize = 18f; setTextColor(Ui.ink); minHeight = Ui.dp(context, 48)
                isChecked = checked
                setOnCheckedChangeListener { _, value -> update(value); options.save(this@KeyboardSettingsActivity); updatePreview() }
            })
        }
        toggle("Larger keys and labels", options.large) { options = options.copy(large = it) }
        toggle("Light keyboard", options.light) { options = options.copy(light = it) }
        toggle("Number row", options.numberRow) { options = options.copy(numberRow = it) }
        toggle("Terminal controls", options.terminal) { options = options.copy(terminal = it) }
        column.addView(Ui.text(this, "Adds Esc, Tab, Ctrl, Alt, navigation and F1–F12. Ctrl and Alt apply to the next key, then release. Terminal apps decide which shortcuts they support."))
        toggle("Key vibration (respects device settings)", options.haptics) { options = options.copy(haptics = it) }
        toggle("Ignore repeated taps on the same key within 250 ms", options.repeatGuard) { options = options.copy(repeatGuard = it) }
        column.addView(Ui.text(this, "Repeat filtering can help with accidental double taps, but slows intentional double letters. It is off by default. All keys work with a single tap; there are no required holds or swipes."))
        column.addView(Ui.button(this, "Reset keyboard preferences") {
            AlertDialog.Builder(this).setTitle("Reset keyboard preferences?")
                .setMessage("Restore standard key size, dark keys, no extra rows, no vibration, and no repeat filtering. Your model and microphone permission stay unchanged.")
                .setNegativeButton("Cancel", null).setPositiveButton("Reset") { _, _ ->
                    options = KeyboardOptions(); options.save(this); render()
                }.show()
        })
        column.addView(Ui.button(this, "Done") { finish() })
        column.addView(Ui.text(this, "Keyboard preview · does not enter or save text", 18f))
        column.addView(preview); updatePreview()
        setContentView(ScrollView(this).apply { addView(column) })
    }
}
