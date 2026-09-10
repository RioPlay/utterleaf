package org.utterleaf.voice

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.InsetDrawable
import android.graphics.drawable.RippleDrawable
import android.graphics.drawable.StateListDrawable
import android.os.SystemClock
import android.util.TypedValue
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Secondary hints are visual; the button keeps its primary spoken key label. */
internal class HintedKey(context: Context) : Button(context) {
    var secondaryHint: String? = null
        set(value) { field = value; invalidate() }
    private val hintPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    override fun onDraw(canvas: Canvas) {
        val hint = secondaryHint
        if (hint != null) {
            hintPaint.color = currentTextColor
            hintPaint.textSize = 10 * resources.displayMetrics.scaledDensity
            // At very large label sizes, preserve the primary key's legibility.
            val offset = Ui.dp(context, 4).toFloat()
            val primaryTop = (height - (paint.fontMetrics.descent - paint.fontMetrics.ascent)) / 2f + offset
            if (Ui.dp(context, 3) + hintPaint.fontMetrics.descent - hintPaint.fontMetrics.ascent <= primaryTop - Ui.dp(context, 2)) {
                canvas.save()
                canvas.translate(0f, offset)
                super.onDraw(canvas)
                canvas.restore()
                hintPaint.textAlign = Paint.Align.RIGHT
                canvas.drawText(hint, width - Ui.dp(context, 6).toFloat(),
                    Ui.dp(context, 3).toFloat() - hintPaint.ascent(), hintPaint)
                return
            }
        }
        super.onDraw(canvas)
    }
}

