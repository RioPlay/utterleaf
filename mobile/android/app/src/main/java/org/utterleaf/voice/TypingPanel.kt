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
    var bottomIcon: android.graphics.drawable.Drawable? = null
    var secondaryHint: String? = null
        set(value) { field = value; invalidate() }
    /** Mockup letter hints sit at the top-left; digit hints at the top-right. */
    var hintAlignRight: Boolean = true
        set(value) { field = value; invalidate() }
    private val hintPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    override fun onDraw(canvas: Canvas) {
        primaryIcon?.let { icon ->
            super.onDraw(canvas)
            val size = minOf(Ui.dp(context, 24), width, height)
            val lift = if (bottomIcon != null) Ui.dp(context, 5) else 0
            val left = (width - size) / 2; val top = (height - size) / 2 - lift
            icon.setBounds(left, top, left + size, top + size)
            icon.setTint(currentTextColor)
            icon.alpha = if (isEnabled) 255 else 90
            icon.draw(canvas)
            bottomIcon?.let { glyph ->
                val small = Ui.dp(context, 11)
                val left2 = (width - small) / 2
                val top2 = height - small - Ui.dp(context, 3)
                glyph.setBounds(left2, top2, left2 + small, top2 + small)
                glyph.setTint(currentTextColor)
                glyph.alpha = if (isEnabled) 150 else 60
                glyph.draw(canvas)
            }
            return
        }
        val hint = secondaryHint
        if (hint != null) {
            hintPaint.color = currentTextColor
            hintPaint.alpha = 170
            hintPaint.textSize = 8 * resources.displayMetrics.scaledDensity
            // At very large label sizes, preserve the primary key's legibility.
            val offset = Ui.dp(context, 3).toFloat()
            val primaryTop = (height - (paint.fontMetrics.descent - paint.fontMetrics.ascent)) / 2f + offset
            if (Ui.dp(context, 3) + hintPaint.fontMetrics.descent - hintPaint.fontMetrics.ascent <= primaryTop - Ui.dp(context, 2)) {
                canvas.save()
                canvas.translate(0f, offset)
                super.onDraw(canvas)
                canvas.restore()
                if (hintAlignRight) {
                    hintPaint.textAlign = Paint.Align.RIGHT
                    canvas.drawText(hint, width - Ui.dp(context, 8).toFloat(),
                        Ui.dp(context, 6).toFloat() - hintPaint.ascent(), hintPaint)
                } else {
                    hintPaint.textAlign = Paint.Align.LEFT
                    canvas.drawText(hint, Ui.dp(context, 8).toFloat(),
                        Ui.dp(context, 6).toFloat() - hintPaint.ascent(), hintPaint)
                }
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
    private val actionAvailable: (EditorAction) -> Boolean = { true },
    private val spaceLabel: String? = null,
    private val rawField: Boolean = false,
    private val backspaceSelection: BackspaceSelection? = null) {
    private val light = options.resolvedLight(context)
    private val surface = Color.parseColor(if (light) "#E8EEEB" else "#171E20")
    private val keyColor = Color.parseColor(if (light) "#FFFFFF" else "#303A3D")
    private val utilityColor = Color.parseColor(if (light) "#D1DFD6" else "#24322D")
    private val ink = Color.parseColor(if (light) "#17251D" else "#F0F5F2")
    private val accent = Color.parseColor(if (light) "#25643D" else "#A2DFB3")
    private val accentInk = Color.parseColor(if (light) "#FFFFFF" else "#10291B")
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
    private val selectableBackspace = backspaceSelection?.let { selection -> object : BackspaceSelection {
        override fun begin(): Boolean = !extraKeysOpen && selection.begin()
        override fun move(left: Boolean): Boolean = !extraKeysOpen && selection.move(left)
        override fun finish(): Boolean = !extraKeysOpen && selection.finish()
        override fun cancel() = selection.cancel()
    } }
    private var availableWidth = 0
    private var disposed = false
    private var needsRenderOnAttach = false
    init {
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
    private var hubOpen = false
    private var extraKeysOpen = false
    private var functionKeysOpen = false
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
    private val shiftKeys = mutableListOf<Button>()
    private var letterShiftKey: Button? = null
    private val arrowRepeaters = mutableListOf<ArrowRepeater>()
    private var capsKey: Button? = null
    private var toolbarStatus: TextView? = null
    private var unavailableToast: Toast? = null
    private var alternateMode = false
    private var alternateKey: Char? = null
    private var composeChoosingMark = false
    private var composeMark: LatinComposeMark? = null
    private var composeError: String? = null
    private var layoutGeneration = 0

    private fun saveQuickOption(numberRow: Boolean? = null, extraKeys: Boolean? = null,
        alignment: KeyboardAlignment? = null, letterLayout: LetterLayout? = null) {
        if (privateEditing || disposed) return
        val current = KeyboardOptions.load(context)
        options = current.copy(
            numberRow = numberRow ?: current.numberRow,
            extraKeys = extraKeys ?: current.extraKeys,
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
        arrowRepeaters.forEach { it.cancel() }
        arrowRepeaters.clear()
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
        shift = false; selecting = false; caps = false; symbols = numeric; moreSymbols = false
        hubOpen = false; extraKeysOpen = false; functionKeysOpen = false
        ctrl = false; alt = false
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
        arrowRepeaters.clear()
        toolbarStatus = null; capsKey = null
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
        hubOpen = false; extraKeysOpen = false; functionKeysOpen = false
        symbols = false
        alternateMode = false; alternateKey = null; cancelCompose()
        view.clearOrdinaryKeys()
        content.removeAllViews()
        val picker = EmojiPanel(context, options,
            { value -> generation == layoutGeneration && commit(value) },
            { if (generation == layoutGeneration) render() })
        emoji = picker
        content.addView(picker.view, LinearLayout.LayoutParams(-1, -2))
    }
    private val border = Color.parseColor(if (light) "#B9CCC1" else "#3D4845")
    private fun shape(color: Int, pillShape: Boolean = false) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = if (pillShape) Ui.dp(context, 23).toFloat() else Ui.dp(context, 8).toFloat()
        if (options.keyBorders) setStroke(Ui.dp(context, 1), border)
    }
    private fun key(row: LinearLayout, label: String, description: String = label, weight: Float = 1f,
        utility: Boolean = false, primary: Boolean = false, height: Int = keyHeight, chordable: Boolean = true,
        widthDp: Int? = null, compact: Boolean = false, labelSizeSp: Int? = null, pill: Boolean = false,
        action: () -> Unit): Button {
        val generation = layoutGeneration
        val button = HintedKey(context).apply {
            text = label; contentDescription = description; isAllCaps = false
            val maximumLabelSize = labelSizeSp ?: if (compact) 13 else if (label.length > 2)
                (if (options.large) 16 else 13) else (if (options.large) 26 else 22)
            textSize = maximumLabelSize.toFloat()
            setSingleLine()
            setHorizontallyScrolling(false)
            setAutoSizeTextTypeUniformWithConfiguration(minOf(if (compact) 10 else 12, maximumLabelSize),
                maximumLabelSize,
                1, TypedValue.COMPLEX_UNIT_SP)
            typeface = Typeface.create("sans-serif", Typeface.NORMAL)
            minWidth = 0; minimumWidth = 0; minHeight = 0; minimumHeight = 0
            setPadding(0, 0, 0, 0); includeFontPadding = false
            gravity = Gravity.CENTER
            val selectedFill = if (compact) utilityColor else accent
            val ordinaryFill = if (compact) surface else if (primary) accent else if (utility) utilityColor else keyColor
            val fill = StateListDrawable().apply {
                addState(intArrayOf(android.R.attr.state_selected), shape(selectedFill, pill))
                addState(intArrayOf(android.R.attr.state_focused), shape(selectedFill, pill))
                addState(intArrayOf(), shape(ordinaryFill, pill))
            }
            val verticalInset = Ui.dp(context, if (compact) 5 else 4)
            background = InsetDrawable(RippleDrawable(ColorStateList.valueOf(0x40808080), fill, shape(Color.WHITE, pill)),
                Ui.dp(context, 3), verticalInset, Ui.dp(context, 3), verticalInset)
            backgroundTintList = null
            stateListAnimator = null
            setTextColor(ColorStateList(arrayOf(intArrayOf(-android.R.attr.state_enabled),
                intArrayOf(android.R.attr.state_selected), intArrayOf(android.R.attr.state_focused), intArrayOf()),
                intArrayOf(Color.parseColor(if (light) "#66766B" else "#97A79E"),
                    if (compact) accent else accentInk, if (compact) accent else accentInk,
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
        row.addView(button, if (widthDp == null) LinearLayout.LayoutParams(0, Ui.dp(context, height), weight)
            else LinearLayout.LayoutParams(Ui.dp(context, widthDp), Ui.dp(context, height)))
        if (chordable && description !in listOf("Keyboard tools and settings", "Dictate", "Keyboard settings",
                "Switch keyboard", "Function keys", "Hide function keys", "Caps lock off", "Caps lock on",
                "Accents and alternate characters", "Select all text", "Select text", "Number row on",
                "Number row off", "Extra keys on", "Extra keys off", "Latin compose", "Emoji", "Private draft",
                "Extra keys", "Undo", "Redo", "Copy", "Cut", "Paste", "Switch letters and symbols"))
            view.modifiers.key(button)
        if (description in listOf("Delete", "Forward delete", "Delete to right")) {
            deleteRepeater.attach(button, options.deleteRepeat && !options.repeatGuard,
                if (description == "Delete") selectableBackspace else null,
                selectionUnavailable = { if (generation == layoutGeneration) {
                    clearUnavailable(); unavailable()
                } }, erase = {
                if (generation == layoutGeneration) {
                    // Modified delete is one unit per press while Ctrl/Alt/Shift are down.
                    if (ctrl || alt || shift) deleteRepeater.stop()
                    action()
                }
            })
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
    /**
     * Shared post-commit shift handling: sentence enders arm auto-capitalization
     * once; ordinary characters consume an armed shift.
     */
    private fun afterCommit(value: String) {
        if (value == "." || value == "!" || value == "?" || value == "\n") {
            if (options.autoCapitalize && !caps && !shift) {
                shift = true
                view.announceForAccessibility("Capitalization armed")
            } else if (!caps) {
                shift = false
            }
        } else if (shift && !caps) {
            shift = false
        }
        updateCase()
    }
    private fun characters(row: LinearLayout, sequence: String) {
        sequence.forEach { character ->
            val button = key(row, character.toString()) {
                if (alternateMode && character in 'a'..'z') {
                    openAlternates(character)
                } else {
                    val value = displayed(character)
                    if (type(value.toString())) afterCommit(value.toString())
                }
            }
            view.registerOrdinaryKey(button)
            if (!symbols) {
                button.tag = character; letters.add(button)
                if (character in '0'..'9' && options.secondaryHints) {
                    (button as HintedKey).apply {
                        secondaryHint = "!@#$%^&*()"["1234567890".indexOf(character)].toString()
                        hintAlignRight = true
                    }
                }
                if (character in 'a'..'z') {
                    if (options.secondaryHints) (button as HintedKey).apply {
                        secondaryHint = AlternateCharacters.hint(character, options.letterLayout,
                            numberRowShown = options.numberRow)
                        hintAlignRight = false
                    }
                    val generation = layoutGeneration
                    button.setOnLongClickListener {
                        if (generation != layoutGeneration) false else {
                            openAlternates(character); true
                        }
                    }
                    gestures.attachLetter(button,
                        { if (generation == layoutGeneration) AlternateCharacters.choices(
                            character, shift xor caps, options.letterLayout, options.numberRow) else emptyList() },
                        { if (generation == layoutGeneration) AlternateCharacters.hint(
                            character, options.letterLayout, options.numberRow) else null },
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
                        afterCommit(value)
                        alternateKey = null; alternateMode = false; render()
                    }
                }
            }
            repeat(5 - group.size) { spacer(line, 1f) }
        }
        val controls = row()
        if (character != '.') capsKey = key(controls, "Caps lock", if (caps) "Caps lock on" else "Caps lock off",
            utility = true, chordable = false) { caps = !caps; render() }.apply { isSelected = caps }
        key(controls, "Cancel", "Cancel alternate characters", utility = true) {
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
        if (disposed) return
        if (rawField) {
            clearUnavailable(); unavailable()
            return
        }
        hubOpen = false; extraKeysOpen = false; functionKeysOpen = false
        alternateMode = false; alternateKey = null
        symbols = false; selecting = false
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
                    afterCommit(value)
                    cancelCompose(); render()
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
        val composeShift = key(third, "⇧", "Shift off", bottomEdge, utility = true, chordable = false) { tapShift() }
        composeShift.tag = "⇧"
        shiftKeys.add(composeShift)
        letterShiftKey = composeShift
        attachCapsLock(composeShift)
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
    private fun type(value: String): Boolean {
        clearUnavailable()
        val accepted = if (ctrl || alt) modifiedCommit(value, ctrl, alt) else commit(value)
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
        if (!accepted) unavailable()
    }
    private fun delete() {
        clearUnavailable()
        if (ctrl || alt || shift) special(KeyEvent.KEYCODE_DEL) else erase()
    }
    private fun navigate(left: Boolean) {
        clearUnavailable()
        if (selecting || shift || ctrl || alt) {
            val accepted = terminalKey(if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT,
                ctrl, alt, selecting || shift)
            if (!accepted) unavailable()
        } else move(left)
    }

    /** Select the word immediately before the caret using the editor's native word movement. */
    private fun selectNeighboringWord() {
        clearUnavailable()
        val accepted = terminalKey(KeyEvent.KEYCODE_DPAD_LEFT, true, false, true)
        if (!accepted) unavailable() else view.announceForAccessibility("Selected neighboring word")
    }

    private fun returnToTyping() {
        cancelForGeometryChange()
        hubOpen = false
        symbols = false; moreSymbols = false; alternateMode = false; alternateKey = null
        cancelCompose()
        render()
    }

    private fun openHub() {
        cancelForGeometryChange()
        hubOpen = true
        extraKeysOpen = false; functionKeysOpen = false
        alternateMode = false; alternateKey = null; cancelCompose()
        render()
        view.announceForAccessibility(if (privateEditing) "Keyboard tools" else "Keyboard tools and settings")
    }

    private fun toggleNumberRow() {
        cancelForGeometryChange()
        saveQuickOption(numberRow = !options.numberRow)
        render(); quickOptionsChanged()
    }

    private fun toggleExtraKeysPanel() {
        cancelForGeometryChange()
        extraKeysOpen = !extraKeysOpen
        if (!extraKeysOpen) functionKeysOpen = false
        render()
        view.announceForAccessibility(if (extraKeysOpen) "Extra keys open" else "Extra keys closed")
    }

    private fun toggleExtraKeysPreference() {
        cancelForGeometryChange()
        saveQuickOption(extraKeys = !options.extraKeys)
        if (!options.extraKeys) {
            extraKeysOpen = false; functionKeysOpen = false
        }
        render(); quickOptionsChanged()
    }

    private fun toolbarKey(row: LinearLayout, label: String, description: String, widthDp: Int = 62,
        selected: Boolean = false, enabled: Boolean = true, action: () -> Unit): Button =
        key(row, label, description, utility = true, height = 48, chordable = false,
            widthDp = widthDp, compact = true, action = action).apply {
            setPadding(Ui.dp(context, 8), 0, Ui.dp(context, 8), 0)
            isSelected = selected; isEnabled = enabled
        }

    private fun toolbarIcon(row: LinearLayout, icon: Int, description: String, weight: Float = 1f,
        primary: Boolean = false, pill: Boolean = false, enabled: Boolean = true,
        action: () -> Unit): Button =
        key(row, "", description, weight = weight, utility = !primary, primary = primary, height = 46,
            chordable = false, compact = true, pill = pill, action = action).apply {
            (this as HintedKey).primaryIcon = context.getDrawable(icon)?.mutate()
            isEnabled = enabled
        }

    private fun editorToolbarAction(row: LinearLayout, action: EditorAction, icon: Int,
        selectAllOnLongPress: Boolean = false) {
        val generation = layoutGeneration
        val button = toolbarIcon(row, icon, action.label) {
            val accepted = editorAction(action)
            selecting = false
            selectKey?.isSelected = false
            if (android.os.Build.VERSION.SDK_INT >= 30) selectKey?.stateDescription = "Off"
            if (!accepted) unavailable()
        }
        actionKeys[action] = button
        button.isEnabled = actionAvailable(action)
        if (selectAllOnLongPress) button.setOnLongClickListener {
            if (disposed || generation != layoutGeneration) false else {
                val accepted = editorAction(EditorAction.SELECT_ALL)
                selecting = false
                selectKey?.isSelected = false
                if (!accepted) unavailable() else view.announceForAccessibility("Selected all text")
                true
            }
        }
    }

    private fun normalToolbar() {
        val toolbar = row()
        if (privateEditing) {
            // A draft has no host exits: local history, local emoji and the panel.
            editorToolbarAction(toolbar, EditorAction.UNDO, R.drawable.ic_undo)
            editorToolbarAction(toolbar, EditorAction.REDO, R.drawable.ic_redo)
            toolbarIcon(toolbar, R.drawable.ic_emoji, "Emoji", enabled = emojiAllowed) { showEmoji() }
            spacer(toolbar, 1f)
            if (options.extraKeys) {
                toolbarIcon(toolbar, if (extraKeysOpen) R.drawable.ic_expand_close else R.drawable.ic_expand_open,
                    "Extra keys", weight = 0.9f) { toggleExtraKeysPanel() }
            } else spacer(toolbar, 1f)
            toolbarStatus = null
            return
        }
        editorToolbarAction(toolbar, EditorAction.UNDO, R.drawable.ic_undo)
        editorToolbarAction(toolbar, EditorAction.REDO, R.drawable.ic_redo)
        editorToolbarAction(toolbar, EditorAction.COPY, R.drawable.ic_copy, selectAllOnLongPress = true)
        editorToolbarAction(toolbar, EditorAction.CUT, R.drawable.ic_cut)
        editorToolbarAction(toolbar, EditorAction.PASTE, R.drawable.ic_paste)
        spacer(toolbar, 1.2f)
        if (openDraft != null) {
            toolbarIcon(toolbar, R.drawable.ic_draft, "Private draft") { openDraft?.invoke() }
        } else spacer(toolbar, 1f)
        toolbarIcon(toolbar, R.drawable.voice_idle, "Dictate", weight = 1.1f, primary = true, pill = true,
            enabled = voiceAllowed) { dictate() }
        if (options.extraKeys) {
            toolbarIcon(toolbar, if (extraKeysOpen) R.drawable.ic_expand_close else R.drawable.ic_expand_open,
                "Extra keys", weight = 0.9f) { toggleExtraKeysPanel() }
        } else spacer(toolbar, 1f)
        toolbarStatus = null
    }

    private fun layerHeader(title: String, exitDescription: String = "Return to typing",
        exit: () -> Unit = { returnToTyping() }) {
        val header = row()
        toolbarKey(header, "ABC", exitDescription, 58, action = exit)
        toolbarStatus = TextView(context).apply {
            text = title; textSize = 14f; setTextColor(ink); gravity = Gravity.CENTER_VERTICAL
            setPadding(Ui.dp(context, 10), 0, Ui.dp(context, 8), 0)
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        }
        header.addView(toolbarStatus, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 1f))
    }

    private fun hubRows() {
        val actions = row()
        if (!privateEditing) {
            key(actions, "Settings", "Keyboard settings", utility = true, height = 48, chordable = false) { settings() }
            key(actions, "Switch", "Switch keyboard", utility = true, height = 48, chordable = false) { switchKeyboard() }
        } else {
            // Keep the hub height stable while omitting all host exits in a draft.
            spacer(actions, 2f)
        }
        capsKey = key(actions, "Caps", if (caps) "Caps lock on" else "Caps lock off",
            utility = true, height = 48, chordable = false) { caps = !caps; returnToTyping() }.apply { isSelected = caps }
        val text = row()
        key(text, "Accents", "Accents and alternate characters", utility = true, height = 48, chordable = false) {
            cancelForGeometryChange(); cancelCompose(); hubOpen = false
            alternateMode = true; alternateKey = null; symbols = false
            render()
            view.announceForAccessibility("Tap a letter for accents, or period for punctuation")
        }
        key(text, "Compose", if (rawField) "Latin compose unavailable in raw input" else "Latin compose",
            utility = true, height = 48, chordable = false) { beginCompose() }.apply { isEnabled = !rawField }
        val generation = layoutGeneration
        selectKey = key(text, "Select all", "Select all text", utility = true, height = 48, chordable = false) {
            val accepted = editorAction(EditorAction.SELECT_ALL)
            selecting = false
            selectKey?.isSelected = false
            if (!accepted) unavailable()
        }.also { button ->
            button.setOnLongClickListener {
                if (disposed || generation != layoutGeneration) false else {
                    selectNeighboringWord(); true
                }
            }
        }
        if (privateEditing) {
            // Keep the layer stable while host preferences stay out of a draft.
            repeat(3) { row().minimumHeight = Ui.dp(context, 48) }
            return
        }
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
        val layouts = row()
        LetterLayout.entries.forEach { layout ->
            key(layouts, layout.label, "${layout.label} letter layout", utility = true, height = 48, chordable = false) {
                chooseLetterLayout(layout)
            }.apply { isSelected = options.letterLayout == layout }
        }
        val modes = row()
        key(modes, "123 row", if (options.numberRow) "Number row on" else "Number row off",
            utility = true, height = 48, chordable = false) { toggleNumberRow() }
            .apply { isSelected = options.numberRow }
        key(modes, "Extra keys", if (options.extraKeys) "Extra keys on" else "Extra keys off",
            utility = true, height = 48, chordable = false) { toggleExtraKeysPreference() }
            .apply { isSelected = options.extraKeys }
    }

    /** The mockup's fold-out panel: extra controls above the toolbar, letters stay visible. */
    private fun extraKeyRows() {
        if (functionKeysOpen) {
            for (start in listOf(1, 7)) {
                val functions = row()
                for (number in start until start + 6) {
                    key(functions, "F$number", utility = true, height = 44, labelSizeSp = 16) {
                        special(KeyEvent.KEYCODE_F1 + number - 1)
                    }
                }
            }
        }
        val modifiers = row()
        if (functionKeysOpen) {
            key(modifiers, "Hide F", "Hide function keys", utility = true, height = 44, labelSizeSp = 13,
                chordable = false) { functionKeysOpen = false; render() }
        } else {
            key(modifiers, "Fn", "Function keys", utility = true, height = 44, labelSizeSp = 16,
                chordable = false) { functionKeysOpen = true; render() }
        }
        key(modifiers, "Esc", "Escape", utility = true, height = 44, labelSizeSp = 16) { special(KeyEvent.KEYCODE_ESCAPE) }
        key(modifiers, "Tab", utility = true, height = 44, labelSizeSp = 16) { special(KeyEvent.KEYCODE_TAB) }
        ctrlKey = key(modifiers, "Ctrl", "Control off", utility = true, height = 44, labelSizeSp = 16) {
            ctrl = !ctrl; updateCase()
        }
        altKey = key(modifiers, "Alt", "Alt off", utility = true, height = 44, labelSizeSp = 16) {
            alt = !alt; updateCase()
        }
        shiftKeys.add(key(modifiers, "Shift", if (shift) "Shift on" else "Shift off", utility = true,
            height = 44, labelSizeSp = 14, chordable = false) { tapShift() }
            .apply {
                tag = "Shift"
                attachCapsLock(this)
            })
        val navigation = row()
        listOf(
            Triple("Home", "Home", KeyEvent.KEYCODE_MOVE_HOME),
            Triple("End", "End", KeyEvent.KEYCODE_MOVE_END),
            Triple("Ins", "Insert", KeyEvent.KEYCODE_INSERT),
            Triple("Del", "Forward delete", KeyEvent.KEYCODE_FORWARD_DEL),
            Triple("PgUp", "Page up", KeyEvent.KEYCODE_PAGE_UP),
            Triple("PgDn", "Page down", KeyEvent.KEYCODE_PAGE_DOWN)).forEach { (label, description, code) ->
            key(navigation, label, description, utility = true, height = 44, labelSizeSp = 14) { special(code) }
        }
        val arrows = row()
        listOf(Triple("←", "Left arrow", KeyEvent.KEYCODE_DPAD_LEFT),
            Triple("↓", "Down arrow", KeyEvent.KEYCODE_DPAD_DOWN),
            Triple("↑", "Up arrow", KeyEvent.KEYCODE_DPAD_UP),
            Triple("→", "Right arrow", KeyEvent.KEYCODE_DPAD_RIGHT)).forEach { (label, description, code) ->
            val generation = layoutGeneration
            val button = key(arrows, label, description, utility = true, height = 44, compact = true,
                labelSizeSp = 20) { special(code) }
            if (options.arrowRepeat) arrowRepeaters.add(ArrowRepeater(button) {
                if (generation == layoutGeneration && !disposed) special(code)
            })
        }
    }
    /** Shift tap toggles case; a long press arms caps lock as the visible alternative. */
    private fun tapShift() {
        if (caps) { caps = false; shift = false } else shift = !shift
        updateCase()
    }
    private fun attachCapsLock(button: Button) {
        button.setOnLongClickListener {
            if (disposed) false else {
                caps = !caps
                updateCase()
                view.announceForAccessibility(if (caps) "Caps lock on" else "Caps lock off")
                true
            }
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
        arrowRepeaters.forEach { it.cancel() }
        arrowRepeaters.clear()
        content.removeAllViews(); letters.clear(); actionKeys.clear()
        shiftKeys.clear(); letterShiftKey = null; capsKey = null; ctrlKey = null; altKey = null; selectKey = null
        applyContentAlignment()
        when {
            hubOpen -> layerHeader("All tools", "Close tools and settings")
            composeChoosingMark -> layerHeader("Compose: choose a mark", "Return to typing") {
                cancelForGeometryChange(); cancelCompose(); render()
            }
            composeMark != null -> layerHeader("Compose ${composeMark!!.label}: choose a letter", "Return to typing") {
                cancelForGeometryChange(); cancelCompose(); render()
            }
            alternateKey != null -> layerHeader("Choose a character", "Return to typing") {
                cancelForGeometryChange(); alternateKey = null; alternateMode = false; render()
            }
            alternateMode -> layerHeader("Choose a letter", "Close alternate characters") {
                cancelForGeometryChange(); alternateMode = false; alternateKey = null; render()
            }
            else -> {
                if (extraKeysOpen) extraKeyRows()
                normalToolbar()
            }
        }
        if (hubOpen) { hubRows(); updateCase(); return }
        if (composeChoosingMark) { composeMarkRows(); updateCase(); return }
        if (composeMark != null) { composeLetterRows(); updateCase(); return }
        alternateKey?.let { alternateRows(it); updateCase(); return }
        if (options.numberRow && !symbols) characters(row(), "1234567890")
        if (symbols) {
            characters(row(), if (moreSymbols) "`~!@#$%^&*" else "1234567890")
            val middle = row()
            characters(middle, if (moreSymbols) "()-_=+[]{}" else "@#$%&-+()/")
            val third = row()
            key(third, if (moreSymbols) "?123" else "=\\<",
                if (moreSymbols) "More numbers and symbols" else "More symbols", 1.5f, utility = true) {
                moreSymbols = !moreSymbols; render()
            }
            characters(third, if (moreSymbols) "\\|;:\"',<>./?±×÷§©®" else "*\"':;!?_")
            key(third, "⌫", "Delete", 1.5f, utility = true) { delete() }
        } else {
            val layout = options.letterLayout
            characters(row(), layout.top)
            val home = row()
            val homeEdge = (10 - layout.home.length) / 2f
            spacer(home, homeEdge); characters(home, layout.home); spacer(home, homeEdge)
            val third = row()
            val bottomEdge = (10 - layout.bottom.length) / 2f
            val shiftButton = key(third, "⇧", "Shift off", bottomEdge, utility = true) { tapShift() }
            shiftButton.tag = "⇧"
            shiftKeys.add(shiftButton)
            letterShiftKey = shiftButton
            attachCapsLock(shiftButton)
            characters(third, layout.bottom)
            key(third, "⌫", "Delete", bottomEdge, utility = true) { delete() }
        }
        renderBottomRow()
        updateCase()
    }

    /** Mockup bottom row: ?123, emoji/settings, labeled space, period, Enter pill. */
    private fun renderBottomRow() {
        val bottom = row()
        key(bottom, if (symbols) "ABC" else "?123", "Switch letters and symbols", 1.5f, utility = true) {
            symbols = !symbols; moreSymbols = false
            extraKeysOpen = false; functionKeysOpen = false
            cancelCompose(); alternateMode = false; alternateKey = null; render()
        }
        if (privateEditing) {
            key(bottom, "Tools", "Keyboard tools", 1.5f, utility = true) { openHub() }
        } else {
            val emojiKey = key(bottom, "", "Emoji", 1.5f, utility = true) { showEmoji() }.apply { isEnabled = emojiAllowed }
            (emojiKey as HintedKey).apply {
                primaryIcon = context.getDrawable(R.drawable.ic_emoji)?.mutate()
                bottomIcon = context.getDrawable(R.drawable.ic_gear)?.mutate()
            }
            val emojiGeneration = layoutGeneration
            emojiKey.setOnLongClickListener {
                if (disposed || emojiGeneration != layoutGeneration || !emojiAllowed) false
                else { openHub(); true }
            }
        }
        key(bottom, spaceLabel ?: "", "Space", 5f, labelSizeSp = 14) { type(" ") }.also { space ->
            val generation = layoutGeneration
            gestures.attachSpace(space) { left -> if (generation == layoutGeneration) navigate(left) }
            view.bindSelection(letterShiftKey, space) { left ->
                if (generation == layoutGeneration) {
                    ctrl = false; alt = false; updateCase()
                    if (!terminalKey(if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT,
                            false, false, true)) unavailable()
                }
            }
        }
        key(bottom, ".") { if (alternateMode) openAlternates('.') else if (type(".")) afterCommit(".") }.also { period ->
            view.registerOrdinaryKey(period)
            val generation = layoutGeneration
            period.setOnLongClickListener {
                if (generation != layoutGeneration) false else { openAlternates('.'); true }
            }
            gestures.attachLetter(period, { AlternateCharacters.punctuation }) { value ->
                if (generation == layoutGeneration) type(value)
            }
        }
        key(bottom, if (actionLabel == "Enter") "↵" else actionLabel, actionLabel, 1.5f, primary = true, pill = true) {
            if (ctrl || alt) special(KeyEvent.KEYCODE_ENTER)
            else {
                if (options.autoCapitalize && actionLabel == "Enter" && !caps) {
                    shift = true
                    view.announceForAccessibility("Capitalization armed")
                }
                enter()
            }
            updateCase()
        }
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
        shiftKeys.forEach { button ->
            button.isSelected = shift || caps
            button.contentDescription = if (shift || caps) "Shift on" else "Shift off"
            button.text = if (button.tag == "Shift") "Shift" else if (caps) "⇪" else "⇧"
        }
        capsKey?.apply { isSelected = caps; contentDescription = if (caps) "Caps lock on" else "Caps lock off" }
        ctrlKey?.apply { isSelected = ctrl; contentDescription = if (ctrl) "Control on" else "Control off" }
        altKey?.apply { isSelected = alt; contentDescription = if (alt) "Alt on" else "Alt off" }
    }
}
