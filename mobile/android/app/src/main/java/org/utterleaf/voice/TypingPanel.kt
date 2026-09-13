package org.utterleaf.voice

import android.annotation.SuppressLint
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
import android.view.ViewConfiguration
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

/** Secondary hints are visual; the button keeps its primary spoken key label. */
internal class HintedKey(context: Context) : Button(context) {
    var primaryIcon: android.graphics.drawable.Drawable? = null
    var secondaryHint: String? = null
        set(value) { field = value; invalidate() }
    private val hintPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    override fun onDraw(canvas: Canvas) {
        primaryIcon?.let { icon ->
            super.onDraw(canvas)
            val size = minOf(Ui.dp(context, 28), width, height)
            val left = (width - size) / 2; val top = (height - size) / 2
            icon.setBounds(left, top, left + size, top + size)
            icon.setTint(currentTextColor)
            icon.alpha = if (isEnabled) 255 else 90
            icon.draw(canvas)
            return
        }
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
class TypingPanel(private val context: Context, private var options: KeyboardOptions,
    private val commit: (String) -> Boolean, private val erase: () -> Unit,
    private val enter: () -> Unit, private val move: (Boolean) -> Unit,
    private val dictate: () -> Unit, private val settings: () -> Unit,
    private val switchKeyboard: () -> Unit,
    private val terminalKey: (Int, Boolean, Boolean, Boolean) -> Boolean = { _, _, _, _ -> false },
    private val modifiedCommit: (String, Boolean, Boolean) -> Boolean = { _, _, _ -> false },
    private val quickOptionsChanged: () -> Unit = {},
    private val editorAction: (EditorAction) -> Boolean = { false },
    private val privateEditing: Boolean = false,
    private val openDraft: (() -> Unit)? = null,
    private val actionAvailable: (EditorAction) -> Boolean = { true }) {
    private val surface = Color.parseColor(if (options.light) "#E8EEEB" else "#171E20")
    private val keyColor = Color.parseColor(if (options.light) "#FFFFFF" else "#303A3D")
    private val utilityColor = Color.parseColor(if (options.light) "#D1DFD6" else "#24322D")
    private val ink = Color.parseColor(if (options.light) "#17251D" else "#F0F5F2")
    private val accent = Color.parseColor(if (options.light) "#25643D" else "#A2DFB3")
    private val accentInk = Color.parseColor(if (options.light) "#FFFFFF" else "#10291B")
    private val keyHeight = if (options.keyHeightDp == 0) { if (options.large) 66 else 54 }
        else options.keyHeightDp.coerceIn(48, 80)
    val view = KeyboardSurface(context)
    private val content = object : LinearLayout(context) {
        override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
            val available = View.MeasureSpec.getSize(widthMeasureSpec)
            val mode = View.MeasureSpec.getMode(widthMeasureSpec)
            val measuredWidth = if (mode == View.MeasureSpec.UNSPECIFIED || available <= 0) available
                else alignedContentWidth(available)
            val resolved = if (mode == View.MeasureSpec.UNSPECIFIED) widthMeasureSpec
                else View.MeasureSpec.makeMeasureSpec(measuredWidth, View.MeasureSpec.EXACTLY)
            super.onMeasure(resolved, heightMeasureSpec)
        }
    }.apply {
        orientation = LinearLayout.VERTICAL
        isMotionEventSplittingEnabled = false
        setPadding(Ui.dp(context, 3), 0, Ui.dp(context, 3), Ui.dp(context, 4 + options.bottomPaddingDp.coerceIn(0, 80)))
        setBackgroundColor(surface)
        layoutDirection = View.LAYOUT_DIRECTION_LTR
    }
    private val gestures = KeyboardGestures(view) {
        if (options.holdDelayMs == 0) ViewConfiguration.getLongPressTimeout().toLong()
        else options.holdDelayMs.toLong()
    }
    private val deleteRepeater = DeleteRepeater()
    private var availableWidth = 0
    private var disposed = false
    private var needsRenderOnAttach = false
    init {
        if (privateEditing) options = options.copy(terminal = false)
        view.setBackgroundColor(surface)
        view.modifiers.repeatEnabled = options.deleteRepeat && !options.repeatGuard
        view.bindRolloverEligibility { key -> !alternateMode && !composeActive() && gestures.permitsRollover(key) }
        view.addView(content, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT,
            alignmentGravity()))
        view.addOnLayoutChangeListener { _, left, _, right, _, _, _, _, _ ->
            val width = right - left
            if (width <= 0) return@addOnLayoutChangeListener
            val geometryChanged = availableWidth > 0 && availableWidth != width
            availableWidth = width
            if (geometryChanged) {
                cancelForGeometryChange()
                render()
            } else {
                applyContentAlignment()
            }
        }
        view.addOnAttachStateChangeListener(object : View.OnAttachStateChangeListener {
            override fun onViewAttachedToWindow(v: View) {
                if (needsRenderOnAttach && !disposed) {
                    needsRenderOnAttach = false
                    render()
                }
            }
            override fun onViewDetachedFromWindow(v: View) {
                layoutGeneration++
                needsRenderOnAttach = true
                clearEmoji(); clearUnavailable(); cancelCompose(); gestures.cancel(); view.cancelRollover(); deleteRepeater.cancel()
            }
        })
    }
    private var shift = false
    private var selecting = false
    private var selectKey: Button? = null
    private var caps = false
    private var symbols = false
    private var moreSymbols = false
    private var toolsOpen = false
    private var editActionsOpen = false
    private var heldCtrl = false
    private var heldAlt = false
    private var armedCtrl = false
    private var armedAlt = false
    private var ctrl: Boolean
        get() = armedCtrl || heldCtrl
        set(value) { armedCtrl = value }
    private var alt: Boolean
        get() = armedAlt || heldAlt
        set(value) { armedAlt = value }
    private var functionKeys = false
    private var ctrlKey: Button? = null
    private var altKey: Button? = null
    private var voiceAllowed = false
    private var emojiAllowed = true
    private var emoji: EmojiPanel? = null
    private val actionKeys = mutableMapOf<EditorAction, Button>()
    private var actionLabel = "Enter"
    private var lastKey = ""
    private var lastTime = 0L
    private val letters = mutableListOf<Button>()
    private var shiftKey: Button? = null
    private var capsKey: Button? = null
    private var toolbarStatus: TextView? = null
    private var unavailableToast: Toast? = null
    private var alternateMode = false
    private var alternateKey: Char? = null
    private var composeChoosingMark = false
    private var composeMark: LatinComposeMark? = null
    private var composeError: String? = null
    private var layoutGeneration = 0