/** Independent keyboard layout; native buttons retain accessibility and focus semantics. */
class TypingPanel(private val context: Context, private val options: KeyboardOptions,
    private val commit: (String) -> Boolean, private val erase: () -> Unit,
    private val enter: () -> Unit, private val move: (Boolean) -> Unit,
    private val dictate: () -> Unit, private val settings: () -> Unit,
    private val switchKeyboard: () -> Unit,
    private val terminalKey: (Int, Boolean, Boolean, Boolean) -> Boolean = { _, _, _, _ -> false },
    private val modifiedCommit: (String, Boolean, Boolean) -> Boolean = { _, _, _ -> false }) {
    private val surface = Color.parseColor(if (options.light) "#E8EEEB" else "#171E20")
    private val keyColor = Color.parseColor(if (options.light) "#FFFFFF" else "#303A3D")
    private val utilityColor = Color.parseColor(if (options.light) "#D1DFD6" else "#24322D")
    private val ink = Color.parseColor(if (options.light) "#17251D" else "#F0F5F2")
    private val accent = Color.parseColor(if (options.light) "#25643D" else "#A2DFB3")
    private val accentInk = Color.parseColor(if (options.light) "#FFFFFF" else "#10291B")
    private val keyHeight = if (options.large) 66 else 54
    val view = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(Ui.dp(context, 3), 0, Ui.dp(context, 3), Ui.dp(context, 4))
        setBackgroundColor(surface)
        layoutDirection = View.LAYOUT_DIRECTION_LTR
    }
    private var shift = false
    private var caps = false
    private var symbols = false
    private var moreSymbols = false
    private var toolsOpen = false
    private var ctrl = false
    private var alt = false
    private var functionKeys = false
    private var ctrlKey: Button? = null
    private var altKey: Button? = null
    private var voiceAllowed = false
    private var actionLabel = "Enter"
    private var lastKey = ""
    private var lastTime = 0L
    private val letters = mutableListOf<Button>()
    private var shiftKey: Button? = null
    private var capsKey: Button? = null
    private var toolbarStatus: TextView? = null
    private var alternateMode = false
    private var alternateKey: Char? = null
    private var layoutGeneration = 0

    fun reset(allowVoice: Boolean, numeric: Boolean, action: String) {
        shift = false; caps = false; symbols = numeric; moreSymbols = false; toolsOpen = false
        ctrl = false; alt = false; functionKeys = false
        alternateMode = false; alternateKey = null
        voiceAllowed = allowVoice; actionLabel = action
        lastKey = ""; lastTime = 0
        render()
    }
    private fun shape(color: Int) = GradientDrawable().apply {
        setColor(color); cornerRadius = Ui.dp(context, 9).toFloat()
    }
    private fun key(row: LinearLayout, label: String, description: String = label, weight: Float = 1f,
        utility: Boolean = false, primary: Boolean = false, height: Int = keyHeight,
        action: () -> Unit): Button {
        val generation = layoutGeneration
        val button = HintedKey(context).apply {
            text = label; contentDescription = description; isAllCaps = false
            textSize = if (label.length > 2) (if (options.large) 16f else 13f) else (if (options.large) 26f else 22f)
            setSingleLine()
            setHorizontallyScrolling(false)
            setAutoSizeTextTypeUniformWithConfiguration(12,
                if (label.length > 2) (if (options.large) 16 else 13) else (if (options.large) 26 else 22),
                1, TypedValue.COMPLEX_UNIT_SP)
            typeface = Typeface.create("sans-serif", Typeface.NORMAL)
            minWidth = 0; minimumWidth = 0; minHeight = 0; minimumHeight = 0
            setPadding(0, 0, 0, 0); includeFontPadding = false
            gravity = Gravity.CENTER
            val fill = StateListDrawable().apply {
                addState(intArrayOf(android.R.attr.state_selected), shape(accent))
                addState(intArrayOf(android.R.attr.state_focused), shape(accent))
                addState(intArrayOf(), shape(if (primary) accent else if (utility) utilityColor else keyColor))
            }
            background = InsetDrawable(RippleDrawable(ColorStateList.valueOf(0x40808080), fill, shape(Color.WHITE)),
                Ui.dp(context, 2), Ui.dp(context, 3), Ui.dp(context, 2), Ui.dp(context, 3))
            backgroundTintList = null
            stateListAnimator = null
            setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled),
                intArrayOf(android.R.attr.state_selected), intArrayOf(android.R.attr.state_focused), intArrayOf()),
                intArrayOf(Color.parseColor(if (options.light) "#66766B" else "#97A79E"), accentInk, accentInk,
                    if (primary) accentInk else ink)))
            isSoundEffectsEnabled = false
            isHapticFeedbackEnabled = options.haptics
            setOnClickListener {
                if (generation != layoutGeneration) return@setOnClickListener
                val now = SystemClock.elapsedRealtime()
                if (!options.repeatGuard || description != lastKey || now - lastTime >= 250) {
                    lastKey = description; lastTime = now
                    if (options.haptics) performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                    action()
                }
            }
        }
        row.addView(button, LinearLayout.LayoutParams(0, Ui.dp(context, height), weight))
        return button
    }
    private fun row() = LinearLayout(context).also {
        it.orientation = LinearLayout.HORIZONTAL
        it.isBaselineAligned = false
        view.addView(it, LinearLayout.LayoutParams(-1, -2))
    }
    private fun spacer(row: LinearLayout, weight: Float) {
        row.addView(View(context).apply { importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO },
            LinearLayout.LayoutParams(0, 1, weight))
    }
    private fun characters(row: LinearLayout, sequence: String) {
        sequence.forEach { character ->
            val button = key(row, character.toString()) {
                if (alternateMode && character in 'a'..'z') {
                    openAlternates(character)
                } else {
                    val value = displayed(character)
                    if (type(value.toString()) && shift) { shift = false; updateCase() }
                }
            }
            if (!symbols) {
                button.tag = character; letters.add(button)
                if (character in 'a'..'z') {
                    if (options.secondaryHints) (button as HintedKey).secondaryHint = AlternateCharacters.hint(character)
                    val generation = layoutGeneration
                    button.setOnLongClickListener {
                        if (generation != layoutGeneration) false else {
                            openAlternates(character); true
                        }
                    }
                }
            }
        }
    }

    private fun openAlternates(character: Char) {
        alternateKey = character; render()
        view.announceForAccessibility("Choose an alternate for ${displayed(character)}, or Cancel")
    }

    private fun alternateRows(character: Char) {
        val choices = AlternateCharacters.choices(character, shift xor caps)
        val heading = TextView(context).apply {
            text = "Alternates for ${displayed(character)}"; textSize = 16f
            setTextColor(ink); gravity = Gravity.CENTER; minHeight = Ui.dp(context, 40)
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        view.addView(heading)
        choices.chunked(5).forEach { group ->
            val line = row()
            group.forEach { value ->
                key(line, value) {
                    val accepted = type(value)
                    if (accepted) {
                        shift = false; alternateKey = null; alternateMode = false; render()
                    }
                }
            }
            repeat(5 - group.size) { spacer(line, 1f) }
        }
        key(row(), "Cancel", "Cancel alternate characters", utility = true) {
            alternateKey = null; alternateMode = false; render()
        }
    }
    private fun displayed(character: Char): Char {
        if (symbols) return character
        if (character in 'a'..'z') return if (shift xor caps) character.uppercaseChar() else character
        val digit = "1234567890".indexOf(character)
        return if (shift && digit >= 0) "!@#$%^&*()"[digit] else character
    }
    private fun releaseModifiers() {
        ctrl = false; alt = false
        updateCase()
    }
    private fun type(value: String): Boolean {
        val accepted = if (ctrl || alt) modifiedCommit(value, ctrl, alt) else commit(value)
        releaseModifiers()
        if (!accepted) unavailable() else toolbarStatus?.text = "English · offline"
        return accepted
    }
    private fun unavailable() {
        toolbarStatus?.apply {
            text = "Key unavailable"
            announceForAccessibility("This key is not supported in the current field")
        }
    }
    private fun special(code: Int) {
        val accepted = terminalKey(code, ctrl, alt, shift)
        shift = false; releaseModifiers()
        if (!accepted) unavailable() else toolbarStatus?.text = "English · offline"
    }
    private fun delete() {
        if (ctrl || alt || (options.terminal && shift)) special(KeyEvent.KEYCODE_DEL) else erase()
    }
    private fun terminalRows() {
        val modifiers = row()
        key(modifiers, "Esc", "Escape", utility = true) { special(KeyEvent.KEYCODE_ESCAPE) }
        key(modifiers, "Tab", utility = true) { special(KeyEvent.KEYCODE_TAB) }
        ctrlKey = key(modifiers, "Ctrl", "Control off", utility = true) { ctrl = !ctrl; updateCase() }
        altKey = key(modifiers, "Alt", "Alt off", utility = true) { alt = !alt; updateCase() }
        key(modifiers, "Fn", "Function keys", utility = true) { functionKeys = !functionKeys; render() }
            .apply { isSelected = functionKeys }
        val navigation = row()
        listOf(Triple("←", "Left arrow", KeyEvent.KEYCODE_DPAD_LEFT),
            Triple("↓", "Down arrow", KeyEvent.KEYCODE_DPAD_DOWN),
            Triple("↑", "Up arrow", KeyEvent.KEYCODE_DPAD_UP),
            Triple("→", "Right arrow", KeyEvent.KEYCODE_DPAD_RIGHT),
            Triple("Home", "Home", KeyEvent.KEYCODE_MOVE_HOME),
            Triple("End", "End", KeyEvent.KEYCODE_MOVE_END),
            Triple("PgUp", "Page up", KeyEvent.KEYCODE_PAGE_UP),
            Triple("PgDn", "Page down", KeyEvent.KEYCODE_PAGE_DOWN)).forEach { (label, description, code) ->
            key(navigation, label, description, utility = true) { special(code) }
        }
    }
    private fun render() {
        layoutGeneration++
        view.removeAllViews(); letters.clear(); shiftKey = null; capsKey = null; ctrlKey = null; altKey = null
        val toolbar = row()
        key(toolbar, if (toolsOpen) "Close" else "Tools", "Keyboard tools", 2f, utility = true, height = 48) {
            toolsOpen = !toolsOpen; alternateMode = false; alternateKey = null; render()
        }.apply { isSelected = toolsOpen }
        toolbarStatus = TextView(context).apply {
            text = if (alternateMode) "Choose a letter" else "English · offline"; textSize = 13f; setTextColor(ink); gravity = Gravity.CENTER
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        toolbar.addView(toolbarStatus, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 5.5f))
        key(toolbar, "Voice", "Dictate", 2.5f, utility = true, height = 48) { dictate() }
            .apply { isEnabled = voiceAllowed }
        if (toolsOpen) {
            val tools = row()
            capsKey = key(tools, "Caps", "Caps lock off", utility = true, height = 48) {
                caps = !caps
                if (alternateKey != null) render() else updateCase()
            }
            key(tools, "←", "Move cursor left", utility = true, height = 48) { move(true) }
            key(tools, "→", "Move cursor right", utility = true, height = 48) { move(false) }
            key(tools, "Accents", "Accents and alternate characters", utility = true, height = 48) {
                alternateMode = !alternateMode; alternateKey = null
                symbols = false; functionKeys = false; render()
                if (alternateMode) view.announceForAccessibility("Tap a letter to choose accents or symbols")
            }.apply { isSelected = alternateMode }
            key(tools, "Settings", "Keyboard settings", utility = true, height = 48) { settings() }
            key(tools, "Switch", "Switch keyboard", utility = true, height = 48) { switchKeyboard() }
        }
        alternateKey?.let { alternateRows(it); updateCase(); return }
        if (options.terminal) terminalRows()
        if ((options.numberRow || options.terminal) && !symbols && !functionKeys) characters(row(), "1234567890")
        if (options.terminal && functionKeys) {
            for (start in listOf(1, 7)) {
                val functions = row()
                for (number in start until start + 6) {
                    key(functions, "F$number", utility = true) { special(KeyEvent.KEYCODE_F1 + number - 1) }
                }
            }
            val editing = row()
            shiftKey = key(editing, "⇧", "Shift off", 1.5f, utility = true) { shift = !shift; updateCase() }
            key(editing, "Insert", utility = true, weight = 2f) { special(KeyEvent.KEYCODE_INSERT) }
            key(editing, "Del", "Forward delete", 2f, utility = true) { special(KeyEvent.KEYCODE_FORWARD_DEL) }
            key(editing, "ABC", "Return to letters", 3f, utility = true) {
                functionKeys = false; symbols = false; render()
            }
            key(editing, "⌫", "Delete", 1.5f, utility = true) { delete() }
        } else if (symbols) {
            characters(row(), if (moreSymbols) "~`|•√π÷×§∆" else "1234567890")
            val middle = row()
            characters(middle, if (moreSymbols) "£¢€¥^°={}\\" else "@#$%&-+()/")
            val third = row()
            key(third, if (moreSymbols) "?123" else "=\\<",
                if (moreSymbols) "More numbers and symbols" else "More symbols", 1.5f, utility = true) {
                moreSymbols = !moreSymbols; render()
            }
            characters(third, if (moreSymbols) "_<>[]¶©" else "*\"':;!?")
            key(third, "⌫", "Delete", 1.5f, utility = true) { delete() }
        } else {
            characters(row(), "qwertyuiop")
            val home = row(); spacer(home, .5f); characters(home, "asdfghjkl"); spacer(home, .5f)
            val third = row()
            shiftKey = key(third, "⇧", "Shift off", 1.5f, utility = true) { shift = !shift; updateCase() }
            characters(third, "zxcvbnm")
            key(third, "⌫", "Delete", 1.5f, utility = true) { delete() }
        }
        val bottom = row()
        key(bottom, if (symbols) "ABC" else "?123", "Switch letters and symbols", 1.5f, utility = true) {
            symbols = !symbols; moreSymbols = false; functionKeys = false
            alternateMode = false; alternateKey = null; render()
        }
        key(bottom, ",") { type(",") }
        key(bottom, "space", "Space", 5f) { type(" ") }
        key(bottom, ".") { type(".") }
        key(bottom, if (actionLabel == "Enter") "↵" else actionLabel, actionLabel, 1.5f, primary = true) {
            if (ctrl || alt || (options.terminal && shift)) special(KeyEvent.KEYCODE_ENTER) else enter()
        }
        updateCase()
    }
    private fun updateCase() {
        letters.forEach { button ->
            button.text = displayed(button.tag as Char).toString()
            button.contentDescription = button.text
        }
        shiftKey?.apply {
            isSelected = shift || caps
            contentDescription = if (shift) "Shift on" else "Shift off"
            text = if (caps) "⇪" else "⇧"
        }
        capsKey?.apply { isSelected = caps; contentDescription = if (caps) "Caps lock on" else "Caps lock off" }
        ctrlKey?.apply { isSelected = ctrl; contentDescription = if (ctrl) "Control on" else "Control off" }
        altKey?.apply { isSelected = alt; contentDescription = if (alt) "Alt on" else "Alt off" }
    }
}
