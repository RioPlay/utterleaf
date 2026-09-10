package org.utterleaf.voice

import android.app.Activity
import android.app.AlertDialog
import android.os.Bundle
import android.text.InputFilter
import android.text.InputType
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.ScrollView

class KeyboardSettingsActivity : Activity() {
    private var options = KeyboardOptions()
    private lateinit var practiceEditor: EditText
    private var practiceActive = false
    private var practiceGeneration = 0
    private var previewContainer: LinearLayout? = null
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        practiceEditor = EditText(this).apply {
            hint = "Practice typing here"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            filters = arrayOf(InputFilter.LengthFilter(256))
            isSaveEnabled = false
            showSoftInputOnFocus = false
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
            setTextIsSelectable(true)
        }
        options = KeyboardOptions.load(this)
    }
    override fun onStart() { super.onStart(); practiceActive = true; render() }
    private fun practiceConnection(generation: Int): android.view.inputmethod.InputConnection? {
        if (!practiceActive || isFinishing || isDestroyed || generation != practiceGeneration) return null
        practiceEditor.requestFocus()
        return practiceEditor.onCreateInputConnection(EditorInfo())
    }
    private fun render() {
        val column = Ui.column(this)
        column.addView(Ui.title(this, "Keyboard preferences"))
        column.addView(Ui.text(this, "Changes save on this device and apply when you reopen the keyboard. No typing history is stored."))
        val preview = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        previewContainer = preview
        fun updatePreview() {
            val generation = ++practiceGeneration
            preview.removeAllViews()
            preview.addView(TypingPanel(this, options,
                { value -> TerminalInput.printable(practiceConnection(generation), value) },
                { TerminalInput.send(practiceConnection(generation), android.view.KeyEvent.KEYCODE_DEL) },
                { TerminalInput.printable(practiceConnection(generation), "\n") },
                { left -> TerminalInput.send(practiceConnection(generation), if (left) android.view.KeyEvent.KEYCODE_DPAD_LEFT else android.view.KeyEvent.KEYCODE_DPAD_RIGHT) },
                {}, {}, {},
                { code, ctrl, alt, shift -> if (shift && !ctrl && !alt && code in listOf(
                    android.view.KeyEvent.KEYCODE_DPAD_LEFT, android.view.KeyEvent.KEYCODE_DPAD_RIGHT,
                    android.view.KeyEvent.KEYCODE_DPAD_UP, android.view.KeyEvent.KEYCODE_DPAD_DOWN,
                    android.view.KeyEvent.KEYCODE_MOVE_HOME, android.view.KeyEvent.KEYCODE_MOVE_END))
                        TerminalInput.select(practiceConnection(generation), code)
                    else TerminalInput.send(practiceConnection(generation), code, ctrl, alt, shift) },
                { value, ctrl, alt -> TerminalInput.printable(practiceConnection(generation), value, ctrl, alt) }).apply {
                reset(false, false, "Enter")
            }.view)
        }
        fun tuningSlider(label: String, value: Int, max: Int, display: (Int) -> String, update: (Int) -> Unit) {
            val labelView = Ui.text(this, display(value), 16f)
            column.addView(labelView)
            column.addView(SeekBar(this).apply {
                this.max = max; progress = value
                contentDescription = label
                setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                    override fun onProgressChanged(seekBar: SeekBar, progress: Int, fromUser: Boolean) {
                        labelView.text = display(progress)
                        if (fromUser) { update(progress); options.save(this@KeyboardSettingsActivity); updatePreview() }
                    }
                    override fun onStartTrackingTouch(seekBar: SeekBar) = Unit
                    override fun onStopTrackingTouch(seekBar: SeekBar) = Unit
                })
            })
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
        toggle("Secondary character hints", options.secondaryHints) { options = options.copy(secondaryHints = it) }
        column.addView(Ui.text(this, "Hold a letter, slide to a highlighted accent or symbol, then release. Slide away to cancel. For tap selection, choose Tools → Accents and a letter. Hiding hints keeps both routes available."))
        column.addView(Ui.text(this, "Hold the period key for quick punctuation, slide to a mark and release. A tap still types a period; symbol pages also provide tap access."))
        column.addView(Ui.text(this, "Slide the spacebar to move the cursor. Hold Shift first, then slide the spacebar with another finger to select text. Release either finger to stop. For taps, use Tools → Select and the cursor arrows. Tools also provides Delete to right, Home and End."))
        toggle("Terminal controls", options.terminal) { options = options.copy(terminal = it) }
        column.addView(Ui.text(this, "Adds Esc, Tab, Ctrl, Alt, navigation and F1–F12. Ctrl and Alt apply to the next key, then release. Terminal apps decide which shortcuts they support."))
        toggle("Key vibration (respects device settings)", options.haptics) { options = options.copy(haptics = it) }
        toggle("Ignore repeated taps on the same key within 250 ms", options.repeatGuard) { options = options.copy(repeatGuard = it) }
        column.addView(Ui.text(this, "Hold a delete key to repeat after the system hold delay; release or slide outside to stop. Repeat filtering disables held deletion and can help with accidental double taps, but slows intentional double letters. It is off by default. All essential actions have tap controls."))
        column.addView(Ui.button(this, "Reset keyboard preferences") {
            AlertDialog.Builder(this).setTitle("Reset keyboard preferences?")
                .setMessage("Restore standard key size, dark keys, secondary character hints, no extra rows, no vibration, and no repeat filtering. Your model and microphone permission stay unchanged.")
                .setNegativeButton("Cancel", null).setPositiveButton("Reset") { _, _ ->
                    options = KeyboardOptions(); options.save(this)
                    getSharedPreferences("keyboard", MODE_PRIVATE).edit().remove("voiceHoldToInsert").apply()
                    render()
                }.show()
        })
        column.addView(Ui.button(this, "Done") { finish() })
        column.addView(Ui.text(this, "Tune your layout", 20f))
        tuningSlider("Key height", if (options.keyHeightDp == 0) 0 else options.keyHeightDp - 47, 33,
            { progress -> if (progress == 0) "Key height: default" else "Key height: ${progress + 47} dp" },
            { progress -> options = options.copy(keyHeightDp = if (progress == 0) 0 else progress + 47) })
        tuningSlider("Bottom space", options.bottomPaddingDp, 80,
            { progress -> "Bottom space: $progress dp" },
            { progress -> options = options.copy(bottomPaddingDp = progress) })
        column.addView(Ui.text(this, "Bottom space raises the keys above the system navigation area. Try typing below; the preview updates immediately."))
        column.addView(Ui.text(this, "Practice area · input stays in this screen, is cleared when it closes, and is never saved", 18f))
        (practiceEditor.parent as? android.view.ViewGroup)?.removeView(practiceEditor)
        column.addView(practiceEditor)
        column.addView(Ui.text(this, "Keyboard preview", 18f))
        column.addView(preview); updatePreview()
        setContentView(ScrollView(this).apply { addView(column); Ui.applySystemInsets(this) })
    }

    private fun clearPractice() {
        practiceActive = false; practiceGeneration++
        previewContainer?.removeAllViews()
        if (::practiceEditor.isInitialized) practiceEditor.setText("")
    }
    override fun finish() { clearPractice(); super.finish() }
    override fun onStop() { clearPractice(); super.onStop() }
}