    private fun saveQuickOption(numberRow: Boolean? = null, terminal: Boolean? = null,
        alignment: KeyboardAlignment? = null, letterLayout: LetterLayout? = null) {
        if (privateEditing || disposed) return
        val current = KeyboardOptions.load(context)
        options = current.copy(
            numberRow = numberRow ?: current.numberRow,
            terminal = terminal ?: current.terminal,
            alignment = alignment ?: current.alignment,
            letterLayout = letterLayout ?: current.letterLayout,
        )
        options.save(context)
    }

    private fun cancelForGeometryChange() {
        clearUnavailable()
        cancelCompose()
        gestures.cancel()
        view.cancelRollover()
        view.cancelSelection()
        deleteRepeater.cancel()
        shift = false; selecting = false
        heldCtrl = false; heldAlt = false; armedCtrl = false; armedAlt = false
        lastKey = ""; lastTime = 0
    }

    private fun chooseAlignment(alignment: KeyboardAlignment) {
        if (options.alignment == alignment) return
        cancelForGeometryChange()
        saveQuickOption(alignment = alignment)
        render()
        quickOptionsChanged()
    }

    private fun chooseLetterLayout(letterLayout: LetterLayout) {
        if (options.letterLayout == letterLayout) return
        cancelForGeometryChange()
        caps = false; alternateMode = false; alternateKey = null
        saveQuickOption(letterLayout = letterLayout)
        render()
        quickOptionsChanged()
    }

    @SuppressLint("RtlHardcoded") // Left/right are explicit physical one-hand choices.
    private fun alignmentGravity() = Gravity.TOP or when (options.alignment) {
        KeyboardAlignment.RIGHT -> Gravity.RIGHT
        else -> Gravity.LEFT
    }

