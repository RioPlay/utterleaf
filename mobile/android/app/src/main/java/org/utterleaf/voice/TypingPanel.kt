package org.utterleaf.voice

import android.annotation.SuppressLint
import android.content.Context
import android.content.res.Configuration
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
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

/** Secondary hints are visual; the button keeps its primary spoken key label. */
internal class HintedKey(context: Context) : Button(context) {
    var primaryIcon: android.graphics.drawable.Drawable? = null
    var primaryIconSizeDp: Int = 24
    var tintPrimaryIcon: Boolean = true
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
            val size = minOf(Ui.dp(context, primaryIconSizeDp), width, height)
            val lift = if (bottomIcon != null) Ui.dp(context, 5) else 0
            val left = (width - size) / 2; val top = (height - size) / 2 - lift
            icon.setBounds(left, top, left + size, top + size)
            if (tintPrimaryIcon) icon.setTint(currentTextColor) else icon.clearColorFilter()
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
    private val openPasswordManager: (() -> Boolean)? = null,
    private val suggest: (() -> SuggestionEngine.SuggestionState)? = null,
    private val completeWord: ((composing: String, candidate: String) -> Boolean)? = null,
    private val requestSuggestions: (() -> Unit)? = null,
    private val backspaceSelection: BackspaceSelection? = null,
    /** Settings previews stage changes; ordinary IME panels still save immediately. */
    private val stageOptions: ((KeyboardOptions) -> Unit)? = null,
    /** Immutable host policy, distinct from the user's local private-draft editor. */
    private val sensitiveField: Boolean = false) {
    private val light = options.resolvedLight(context)
    private val palette = Ui.palette(context, options)
    private val surface = palette.background
    private val keyColor = palette.key
    private val utilityColor = palette.utility
    private val ink = palette.ink
    private val accent = palette.accent
    private val accentInk = palette.accentInk
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
    // Keep the swipe recognizer so a refused gesture cannot become a Delete tap.
    // The sensitive wrapper never calls the host's selection/context callbacks.
    private val selectableBackspace = if (sensitiveField) object : BackspaceSelection {
        override fun begin() = false
        override fun move(left: Boolean) = false
        override fun finish() = false
        override fun cancel() = Unit
    } else backspaceSelection?.let { selection -> object : BackspaceSelection {
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
                resetTransientState()
            }
        })
    }
    private var shift = false
    private var selecting = false
    private var caps = false
    private var baseNumeric = false
    private var symbols = false
    private var moreSymbols = false
    private var hubOpen = false
    private var editOpen = false
    private var extraKeysOpen = false
    private enum class ExtraKeyGroup { ACCESSORY, FUNCTIONS }
    private var extraKeyGroup = ExtraKeyGroup.ACCESSORY
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
    private var suggestionRow: LinearLayout? = null
    private val suggestionChips = mutableListOf<Button>()
    private var suggestionEmpty: TextView? = null
    private var renderedSuggestions = SuggestionEngine.SuggestionState.EMPTY

    /** Refreshes the cache-backed strip without reading the host editor. */
    fun refreshSuggestions() {
        if (!disposed) refreshSuggestionsRow(request = false)
    }

    private fun saveQuickOption(numberRow: Boolean? = null, extraKeys: Boolean? = null,
        alignment: KeyboardAlignment? = null, letterLayout: LetterLayout? = null,
        splitLandscape: Boolean? = null) {
        if (privateEditing || sensitiveField || disposed) return
        val current = if (stageOptions == null) KeyboardOptions.load(context) else options
        options = current.copy(
            numberRow = numberRow ?: current.numberRow,
            extraKeys = extraKeys ?: current.extraKeys,
            alignment = alignment ?: current.alignment,
            letterLayout = letterLayout ?: current.letterLayout,
            splitLandscape = splitLandscape ?: current.splitLandscape,
        )
        if (stageOptions == null) options.save(context) else stageOptions.invoke(options)
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
        if (options.alignment == alignment && !(options.splitLandscape && alignment != KeyboardAlignment.FULL)) return
        cancelForGeometryChange()
        saveQuickOption(alignment = alignment,
            splitLandscape = options.splitLandscape && alignment == KeyboardAlignment.FULL)
        render()
        quickOptionsChanged()
    }

    private fun chooseSplitLandscape() {
        cancelForGeometryChange()
        saveQuickOption(alignment = KeyboardAlignment.FULL, splitLandscape = !options.splitLandscape)
        render()
        quickOptionsChanged()
    }

    private fun splitLandscape() = options.splitLandscape &&
        context.resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE

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
        KeyboardAlignment.RIGHT -> if (splitLandscape()) Gravity.LEFT else Gravity.RIGHT
        else -> Gravity.LEFT
    }

    private fun alignedContentWidth(available: Int): Int {
        val minimum = Ui.dp(context, 320)
        val maximum = Ui.dp(context, 360)
        return if (splitLandscape() || options.alignment == KeyboardAlignment.FULL || available <= minimum) {
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
        baseNumeric = numeric
        resetTransientState()
        voiceAllowed = allowVoice && !privateEditing && !sensitiveField
        emojiAllowed = allowEmoji && !sensitiveField; actionLabel = action
        render()
    }
    /** A view boundary resets modes, never preferences or an owning editor's text. */
    private fun resetTransientState() {
        clearEmoji()
        cancelForGeometryChange()
        caps = false; symbols = baseNumeric; moreSymbols = false
        hubOpen = false; editOpen = false; extraKeysOpen = false; extraKeyGroup = ExtraKeyGroup.ACCESSORY
        alternateMode = false; alternateKey = null
        renderedSuggestions = SuggestionEngine.SuggestionState.EMPTY
    }
    /** Permanently invalidates even an owned panel that was never attached. */
    fun dispose() {
        if (disposed) return
        disposed = true; layoutGeneration++
        clearEmoji(); cancelForGeometryChange(); view.clearOrdinaryKeys()
        view.modifiers.reset(); content.removeAllViews(); letters.clear(); actionKeys.clear()
        caps = false; hubOpen = false; editOpen = false; extraKeysOpen = false
        alternateMode = false; alternateKey = null
        renderedSuggestions = SuggestionEngine.SuggestionState.EMPTY
        suggestionRow = null; suggestionChips.clear(); suggestionEmpty = null
        arrowRepeaters.clear()
        toolbarStatus = null; capsKey = null
        ctrlKey = null; altKey = null
    }
    fun refreshEditorActions() {
        if (!disposed) actionKeys.forEach { (action, button) -> button.isEnabled = allowsEditorAction(action) }
    }
    private fun clearEmoji() {
        emoji?.clear()
        emoji = null
    }
    private fun showEmoji() {
        if (disposed || sensitiveField || !emojiAllowed) return
        cancelForGeometryChange()
        clearEmoji()
        layoutGeneration++
        val generation = layoutGeneration
        hubOpen = false; editOpen = false; extraKeysOpen = false; extraKeyGroup = ExtraKeyGroup.ACCESSORY
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
            val selectedFill = if (compact && !primary) utilityColor else accent
            val ordinaryFill = if (primary) accent else if (compact) surface else if (utility) utilityColor else keyColor
            val fill = StateListDrawable().apply {
                if (primary) addState(intArrayOf(-android.R.attr.state_enabled), shape(surface, pill))
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
                    if (compact && !primary) accent else accentInk, if (compact && !primary) accent else accentInk,
                    if (primary) accentInk else ink)))
            isSoundEffectsEnabled = false
            isHapticFeedbackEnabled = options.haptics
            setOnClickListener {
                if (disposed || generation != layoutGeneration) return@setOnClickListener
                val now = SystemClock.elapsedRealtime()
                if (sensitiveField || !options.repeatGuard || description != lastKey || now - lastTime >= 250) {
                    // A character's accessibility label is typed content. Never keep
                    // a last-key cache for passwords, even when repeat guard is saved.
                    if (!sensitiveField) { lastKey = description; lastTime = now }
                    if (options.haptics) performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                    clearUnavailable()
                    action()
                }
            }
        }
        row.addView(button, if (widthDp == null) LinearLayout.LayoutParams(0, Ui.dp(context, height), weight)
            else LinearLayout.LayoutParams(Ui.dp(context, widthDp), Ui.dp(context, height)))
        if (chordable && description !in listOf("Keyboard tools and settings", "Dictate", "Keyboard settings",
                "Switch keyboard", "Function keys", "Caps lock off", "Caps lock on",
                "Accents and alternate characters", "Select all text", "Select text", "Number row on",
                "Number row off", "Latin compose", "Emoji", "Private draft",
                "Extra keys", "Undo", "Redo", "Copy", "Cut", "Paste", "Switch letters and symbols",
                "Open password manager"))
            view.modifiers.key(button)
        if (description in listOf("Delete", "Forward delete", "Delete to right")) {
            deleteRepeater.attach(button, options.deleteRepeat && !options.repeatGuard,
                if (description == "Delete") selectableBackspace else null,
                selectionUnavailable = { if (generation == layoutGeneration) {
                    clearUnavailable(); unavailable()
                } }, erase = {
                if (generation == layoutGeneration) {
                    // Explicit modified delete stays one unit per press. Letter-case
                    // Shift (including auto-capitalization) must not stop Backspace.
                    if (usesModifiedDelete()) deleteRepeater.stop()
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
            if (!sensitiveField && options.autoCapitalize && !caps && !shift) {
                shift = true
                view.announceForAccessibility("Capitalization armed")
            } else if (!caps) {
                shift = false
            }
        } else if (shift && !caps) {
            shift = false
        }
        updateCase()
        refreshSuggestionsRow()
    }

    /** The mockup's suggestion strip: stable height, completions of the current word. */
    private fun suggestionRow() {
        if (sensitiveField) return
        val row = row()
        row.minimumHeight = Ui.dp(context, 40)
        suggestionRow = row
        refreshSuggestionsRow()
    }

    private fun refreshSuggestionsRow(request: Boolean = true) {
        if (disposed || sensitiveField) return
        val row = suggestionRow ?: return
        val provider = suggest ?: return
        val state = runCatching { provider.invoke() }.getOrNull() ?: SuggestionEngine.SuggestionState.EMPTY
        renderedSuggestions = state
        if (suggestionChips.isEmpty()) {
            repeat(3) { index ->
                suggestionChips += key(row, "", "", height = 40, compact = true,
                    chordable = false, labelSizeSp = 16) {
                    renderedSuggestions.candidates.getOrNull(index)?.let { candidate ->
                        completeChip(renderedSuggestions.composing, candidate)
                    }
                }
            }
        }
        if (state.candidates.isEmpty()) {
            suggestionChips.forEach { chip ->
                chip.visibility = View.GONE
                chip.isEnabled = false
            }
            val empty = suggestionEmpty ?: TextView(context).also { created ->
                created.textSize = 13f
                created.setTextColor(ink)
                created.gravity = Gravity.CENTER
                created.includeFontPadding = false
                suggestionEmpty = created
                row.addView(created, 0, LinearLayout.LayoutParams(0, Ui.dp(context, 40), 3f))
            }
            empty.text = if (state.composing.isEmpty()) "Type a word" else "No completions"
            empty.contentDescription = empty.text
            empty.visibility = View.VISIBLE
        } else {
            suggestionEmpty?.visibility = View.GONE
            suggestionChips.forEachIndexed { index, chip ->
                val candidate = state.candidates.getOrNull(index)
                chip.text = candidate ?: ""
                chip.contentDescription = candidate?.let { "Complete with $it" } ?: ""
                chip.isEnabled = candidate != null
                // Keep every chip's one-third slot stable as candidates vary.
                chip.visibility = if (candidate == null) View.INVISIBLE else View.VISIBLE
            }
        }
        if (request) requestSuggestions?.invoke()
    }

    private fun completeChip(composing: String, candidate: String) {
        if (disposed || sensitiveField) return
        val provider = suggest ?: return
        val completer = completeWord ?: return
        clearUnavailable()
        // Re-verify the composing word at tap time: the caret may have moved
        // since this chip rendered.
        val fresh = runCatching { provider.invoke() }.getOrNull()
        if (fresh == null || fresh.composing != composing || composing.isEmpty() ||
            candidate !in fresh.candidates) {
            unavailable()
            return
        }
        if (completer.invoke(composing, candidate)) {
            render()
        } else {
            unavailable()
        }
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
        if (disposed || sensitiveField) return
        if (rawField) {
            clearUnavailable(); unavailable()
            return
        }
        hubOpen = false; editOpen = false; extraKeysOpen = false; extraKeyGroup = ExtraKeyGroup.ACCESSORY
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
        val accepted = if (!sensitiveField && (ctrl || alt)) modifiedCommit(value, ctrl, alt) else commit(value)
        selecting = false
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
        if (disposed || sensitiveField) return
        clearUnavailable()
        val accepted = terminalKey(code, ctrl, alt, shift)
        if (!accepted) unavailable()
    }
    private fun usesModifiedDelete() = !sensitiveField && (ctrl || alt || (shift && (extraKeysOpen || rawField)))
    private fun delete() {
        clearUnavailable()
        if (usesModifiedDelete()) special(KeyEvent.KEYCODE_DEL) else erase()
        refreshSuggestionsRow()
    }
    private fun navigate(left: Boolean) {
        if (disposed || sensitiveField) return
        clearUnavailable()
        if (selecting || shift || ctrl || alt) {
            val accepted = terminalKey(if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT,
                ctrl, alt, selecting || shift)
            if (!accepted) unavailable()
        } else move(left)
        refreshSuggestionsRow()
    }

    /** Select the word immediately before the caret using the editor's native word movement. */
    private fun selectNeighboringWord() {
        if (disposed || sensitiveField) return
        clearUnavailable()
        val accepted = terminalKey(KeyEvent.KEYCODE_DPAD_LEFT, true, false, true)
        if (!accepted) unavailable() else view.announceForAccessibility("Selected neighboring word")
    }

    private fun returnToTyping() {
        cancelForGeometryChange()
        hubOpen = false; editOpen = false
        symbols = false; moreSymbols = false; alternateMode = false; alternateKey = null
        cancelCompose()
        render()
    }

    private fun openHub() {
        if (disposed || sensitiveField) return
        cancelForGeometryChange()
        hubOpen = true; editOpen = false
        extraKeysOpen = false; extraKeyGroup = ExtraKeyGroup.ACCESSORY
        alternateMode = false; alternateKey = null; cancelCompose()
        render()
        view.announceForAccessibility(if (privateEditing) "Keyboard tools" else "Keyboard tools and settings")
    }
    private fun splitGap(row: LinearLayout) {
        row.addView(View(context).apply {
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            isClickable = false
            isFocusable = false
        }, LinearLayout.LayoutParams(Ui.dp(context, 72), 1))
    }
    private fun characterRow(sequence: String) {
        val line = row()
        if (!splitLandscape()) {
            characters(line, sequence)
            return
        }
        val split = (sequence.length + 1) / 2
        characters(line, sequence.take(split))
        splitGap(line)
        characters(line, sequence.drop(split))
    }

    private fun openEdit() {
        if (disposed || sensitiveField) return
        cancelForGeometryChange()
        hubOpen = false; editOpen = true
        extraKeysOpen = false; extraKeyGroup = ExtraKeyGroup.ACCESSORY
        alternateMode = false; alternateKey = null; cancelCompose()
        render()
        view.announceForAccessibility("Editing tools")
    }

    private fun openExtraKeys() {
        if (disposed || sensitiveField) return
        cancelForGeometryChange()
        hubOpen = false; editOpen = false
        extraKeysOpen = true; extraKeyGroup = ExtraKeyGroup.ACCESSORY
        render()
        view.announceForAccessibility("Extra keys open")
    }

    private fun toggleNumberRow() {
        cancelForGeometryChange()
        saveQuickOption(numberRow = !options.numberRow)
        render(); quickOptionsChanged()
    }

    private fun toggleExtraKeysPanel() {
        if (disposed || sensitiveField) return
        cancelForGeometryChange()
        extraKeysOpen = !extraKeysOpen
        if (!extraKeysOpen) extraKeyGroup = ExtraKeyGroup.ACCESSORY
        render()
        view.announceForAccessibility(if (extraKeysOpen) "Extra keys open" else "Extra keys closed")
    }

    private fun toolbarKey(row: LinearLayout, label: String, description: String, widthDp: Int = 62,
        selected: Boolean = false, enabled: Boolean = true, action: () -> Unit): Button =
        key(row, label, description, utility = true, height = 48, chordable = false,
            widthDp = widthDp, compact = true, action = action).apply {
            setPadding(Ui.dp(context, 8), 0, Ui.dp(context, 8), 0)
            isSelected = selected; isEnabled = enabled
        }

    private fun toolbarIcon(row: LinearLayout, icon: Int, description: String, weight: Float = 1f,
        primary: Boolean = false, pill: Boolean = false, enabled: Boolean = true, selected: Boolean = false,
        iconSizeDp: Int = 24, tintIcon: Boolean = true,
        action: () -> Unit): Button =
        key(row, "", description, weight = weight, utility = !primary, primary = primary, height = 48,
            chordable = false, compact = true, pill = pill, action = action).apply {
            (this as HintedKey).primaryIcon = context.getDrawable(icon)?.mutate()
            this.primaryIconSizeDp = iconSizeDp
            this.tintPrimaryIcon = tintIcon
            isEnabled = enabled; isSelected = selected
        }

    private fun allowsEditorAction(action: EditorAction) =
        (!sensitiveField || action == EditorAction.PASTE) && actionAvailable(action)

    private fun performEditorAction(action: EditorAction): Boolean =
        !disposed && allowsEditorAction(action) && editorAction(action)

    private fun toolbarEditorAction(row: LinearLayout, action: EditorAction, icon: Int) {
        val button = toolbarIcon(row, icon, action.label) {
            val accepted = performEditorAction(action)
            selecting = false
            if (!accepted) unavailable()
        }
        actionKeys[action] = button
        button.isEnabled = allowsEditorAction(action)
    }

    private fun editorActionKey(row: LinearLayout, action: EditorAction, label: String = action.label) {
        val button = key(row, label, action.label, utility = true, height = 48, chordable = false) {
            val accepted = performEditorAction(action)
            selecting = false
            if (!accepted) unavailable()
        }
        actionKeys[action] = button
        button.isEnabled = allowsEditorAction(action)
    }

    private fun selectActionKey(row: LinearLayout, height: Int = 48) {
        val generation = layoutGeneration
        val button = key(row, "Select", "Select neighboring word", utility = true, height = height,
            chordable = false, compact = true) { selectNeighboringWord() }
        actionKeys[EditorAction.SELECT_ALL] = button
        button.isEnabled = allowsEditorAction(EditorAction.SELECT_ALL)
        button.setOnLongClickListener {
            if (disposed || generation != layoutGeneration) false else {
                val accepted = performEditorAction(EditorAction.SELECT_ALL)
                selecting = false
                if (!accepted) unavailable() else view.announceForAccessibility("Selected all text")
                true
            }
        }
        button.accessibilityDelegate = object : View.AccessibilityDelegate() {
            override fun onInitializeAccessibilityNodeInfo(host: View,
                info: android.view.accessibility.AccessibilityNodeInfo) {
                super.onInitializeAccessibilityNodeInfo(host, info)
                if (host.isEnabled) info.addAction(android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction(
                    android.view.accessibility.AccessibilityNodeInfo.ACTION_LONG_CLICK, "Select all text"))
            }
        }
    }

    private fun normalToolbar() {
        if (sensitiveField) {
            val actions = row()
            toolbarEditorAction(actions, EditorAction.PASTE, R.drawable.ic_paste)
            if (openPasswordManager != null) {
                toolbarIcon(actions, R.drawable.ic_key, "Open password manager") {
                    if (openPasswordManager.invoke() != true) unavailable()
                }
            }
            key(actions, "Switch", "Switch keyboard", utility = true, height = 48,
                chordable = false, compact = true) { switchKeyboard() }
            toolbarStatus = null
            return
        }
        val actions = row()
        toolbarEditorAction(actions, EditorAction.UNDO, R.drawable.ic_undo)
        toolbarEditorAction(actions, EditorAction.REDO, R.drawable.ic_redo)
        if (privateEditing) {
            repeat(3) { spacer(actions, 1f) }
        } else {
            toolbarEditorAction(actions, EditorAction.CUT, R.drawable.ic_cut)
            toolbarEditorAction(actions, EditorAction.COPY, R.drawable.ic_copy)
            toolbarEditorAction(actions, EditorAction.PASTE, R.drawable.ic_paste)
        }
        selectActionKey(actions)

        // A single 12-position strip keeps the typing rows visible in landscape.
        // Portrait retains two rows so every target stays at least 48dp wide.
        val destinations = if (context.resources.configuration.orientation ==
            Configuration.ORIENTATION_LANDSCAPE) actions else row()
        key(destinations, "Tools", "Keyboard tools", utility = true, height = 48,
            chordable = false, compact = true) { openHub() }
        key(destinations, "Edit", "Editing tools", utility = true, height = 48,
            chordable = false, compact = true) { openEdit() }
        toolbarIcon(destinations, R.drawable.ic_emoji, "Emoji", enabled = emojiAllowed) { showEmoji() }
        if (!privateEditing && openPasswordManager != null) {
            toolbarIcon(destinations, R.drawable.ic_key, "Open password manager") {
                if (openPasswordManager?.invoke() != true) unavailable()
            }
        } else if (!privateEditing && openDraft != null) {
            toolbarIcon(destinations, R.drawable.ic_draft, "Private draft") { openDraft?.invoke() }
        } else spacer(destinations, 1f)
        if (!privateEditing) {
            toolbarIcon(destinations, R.drawable.utterling_mic, "Dictate", primary = true, pill = true,
                enabled = voiceAllowed, iconSizeDp = 34, tintIcon = false) { dictate() }
        } else {
            spacer(destinations, 1f)
        }
        if (options.extraKeys) toolbarIcon(destinations, R.drawable.ic_expand_open,
            if (extraKeysOpen) "Close extra keys" else "Extra keys", selected = extraKeysOpen) {
            if (extraKeysOpen) toggleExtraKeysPanel() else openExtraKeys()
        }
        else spacer(destinations, 1f)
        toolbarStatus = null
    }

    private fun editRows() {
        val history = row()
        editorActionKey(history, EditorAction.UNDO)
        editorActionKey(history, EditorAction.REDO)
        selectActionKey(history)
        val clipboard = row()
        editorActionKey(clipboard, EditorAction.CUT)
        editorActionKey(clipboard, EditorAction.COPY)
        editorActionKey(clipboard, EditorAction.PASTE)
        val navigation = row()
        key(navigation, "←", "Move cursor left", utility = true, height = 48, chordable = false) { navigate(true) }
        key(navigation, "→", "Move cursor right", utility = true, height = 48, chordable = false) { navigate(false) }
        if (options.extraKeys) {
            key(navigation, "More keys", "Extra keys", utility = true, height = 48,
                chordable = false) { openExtraKeys() }
        } else spacer(navigation, 1f)
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
        val destinations = row()
        if (!privateEditing && openPasswordManager != null) {
            key(destinations, "Passwords", "Open password manager", utility = true, height = 48,
                chordable = false) { if (openPasswordManager?.invoke() != true) unavailable() }
        } else if (!privateEditing && openDraft != null) {
            key(destinations, "Draft", "Private draft", utility = true, height = 48,
                chordable = false) { openDraft?.invoke() }
        } else spacer(destinations, 1f)
        key(destinations, "Extra keys", "Extra keys", utility = true, height = 48,
            chordable = false) { openExtraKeys() }
        if (!privateEditing) {
            key(destinations, "123 row", if (options.numberRow) "Number row on" else "Number row off",
                utility = true, height = 48, chordable = false) { toggleNumberRow() }
                .apply { isSelected = options.numberRow }
        } else spacer(destinations, 1f)
        val text = row()
        key(text, "Accents", "Accents and alternate characters", utility = true, height = 48, chordable = false) {
            cancelForGeometryChange(); cancelCompose(); hubOpen = false
            alternateMode = true; alternateKey = null; symbols = false
            render()
            view.announceForAccessibility("Tap a letter for accents, or period for punctuation")
        }
        key(text, "Compose", if (rawField) "Latin compose unavailable in raw input" else "Latin compose",
            utility = true, height = 48, chordable = false) { beginCompose() }.apply { isEnabled = !rawField }
        spacer(text, 1f)
        if (privateEditing) {
            // Keep the layer stable while host preferences stay out of a draft.
            repeat(2) { row().minimumHeight = Ui.dp(context, 48) }
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
        key(alignment, "Split", "Split keyboard in landscape", utility = true, height = 48, chordable = false) {
            chooseSplitLandscape()
        }.apply { isSelected = options.splitLandscape }
        val layouts = row()
        LetterLayout.entries.forEach { layout ->
            key(layouts, layout.label, "${layout.label} letter layout", utility = true, height = 48, chordable = false) {
                chooseLetterLayout(layout)
            }.apply { isSelected = options.letterLayout == layout }
        }
    }

    /** One grouped specialist row keeps the typing surface and daily toolbar visible. */
    private fun extraKeyRows() {
        addExtraKeyControls(row())
    }

    private fun landscapeExtraHeader() {
        val specialist = row()
        key(specialist, "ABC", "Close extra keys", utility = true, height = 48, widthDp = 48,
            compact = true, labelSizeSp = 12, chordable = false) { toggleExtraKeysPanel() }
        addExtraKeyControls(specialist)
    }

    private fun addExtraKeyControls(specialist: LinearLayout, stripWeight: Float = 1f) {
        fun group(label: String, description: String, value: ExtraKeyGroup) {
            key(specialist, label, description, utility = true, height = 48, widthDp = 48,
                compact = true, labelSizeSp = 12, chordable = false) {
                if (extraKeyGroup != value) { extraKeyGroup = value; render() }
            }.isSelected = extraKeyGroup == value
        }
        group("Keys", "Accessory keys", ExtraKeyGroup.ACCESSORY)
        group("F1–12", "Function keys", ExtraKeyGroup.FUNCTIONS)

        val strip = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            isMotionEventSplittingEnabled = false
            isBaselineAligned = false
        }
        specialist.addView(HorizontalScrollView(context).apply {
            isHorizontalScrollBarEnabled = false
            isFillViewport = true
            overScrollMode = View.OVER_SCROLL_IF_CONTENT_SCROLLS
            addView(strip, FrameLayout.LayoutParams(-2, Ui.dp(context, 48)))
        }, LinearLayout.LayoutParams(0, Ui.dp(context, 48), stripWeight))

        when (extraKeyGroup) {
            ExtraKeyGroup.ACCESSORY -> {
                key(strip, "Esc", "Escape", utility = true, height = 48, widthDp = 52,
                    compact = true, labelSizeSp = 14) { special(KeyEvent.KEYCODE_ESCAPE) }
                ctrlKey = key(strip, "Ctrl", "Control off", utility = true, height = 48, widthDp = 52,
                    compact = true, labelSizeSp = 14) { ctrl = !ctrl; updateCase() }
                addNavigationKey(strip, "←", "Left arrow", KeyEvent.KEYCODE_DPAD_LEFT)
                altKey = key(strip, "Alt", "Alt off", utility = true, height = 48, widthDp = 52,
                    compact = true, labelSizeSp = 14) { alt = !alt; updateCase() }
                shiftKeys.add(key(strip, "Shift", if (shift) "Shift on" else "Shift off", utility = true,
                    height = 48, widthDp = 58, compact = true, labelSizeSp = 13, chordable = false) { tapShift() }
                    .apply { tag = "Shift"; attachCapsLock(this) })
                key(strip, "Tab", utility = true, height = 48, widthDp = 52,
                    compact = true, labelSizeSp = 14) { special(KeyEvent.KEYCODE_TAB) }
                listOf(
                    Triple("↓", "Down arrow", KeyEvent.KEYCODE_DPAD_DOWN),
                    Triple("↑", "Up arrow", KeyEvent.KEYCODE_DPAD_UP),
                    Triple("→", "Right arrow", KeyEvent.KEYCODE_DPAD_RIGHT),
                    Triple("Home", "Home", KeyEvent.KEYCODE_MOVE_HOME),
                    Triple("End", "End", KeyEvent.KEYCODE_MOVE_END),
                    Triple("Ins", "Insert", KeyEvent.KEYCODE_INSERT),
                    Triple("Del", "Forward delete", KeyEvent.KEYCODE_FORWARD_DEL),
                    Triple("PgUp", "Page up", KeyEvent.KEYCODE_PAGE_UP),
                    Triple("PgDn", "Page down", KeyEvent.KEYCODE_PAGE_DOWN)).forEach { (label, description, code) ->
                    addNavigationKey(strip, label, description, code)
                }
            }
            ExtraKeyGroup.FUNCTIONS -> (1..12).forEach { number ->
                key(strip, "F$number", utility = true, height = 48, widthDp = 52,
                    compact = true, labelSizeSp = 14) { special(KeyEvent.KEYCODE_F1 + number - 1) }
            }
        }
    }

    private fun addNavigationKey(row: LinearLayout, label: String, description: String, code: Int) {
        val generation = layoutGeneration
        val button = key(row, label, description, utility = true, height = 48, widthDp = 54,
            compact = true, labelSizeSp = if (label.length == 1) 20 else 12) { special(code) }
        if (options.arrowRepeat && code in setOf(KeyEvent.KEYCODE_DPAD_LEFT,
                KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN)) {
            arrowRepeaters.add(ArrowRepeater(button) {
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
        val generation = layoutGeneration
        button.setOnLongClickListener {
            if (disposed || generation != layoutGeneration) false else {
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
        suggestionRow = null; suggestionChips.clear(); suggestionEmpty = null
        shiftKeys.clear(); letterShiftKey = null; capsKey = null; ctrlKey = null; altKey = null
        applyContentAlignment()
        val landscapeExtra = extraKeysOpen && context.resources.configuration.orientation ==
            Configuration.ORIENTATION_LANDSCAPE
        when {
            hubOpen -> layerHeader("All tools", "Close tools and settings")
            editOpen -> layerHeader("Edit", "Close editing tools")
            extraKeysOpen -> if (landscapeExtra) landscapeExtraHeader() else normalToolbar()
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
                normalToolbar()
                if (!sensitiveField && suggest != null && !symbols) suggestionRow()
            }
        }
        if (hubOpen) { hubRows(); updateCase(); return }
        if (editOpen) { editRows(); updateCase(); return }
        if (extraKeysOpen && !landscapeExtra) extraKeyRows()
        if (composeChoosingMark) { composeMarkRows(); updateCase(); return }
        if (composeMark != null) { composeLetterRows(); updateCase(); return }
        alternateKey?.let { alternateRows(it); updateCase(); return }
        if (options.numberRow && !symbols) characterRow("1234567890")
        if (symbols) {
            characterRow(if (moreSymbols) "`~!@#$%^&*" else "1234567890")
            characterRow(if (moreSymbols) "()-_=+[]{}" else "@#$%&-+()/")
            if (moreSymbols) {
                characterRow("\\|;:\"',<>./?")
                val last = row()
                key(last, "?123", "More numbers and symbols", 1.5f, utility = true) {
                    moreSymbols = false; render()
                }
                characters(last, "±×÷")
                if (splitLandscape()) splitGap(last)
                characters(last, "§©®")
                key(last, "⌫", "Delete", 1.5f, utility = true) { delete() }
            } else {
                val third = row()
                key(third, "=\\<", "More symbols", 1.5f, utility = true) {
                    moreSymbols = true; render()
                }
                characters(third, "*\"':")
                if (splitLandscape()) splitGap(third)
                characters(third, ";!?_")
                key(third, "⌫", "Delete", 1.5f, utility = true) { delete() }
            }
        } else {
            val layout = options.letterLayout
            characterRow(layout.top)
            val home = row()
            val homeEdge = (10 - layout.home.length) / 2f
            spacer(home, homeEdge)
            if (splitLandscape()) {
                val split = (layout.home.length + 1) / 2
                characters(home, layout.home.take(split)); splitGap(home); characters(home, layout.home.drop(split))
                if (layout.home.length % 2 != 0) spacer(home, 1f)
            } else characters(home, layout.home)
            spacer(home, homeEdge)
            val third = row()
            val bottomEdge = (10 - layout.bottom.length) / 2f
            val shiftButton = key(third, "⇧", "Shift off", bottomEdge, utility = true) { tapShift() }
            shiftButton.tag = "⇧"
            shiftKeys.add(shiftButton)
            letterShiftKey = shiftButton
            attachCapsLock(shiftButton)
            if (splitLandscape()) {
                val split = (layout.bottom.length + 1) / 2
                characters(third, layout.bottom.take(split)); splitGap(third); characters(third, layout.bottom.drop(split))
                if (layout.bottom.length % 2 != 0) spacer(third, 1f)
            } else characters(third, layout.bottom)
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
            extraKeysOpen = false; extraKeyGroup = ExtraKeyGroup.ACCESSORY
            cancelCompose(); alternateMode = false; alternateKey = null; render()
        }
        // Daily destinations live in the stable toolbar; keep this row focused on typing.
        val spaces = mutableListOf<Button>()
        fun addSpace(weight: Float) = key(bottom, spaceLabel ?: "", "Space", weight, labelSizeSp = 14) {
            if (type(" ")) refreshSuggestionsRow()
        }.also { space ->
            spaces += space
            val generation = layoutGeneration
            // Recognize and consume a drag in sensitive fields, but navigate()
            // refuses it without calling the host or inserting an accidental space.
            gestures.attachSpace(space) { left -> if (generation == layoutGeneration) navigate(left) }
        }
        if (splitLandscape()) {
            spacer(bottom, 1f)
            addSpace(2.5f)
            splitGap(bottom)
            addSpace(2.5f)
        } else {
            spacer(bottom, 1.5f)
            addSpace(5f)
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
            if (!sensitiveField && (ctrl || alt)) special(KeyEvent.KEYCODE_ENTER)
            else {
                if (!sensitiveField && options.autoCapitalize && actionLabel == "Enter" && !caps) {
                    shift = true
                    view.announceForAccessibility("Capitalization armed")
                }
                enter()
            }
            updateCase()
            refreshSuggestionsRow()
        }
        val generation = layoutGeneration
        if (!sensitiveField) view.bindSelection(letterShiftKey, spaces.last()) { left ->
            if (generation == layoutGeneration) {
                ctrl = false; alt = false; updateCase()
                if (!terminalKey(if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT,
                        false, false, true)) unavailable()
                refreshSuggestionsRow()
            }
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
