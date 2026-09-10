package org.utterleaf.voice

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.os.SystemClock
import android.view.HapticFeedbackConstants
import android.view.View
import android.widget.Button
import android.widget.LinearLayout

/** Native buttons expose each key to accessibility services without custom touch interception. */
class TypingPanel(private val context: Context, private val options: KeyboardOptions,
    private val commit: (String) -> Boolean, private val erase: () -> Unit,
    private val enter: () -> Unit, private val move: (Boolean) -> Unit,
    private val dictate: () -> Unit, private val settings: () -> Unit,
    private val switchKeyboard: () -> Unit) {
    val view = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(Ui.dp(context, 3), 0, Ui.dp(context, 3), Ui.dp(context, 3))
        setBackgroundColor(if (options.light) Color.rgb(241, 246, 242) else Color.rgb(23, 30, 32))
        // A Latin layout must keep its physical order in RTL applications, too.
        layoutDirection = View.LAYOUT_DIRECTION_LTR
    }
    private var shift = false
    private var caps = false
    private var symbols = false
    private var voiceAllowed = false
    private var actionLabel = "Enter"
    private var lastKey = ""
    private var lastTime = 0L
    private val letters = mutableListOf<Button>()
    private lateinit var shiftKey: Button
    private lateinit var capsKey: Button

    fun reset(allowVoice: Boolean, numeric: Boolean, action: String) {
        shift = false; caps = false; symbols = numeric
        voiceAllowed = allowVoice; actionLabel = action
        lastKey = ""; lastTime = 0
        render()
    }
    private fun key(row: LinearLayout, label: String, description: String = label, weight: Float = 1f,
        action: () -> Unit): Button {
        val button = Ui.button(context, label) {}.apply {
            contentDescription = description
            textSize = if (options.large) 22f else 18f
            minWidth = 0; minimumWidth = 0
            setPadding(0, 0, 0, 0)
            isSoundEffectsEnabled = false
            isHapticFeedbackEnabled = options.haptics
            if (options.light) {
                backgroundTintList = ColorStateList.valueOf(Color.rgb(215, 229, 219))
                setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
                    intArrayOf(Color.rgb(96, 110, 99), Color.rgb(15, 48, 27))))
            }
            setOnClickListener {
                val now = SystemClock.elapsedRealtime()
                // Opt-in debounce is scoped to repeated activation of the same key.
                if (!options.repeatGuard || description != lastKey || now - lastTime >= 250) {
                    lastKey = description; lastTime = now
                    if (options.haptics) performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                    action()
                }
            }
        }
        row.addView(button, LinearLayout.LayoutParams(0, Ui.dp(context, if (options.large) 64 else 50), weight))
        return button
    }
    private fun row() = LinearLayout(context).also { view.addView(it) }
    private fun render() {
        view.removeAllViews(); letters.clear()
        val tools = row()
        key(tools, "Mic", "Dictate") { dictate() }.apply { isEnabled = voiceAllowed }
        key(tools, "←", "Move cursor left") { move(true) }
        key(tools, "→", "Move cursor right") { move(false) }
        key(tools, "⚙", "Keyboard settings") { settings() }
        key(tools, "⌨", "Switch keyboard") { switchKeyboard() }
        val rows = if (symbols) listOf("1234567890", "@#%&*()-+=", "!?/'\":;,._", "[]{}<>\\|~`$")
                   else listOf("qwertyuiop", "asdfghjkl", "zxcvbnm")
        rows.forEach { sequence ->
            val row = row()
            sequence.forEach { character ->
                val button = key(row, character.toString()) {
                    val value = if (!symbols && (shift xor caps)) character.uppercaseChar() else character
                    if (commit(value.toString()) && shift) { shift = false; updateCase() }
                }
                if (!symbols) letters.add(button)
            }
        }
        val bottom = row()
        key(bottom, if (symbols) "ABC" else "123", "Switch letters and symbols") { symbols = !symbols; render() }
        shiftKey = key(bottom, "⇧", "Shift off") { shift = !shift; updateCase() }
        capsKey = key(bottom, "⇪", "Caps lock off") { caps = !caps; updateCase() }
        key(bottom, "Space", weight = 2f) { commit(" ") }
        key(bottom, "⌫", "Delete") { erase() }
        key(bottom, "↵", actionLabel) { enter() }
        updateCase()
    }
    private fun updateCase() {
        letters.forEach { button ->
            button.text = if (shift xor caps) button.text.toString().uppercase() else button.text.toString().lowercase()
            button.contentDescription = button.text
        }
        shiftKey.isSelected = shift; shiftKey.contentDescription = if (shift) "Shift on" else "Shift off"
        capsKey.isSelected = caps; capsKey.contentDescription = if (caps) "Caps lock on" else "Caps lock off"
        shiftKey.text = if (shift) "⇧ •" else "⇧"
        capsKey.text = if (caps) "⇪ •" else "⇪"
    }
}