    private fun alignedContentWidth(available: Int): Int {
        val minimum = Ui.dp(context, 320)
        val maximum = Ui.dp(context, 360)
        return if (options.alignment == KeyboardAlignment.FULL || available <= minimum) {
            available
        } else {
            ((available.toLong() * 82L) / 100L).toInt()
                .coerceIn(minimum, minOf(maximum, available))
        }
    }

    @SuppressLint("RtlHardcoded") // Left/right are explicit physical one-hand choices.
    private fun applyContentAlignment() {
        val gravity = alignmentGravity()
        val current = content.layoutParams as? FrameLayout.LayoutParams
        if (current?.width == FrameLayout.LayoutParams.WRAP_CONTENT && current.gravity == gravity) return
        content.layoutParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT, gravity)
    }

    fun reset(allowVoice: Boolean, numeric: Boolean, action: String, allowEmoji: Boolean = true) {
        if (disposed) return
        clearEmoji()
        clearUnavailable()
        gestures.cancel()
        view.cancelRollover()
        shift = false; selecting = false; caps = false; symbols = numeric; moreSymbols = false; toolsOpen = false; editActionsOpen = false
        ctrl = false; alt = false; functionKeys = false
        alternateMode = false; alternateKey = null; cancelCompose()
        voiceAllowed = allowVoice && !privateEditing; emojiAllowed = allowEmoji; actionLabel = action
        lastKey = ""; lastTime = 0
        render()
    }
    /** Permanently invalidates even an owned panel that was never attached. */
    fun dispose() {
        if (disposed) return
        disposed = true; layoutGeneration++
        clearEmoji(); cancelForGeometryChange(); view.clearOrdinaryKeys()
        view.modifiers.reset(); content.removeAllViews(); letters.clear(); actionKeys.clear()
        toolbarStatus = null; shiftKey = null; capsKey = null
        ctrlKey = null; altKey = null; selectKey = null
    }
    fun refreshEditorActions() {
        if (!disposed) actionKeys.forEach { (action, button) -> button.isEnabled = actionAvailable(action) }
    }
    private fun clearEmoji() {
        emoji?.clear()
        emoji = null
    }
    private fun showEmoji() {
        if (disposed || !emojiAllowed) return
        cancelForGeometryChange()
        clearEmoji()
        layoutGeneration++
        val generation = layoutGeneration
        toolsOpen = false; editActionsOpen = false; symbols = false; functionKeys = false
        alternateMode = false; alternateKey = null; cancelCompose()
        view.clearOrdinaryKeys()
        content.removeAllViews()
        val picker = EmojiPanel(context, options,
            { value -> generation == layoutGeneration && commit(value) },
            { if (generation == layoutGeneration) render() })
        emoji = picker
        content.addView(picker.view, LinearLayout.LayoutParams(-1, -2))
    }
    private fun shape(color: Int) = GradientDrawable().apply {
        setColor(color); cornerRadius = Ui.dp(context, 9).toFloat()
    }
    private fun key(row: LinearLayout, label: String, description: String = label, weight: Float = 1f,
        utility: Boolean = false, primary: Boolean = false, height: Int = keyHeight, chordable: Boolean = true,
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
                if (disposed || generation != layoutGeneration) return@setOnClickListener
                val now = SystemClock.elapsedRealtime()
                if (!options.repeatGuard || description != lastKey || now - lastTime >= 250) {
                    lastKey = description; lastTime = now
                    if (options.haptics) performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                    clearUnavailable()
                    action()
                }
            }
        }
        row.addView(button, LinearLayout.LayoutParams(0, Ui.dp(context, height), weight))
        if (chordable && description !in listOf("Keyboard tools", "Dictate", "Keyboard settings", "Switch keyboard",
                "Function keys", "Caps lock off", "Accents and alternate characters", "Select text",
                "Number row on", "Number row off", "Terminal controls on", "Terminal controls off"))
            view.modifiers.key(button)
        if (description in listOf("Delete", "Forward delete", "Delete to right")) {
            deleteRepeater.attach(button, options.deleteRepeat && !options.repeatGuard) {
                if (generation == layoutGeneration) {
                    // A one-shot modified delete must not become an unmodified repeat.
                    if (ctrl || alt || shift) deleteRepeater.stop()
                    action()
                }
            }
        }
        return button
    }
    private fun row() = LinearLayout(context).also {
        it.orientation = LinearLayout.HORIZONTAL
        it.isMotionEventSplittingEnabled = false
        it.isBaselineAligned = false
        content.addView(it, LinearLayout.LayoutParams(-1, -2))
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
            view.registerOrdinaryKey(button)
            if (!symbols) {
                button.tag = character; letters.add(button)
                if (character in 'a'..'z') {
                    if (options.secondaryHints) (button as HintedKey).secondaryHint =
                        AlternateCharacters.hint(character, options.letterLayout)
                    val generation = layoutGeneration
                    button.setOnLongClickListener {
                        if (generation != layoutGeneration) false else {
                            openAlternates(character); true
                        }
                    }
                    gestures.attachLetter(button,
                        { if (generation == layoutGeneration) AlternateCharacters.choices(
                            character, shift xor caps, options.letterLayout) else emptyList() },
                        { if (generation == layoutGeneration) AlternateCharacters.hint(
                            character, options.letterLayout) else null },
                        { value ->
                            if (generation == layoutGeneration && type(value)) {
                                shift = false; alternateKey = null; alternateMode = false; updateCase()
                            }
                        })
                }
            }
        }
    }

    private fun openAlternates(character: Char) {
        alternateKey = character; render()
        view.announceForAccessibility("Choose an alternate for ${displayed(character)}, or Cancel")
    }

    private fun alternateRows(character: Char) {
        val choices = if (character == '.') AlternateCharacters.punctuation else AlternateCharacters.choices(
            character, shift xor caps, options.letterLayout)
        val heading = TextView(context).apply {
            text = if (character == '.') "Punctuation" else "Alternates for ${displayed(character)}"; textSize = 16f
            setTextColor(ink); gravity = Gravity.CENTER; minHeight = Ui.dp(context, 40)
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        content.addView(heading)
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

    private fun composeActive() = composeChoosingMark || composeMark != null

    private fun cancelCompose() {
        composeChoosingMark = false
        composeMark = null
        composeError = null
    }

    private fun beginCompose() {
        if (options.terminal || disposed) return
        toolsOpen = false; editActionsOpen = false; alternateMode = false; alternateKey = null
        symbols = false; functionKeys = false; selecting = false
        composeChoosingMark = true; composeMark = null; composeError = null
        render()
        view.announceForAccessibility("Compose: choose a mark, or Cancel")
    }

    private fun updateComposeStatus() {
        toolbarStatus?.apply {
            text = when {
                composeChoosingMark -> "Compose: choose a mark"
                composeError != null -> composeError
                composeMark != null -> "Compose ${composeMark!!.label}: choose a letter"
                else -> ""
            }
            visibility = if (composeActive()) View.VISIBLE else View.GONE
        }
    }

    private fun composeMarkRows() {
        LatinComposeMark.entries.chunked(4).forEach { group ->
            val line = row()
            group.forEach { mark ->
                key(line, "${mark.label} ${mark.symbol}", "${mark.label} compose mark", utility = true,
                    chordable = false) {
                    composeChoosingMark = false; composeMark = mark; composeError = null; render()
                    view.announceForAccessibility("Compose ${mark.label}: choose a letter, or Cancel")
                }
            }
            repeat(4 - group.size) { spacer(line, 1f) }
        }
        key(row(), "Cancel", "Cancel compose", utility = true, chordable = false) {
            cancelCompose(); render()
        }
    }

    private fun composeCharacters(row: LinearLayout, sequence: String) {
        sequence.forEach { character ->
            val button = key(row, displayed(character).toString(), chordable = false) {
                val mark = composeMark ?: return@key
                val value = LatinCompose.compose(mark, character, shift xor caps)
                if (value == null) {
                    composeError = "${mark.label}: combination unavailable"
                    updateComposeStatus()
                    view.announceForAccessibility("Combination unavailable; ${mark.label} is still selected")
                } else if (type(value)) {
                    shift = false; cancelCompose(); render()
                }
            }
            button.tag = character
            letters.add(button)
        }
    }

    private fun composeLetterRows() {
        val layout = options.letterLayout
        composeCharacters(row(), layout.top)
        val home = row()
        val homeEdge = (10 - layout.home.length) / 2f
        spacer(home, homeEdge); composeCharacters(home, layout.home); spacer(home, homeEdge)
        val third = row()
        val bottomEdge = (10 - layout.bottom.length) / 2f
        shiftKey = key(third, "⇧", "Shift off", bottomEdge, utility = true, chordable = false) {
            shift = !shift; updateCase()
        }
        composeCharacters(third, layout.bottom)
        spacer(third, bottomEdge)
        key(row(), "Cancel", "Cancel compose", utility = true, chordable = false) {
            cancelCompose(); shift = false; render()
        }
        updateCase()
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
        clearUnavailable()
        val accepted = if (ctrl || alt) modifiedCommit(value, ctrl, alt) else commit(value)
        releaseModifiers()
        selecting = false
        selectKey?.isSelected = false
        if (!accepted) unavailable()
        return accepted
    }
    private fun clearUnavailable() {
        unavailableToast?.cancel()
        unavailableToast = null
    }
    private fun unavailable() {
        unavailableToast?.cancel()
        unavailableToast = Toast.makeText(context, "Key unavailable", Toast.LENGTH_SHORT).also { it.show() }
        view.announceForAccessibility("This key is not supported in the current field")
    }
    private fun special(code: Int) {
        clearUnavailable()
        val accepted = terminalKey(code, ctrl, alt, shift)
        shift = false; releaseModifiers()
        if (!accepted) unavailable()
    }
    private fun delete() {
        clearUnavailable()
        if (ctrl || alt || (options.terminal && shift)) special(KeyEvent.KEYCODE_DEL) else erase()
    }
    private fun navigate(left: Boolean) {
        clearUnavailable()
        if (selecting || shift || ctrl || alt) {
            val accepted = terminalKey(if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT,
                ctrl, alt, selecting || shift)
            releaseModifiers()
            if (!accepted) unavailable()
        } else move(left)
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
    private fun editingRows() {
        fun actionRow(actions: List<EditorAction>) {
            val line = row()
            actions.forEach { action ->
                key(line, action.label, utility = true, height = 48, chordable = false) {
                    val accepted = editorAction(action)
                    selecting = false; shift = false; releaseModifiers()
                    selectKey?.isSelected = false
                    if (!accepted) unavailable()
                }.also { button -> actionKeys[action] = button; button.isEnabled = actionAvailable(action) }
            }
        }
        actionRow(listOf(EditorAction.UNDO, EditorAction.REDO, EditorAction.SELECT_ALL))
        if (!privateEditing) actionRow(listOf(EditorAction.CUT, EditorAction.COPY, EditorAction.PASTE))
        val arrows = row()
        listOf(Triple("←", "Move cursor left", KeyEvent.KEYCODE_DPAD_LEFT),
            Triple("↓", "Move cursor down", KeyEvent.KEYCODE_DPAD_DOWN),
            Triple("↑", "Move cursor up", KeyEvent.KEYCODE_DPAD_UP),
            Triple("→", "Move cursor right", KeyEvent.KEYCODE_DPAD_RIGHT)).forEach { (label, description, code) ->
            key(arrows, label, description, utility = true, height = 48, chordable = false) {
                if (!terminalKey(code, false, false, selecting)) unavailable()
            }
        }
        val navigation = row()
        selectKey = key(navigation, "Select", "Select text", utility = true, height = 48, chordable = false) {
            selecting = !selecting; selectKey?.isSelected = selecting
        }.apply { isSelected = selecting }
        listOf("Home" to KeyEvent.KEYCODE_MOVE_HOME, "End" to KeyEvent.KEYCODE_MOVE_END).forEach { (label, code) ->
            key(navigation, label, utility = true, height = 48, chordable = false) {
                if (!terminalKey(code, false, false, selecting)) unavailable()
            }
        }
        key(navigation, "ABC", "Return to typing", utility = true, height = 48, chordable = false) {
            editActionsOpen = false; selecting = false; render()
        }
    }
    private fun render() {
        if (disposed) return
        clearEmoji()
        clearUnavailable()
        layoutGeneration++
        gestures.cancel()
        view.cancelRollover()
        view.clearOrdinaryKeys()
        view.cancelSelection()
        deleteRepeater.cancel()
        content.removeAllViews(); letters.clear(); actionKeys.clear(); shiftKey = null; capsKey = null; ctrlKey = null; altKey = null; selectKey = null
        applyContentAlignment()
        val toolbar = row()
        key(toolbar, if (toolsOpen) "Close" else "Tools", "Keyboard tools", 2f, utility = true, height = 48) {
            val opening = !toolsOpen
            cancelCompose(); toolsOpen = opening; editActionsOpen = false; alternateMode = false; alternateKey = null; render()
        }.apply { isSelected = toolsOpen }
        key(toolbar, if (editActionsOpen) "ABC" else "Edit", if (editActionsOpen) "Close edit actions" else "Edit actions",
            2f, utility = true, height = 48, chordable = false) {
            val opening = !editActionsOpen
            cancelCompose(); toolsOpen = false; editActionsOpen = opening; selecting = false
            shift = false; heldCtrl = false; heldAlt = false; releaseModifiers()
            alternateMode = false; alternateKey = null; render()
        }.apply { isSelected = editActionsOpen }
        key(toolbar, "Emoji", if (emojiAllowed) "Emoji" else "Emoji unavailable in raw input",
            2f, utility = true, height = 48, chordable = false) { showEmoji() }
            .apply { isEnabled = emojiAllowed }
        toolbarStatus = TextView(context).apply {
            text = when {
                composeChoosingMark -> "Compose: choose a mark"
                composeError != null -> composeError
                composeMark != null -> "Compose ${composeMark!!.label}: choose a letter"
                alternateKey != null -> "Choose a character"
                alternateMode -> "Choose a letter"
                else -> ""
            }
            textSize = 13f; setTextColor(ink); gravity = Gravity.CENTER
            visibility = if (composeActive() || alternateKey != null || alternateMode) View.VISIBLE else View.GONE
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        }
        content.addView(toolbarStatus, LinearLayout.LayoutParams(-1, -2))
        if (!privateEditing) key(toolbar, "", "Dictate", 2.5f, utility = true, height = 48) {
            dictate()
        }.apply {
            (this as HintedKey).primaryIcon = context.getDrawable(R.drawable.voice_idle)?.mutate()
        }
            .apply { isEnabled = voiceAllowed }
        if (toolsOpen) {
            val quick = row()
          if (!privateEditing) {
            key(quick, "Number row", if (options.numberRow) "Number row on" else "Number row off",
                utility = true, height = 48, chordable = false) {
                saveQuickOption(numberRow = !options.numberRow); render(); quickOptionsChanged()
            }.apply { isSelected = options.numberRow }
            key(quick, "Terminal", if (options.terminal) "Terminal controls on" else "Terminal controls off",
                utility = true, height = 48, chordable = false) {
                val enabled = !options.terminal
                saveQuickOption(terminal = enabled)
                if (!enabled) {
                    heldCtrl = false; heldAlt = false; armedCtrl = false; armedAlt = false
                    functionKeys = false
                }
                render(); quickOptionsChanged()
            }.apply { isSelected = options.terminal }
            openDraft?.let { open ->
                key(quick, "Draft", "Private draft", utility = true, height = 48, chordable = false) { open() }
            }
          }
            key(quick, "Compose", if (options.terminal) "Latin compose unavailable in terminal mode" else "Latin compose",
                utility = true, height = 48, chordable = false) { beginCompose() }
                .apply { isEnabled = !options.terminal }
            val tools = row()
            capsKey = key(tools, "Caps", "Caps lock off", utility = true, height = 48) {
                caps = !caps
                if (alternateKey != null) render() else updateCase()
            }
            key(tools, "←", "Move cursor left", utility = true, height = 48) { navigate(true) }
            key(tools, "→", "Move cursor right", utility = true, height = 48) { navigate(false) }
            key(tools, "Accents", "Accents and alternate characters", utility = true, height = 48) {
                cancelCompose()
                alternateMode = !alternateMode; alternateKey = null
                symbols = false; functionKeys = false; render()
                if (alternateMode) view.announceForAccessibility("Tap a letter for accents, or period for punctuation")
            }.apply { isSelected = alternateMode }
          if (!privateEditing) {
            key(tools, "Settings", "Keyboard settings", utility = true, height = 48) { settings() }
            key(tools, "Switch", "Switch keyboard", utility = true, height = 48) { switchKeyboard() }
            val alignment = row()
            key(alignment, "Full", "Full width layout", utility = true, height = 48, chordable = false) {
                chooseAlignment(KeyboardAlignment.FULL)
            }.apply { isSelected = options.alignment == KeyboardAlignment.FULL }
            key(alignment, "Left", "Left hand layout", utility = true, height = 48, chordable = false) {
                chooseAlignment(KeyboardAlignment.LEFT)
            }.apply { isSelected = options.alignment == KeyboardAlignment.LEFT }
            key(alignment, "Right", "Right hand layout", utility = true, height = 48, chordable = false) {
                chooseAlignment(KeyboardAlignment.RIGHT)
            }.apply { isSelected = options.alignment == KeyboardAlignment.RIGHT }
            val letterLayouts = row()
            LetterLayout.entries.forEach { layout ->
                key(letterLayouts, layout.label, "${layout.label} letter layout", utility = true,
                    height = 48, chordable = false) { chooseLetterLayout(layout) }
                    .apply { isSelected = options.letterLayout == layout }
            }
          }
            val editing = row()
            selectKey = key(editing, "Select", "Select text", utility = true, height = 48) {
                selecting = !selecting; render()
            }.apply { isSelected = selecting }
            key(editing, "Del →", "Delete to right", utility = true, height = 48) { special(KeyEvent.KEYCODE_FORWARD_DEL) }
            key(editing, "Home", "Go to beginning", utility = true, height = 48) { special(KeyEvent.KEYCODE_MOVE_HOME) }
            key(editing, "End", "Go to end", utility = true, height = 48) { special(KeyEvent.KEYCODE_MOVE_END) }
        }
        if (editActionsOpen) { editingRows(); return }
        if (composeChoosingMark) { composeMarkRows(); return }
        if (composeMark != null) { composeLetterRows(); return }
        alternateKey?.let { alternateRows(it); updateCase(); return }
        if (options.terminal) terminalRows()
        if (options.numberRow && !symbols && !functionKeys) characters(row(), "1234567890")
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
            val layout = options.letterLayout
            characters(row(), layout.top)
            val home = row()
            val homeEdge = (10 - layout.home.length) / 2f
            spacer(home, homeEdge); characters(home, layout.home); spacer(home, homeEdge)
            val third = row()
            val bottomEdge = (10 - layout.bottom.length) / 2f
            shiftKey = key(third, "⇧", "Shift off", bottomEdge, utility = true) { shift = !shift; updateCase() }
            characters(third, layout.bottom)
            key(third, "⌫", "Delete", bottomEdge, utility = true) { delete() }
        }
        val bottom = row()
        key(bottom, if (symbols) "ABC" else "?123", "Switch letters and symbols", 1.5f, utility = true) {
            symbols = !symbols; moreSymbols = false; functionKeys = false
            cancelCompose(); alternateMode = false; alternateKey = null; render()
        }
        key(bottom, ",") { type(",") }.also { view.registerOrdinaryKey(it) }
        key(bottom, "space", "Space", 5f) { type(" ") }.also { space ->
            val generation = layoutGeneration
            gestures.attachSpace(space) { left -> if (generation == layoutGeneration) navigate(left) }
            view.bindSelection(shiftKey, space) { left ->
                if (generation == layoutGeneration) {
                    ctrl = false; alt = false; updateCase()
                    if (!terminalKey(if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT,
                            false, false, true)) unavailable()
                }
            }
        }
        key(bottom, ".") { if (alternateMode) openAlternates('.') else type(".") }.also { period ->
            view.registerOrdinaryKey(period)
            val generation = layoutGeneration
            period.setOnLongClickListener {
                if (generation != layoutGeneration) false else { openAlternates('.'); true }
            }
            gestures.attachLetter(period, { AlternateCharacters.punctuation }) { value ->
                if (generation == layoutGeneration) type(value)
            }
        }
        key(bottom, if (actionLabel == "Enter") "↵" else actionLabel, actionLabel, 1.5f, primary = true) {
            if (ctrl || alt || (options.terminal && shift)) special(KeyEvent.KEYCODE_ENTER) else enter()
        }
        updateCase()
    }
    private fun updateCase() {
        view.modifiers.bind(ctrlKey, altKey) { control, alternate ->
            heldCtrl = control; heldAlt = alternate
            updateCase()
        }
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
