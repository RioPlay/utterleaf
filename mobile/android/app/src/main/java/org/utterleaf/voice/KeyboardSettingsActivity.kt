package org.utterleaf.voice

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.Editable
import android.text.InputFilter
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.TextView

/**
 * Mockup Settings: category list with search, staged edits applied only on
 * Apply, and a practice message with the live keyboard preview. Input in the
 * practice area stays on this screen, is cleared on close and is never saved.
 */
class KeyboardSettingsActivity : Activity() {
    private var staged = KeyboardOptions()
    private var stagedVoiceHold = false
    private var previewPanel: TypingPanel? = null
    private lateinit var practiceEditor: EditText
    private var practiceActive = false
    private var practiceGeneration = 0
    private var previewContainer: LinearLayout? = null
    private var detail: String? = null
    private var query = ""
    private data class Draft(val options: KeyboardOptions, val voiceHold: Boolean,
        val detail: String?, val query: String)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            onBackInvokedDispatcher.registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT) { navigateBack() }
        }
        practiceEditor = EditText(this).apply {
            hint = "Practice typing here"
            setText("Let's meet tomorrow at six. Bring the notes.")
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            filters = arrayOf(InputFilter.LengthFilter(256))
            isSaveEnabled = false
            showSoftInputOnFocus = false
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
            setTextIsSelectable(true)
        }
        staged = KeyboardOptions.load(this)
        stagedVoiceHold = getSharedPreferences("keyboard", Context.MODE_PRIVATE)
            .getBoolean("voiceHoldToInsert", false)
        (lastNonConfigurationInstance as? Draft)?.let {
            staged = it.options; stagedVoiceHold = it.voiceHold
            detail = it.detail; query = it.query
        }
    }
    // Configuration changes retain explicit choices in memory, never practice input.
    override fun onRetainNonConfigurationInstance(): Any = Draft(staged, stagedVoiceHold, detail, query)
    override fun onStart() { super.onStart(); practiceActive = true; render() }
    private fun practiceConnection(generation: Int): android.view.inputmethod.InputConnection? {
        if (!practiceActive || isFinishing || isDestroyed || generation != practiceGeneration) return null
        practiceEditor.requestFocus()
        return practiceEditor.onCreateInputConnection(EditorInfo())
    }

    private fun subtypeSummary(): String {
        val subtype = (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
            .currentInputMethodSubtype ?: return ""
        @Suppress("DEPRECATION")
        val parts = subtype.locale.split("_", "-")
        if (parts.isEmpty()) return ""
        val locale = java.util.Locale(parts[0], parts.getOrElse(1) { "" })
        val language = locale.displayLanguage.uppercase()
        val rawRegion = locale.displayCountry.uppercase()
        val region = if (rawRegion.length > 3) locale.country.uppercase() else rawRegion
        return if (region.isBlank()) language else "$language · $region"
    }

    private fun subtypeSpaceLabel(): String {
        val subtype = (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
            .currentInputMethodSubtype ?: return ""
        @Suppress("DEPRECATION")
        val parts = subtype.locale.split("_", "-")
        if (parts.isEmpty()) return ""
        val locale = java.util.Locale(parts[0], parts.getOrElse(1) { "" })
        val region = if (locale.displayCountry.length > 3) locale.country else locale.displayCountry
        return if (region.isBlank()) locale.displayLanguage
        else "${locale.displayLanguage} ($region)"
    }

    private fun header(title: String, leftLabel: String, leftAction: () -> Unit): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, Ui.dp(this@KeyboardSettingsActivity, 8), 0, Ui.dp(this@KeyboardSettingsActivity, 12))
        }
        row.addView(Ui.button(this, leftLabel) { leftAction() }.apply {
            background = null
            setPadding(0, Ui.dp(this@KeyboardSettingsActivity, 12), Ui.dp(this@KeyboardSettingsActivity, 8),
                Ui.dp(this@KeyboardSettingsActivity, 12))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(TextView(this).apply {
            text = title; textSize = 18f; setTextColor(Ui.ink); setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(Ui.button(this, "Apply") {
            staged.save(this@KeyboardSettingsActivity)
            getSharedPreferences("keyboard", Context.MODE_PRIVATE).edit()
                .putBoolean("voiceHoldToInsert", stagedVoiceHold).apply()
            finish()
        }.apply {
            minHeight = Ui.dp(this@KeyboardSettingsActivity, 44)
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        return row
    }

    private fun categoryRow(icon: Int, title: String, summary: String, open: () -> Unit): View {
        val context = this
        val row = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = Ui.dp(context, 60)
            setPadding(Ui.dp(context, 4), Ui.dp(context, 8), Ui.dp(context, 4), Ui.dp(context, 8))
            background = Ripple()
            setOnClickListener { open() }
            contentDescription = "$title, $summary"
        }
        fun label(size: Float, value: String, bold: Boolean = false, color: Int = Ui.ink) = TextView(context).apply {
            text = value; textSize = size; setTextColor(color)
            if (bold) setTypeface(typeface, Typeface.BOLD)
        }
        row.addView(ImageView(context).apply {
            setImageResource(icon)
            colorFilter = android.graphics.PorterDuffColorFilter(Ui.ink, android.graphics.PorterDuff.Mode.SRC_IN)
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, LinearLayout.LayoutParams(Ui.dp(context, 22), Ui.dp(context, 22)).apply {
            marginEnd = Ui.dp(context, 16)
        })
        val text = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        text.addView(label(16f, title, bold = true))
        text.addView(label(12f, summary, color = Color.parseColor("#97A79E")))
        row.addView(text, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(label(20f, "›", color = Color.parseColor("#97A79E")))
        return row
    }

    private inner class Ripple : android.graphics.drawable.RippleDrawable(
        android.content.res.ColorStateList.valueOf(Color.parseColor("#33808080")),
        GradientDrawable().apply { setColor(Color.TRANSPARENT) },
        GradientDrawable().apply { setColor(Color.WHITE) })

    private fun renderCategoryList(target: LinearLayout) {
        target.removeAllViews()
        val context = this
        data class Category(val id: String, val icon: Int, val title: String, val summary: String)
        val categories = listOf(
            Category("layout", R.drawable.ic_layout, "Layout & size", listOf(
                if (staged.numberRow) "Number row on" else "Number row off",
                if (staged.extraKeys) "Fold-out extra keys" else "Extra keys hidden",
                when (staged.alignment) {
                    KeyboardAlignment.FULL -> "Full width"
                    KeyboardAlignment.LEFT -> "Left hand"
                    KeyboardAlignment.RIGHT -> "Right hand"
                }).joinToString(" · ")),
            Category("terminal", R.drawable.ic_nav, "Navigation & terminal", listOf(
                if (staged.arrowRepeat) "Arrow repeat on" else "Arrow repeat off",
                if (staged.extraKeys) "Expand arrow on" else "Expand arrow off").joinToString(" · ")),
            Category("assistance", R.drawable.ic_typing, "Typing assistance", listOf(
                if (staged.autoCapitalize) "Auto-capitalization on" else "Auto-capitalization off",
                if (staged.suggestions) "Suggestions on" else "Suggestions off",
                if (staged.secondaryHints) "Hints on" else "Hints off").joinToString(" · ")),
            Category("gestures", R.drawable.ic_gestures, "Holds & gestures", listOf(
                if (staged.holdDelayMs == 0) "System hold" else "${staged.holdDelayMs} ms hold",
                if (staged.secondaryHints) "Accents on" else "Accents by menu",
                "Cursor slide on").joinToString(" · ")),
            Category("appearance", R.drawable.ic_appearance, "Appearance", listOf(
                when (staged.theme) {
                    ThemeMode.SYSTEM -> "System"
                    ThemeMode.LIGHT -> "Light"
                    ThemeMode.DARK -> "Dark"
                },
                if (staged.keyBorders) "Key borders on" else "Key borders off").joinToString(" · ")),
            Category("voice", R.drawable.ic_mic, "Voice input",
                if (stagedVoiceHold) "Hold to start · On-device recognition"
                else "Tap to start · On-device recognition"),
            Category("privacy", R.drawable.ic_privacy, "Privacy & data",
                "Voice only when requested · No typing history"))
        val needle = query.trim().lowercase()
        categories.filter { needle.isEmpty() || it.title.lowercase().contains(needle) ||
            it.summary.lowercase().contains(needle) }.forEach { category ->
            target.addView(categoryRow(category.icon, category.title, category.summary) {
                detail = category.id
                render()
            })
        }
        if (target.childCount == 0) {
            target.addView(Ui.text(context, "No settings match \"$query\""))
        }
    }

    private fun render() {
        disposePreview()
        val root = Ui.column(this).apply { setPadding(0, 0, 0, 0) }
        val heading = Ui.column(this).apply { setPadding(Ui.dp(context, 18), 0, Ui.dp(context, 18), 0) }
        heading.addView(if (detail == null) header("Settings", "Cancel") { finish() }
        else header("Settings", "‹ Back") { detail = null; render() })
        root.addView(heading)
        val column = Ui.column(this)
        if (detail == null) {
            val search = EditText(this).apply {
                hint = "Search settings"
                textSize = 15f; setTextColor(Ui.ink)
                setHintTextColor(Color.parseColor("#71897B"))
                setSingleLine()
                setText(query)
                setSelection(text.length)
                isSaveEnabled = false
                importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
                background = GradientDrawable().apply {
                    setColor(Color.parseColor("#242E2B"))
                    cornerRadius = Ui.dp(this@KeyboardSettingsActivity, 12).toFloat()
                }
                setPadding(Ui.dp(this@KeyboardSettingsActivity, 14), Ui.dp(this@KeyboardSettingsActivity, 12),
                    Ui.dp(this@KeyboardSettingsActivity, 14), Ui.dp(this@KeyboardSettingsActivity, 12))
            }
            column.addView(search)
            val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            column.addView(list)
            renderCategoryList(list)
            search.addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
                override fun afterTextChanged(s: Editable?) {
                    query = s?.toString() ?: ""
                    renderCategoryList(list)
                }
            })
            column.addView(resetRow())
            column.addView(Ui.text(this,
                "Changes apply when you choose Apply; Cancel leaves everything unchanged. " +
                    "Reset restores defaults and keeps your models and microphone permission."))
        } else {
            column.addView(Ui.title(this, detailTitle()))
            column.addView(Ui.text(this, detailSummary(), 14f))
            detailControls(column)
            column.addView(practiceSection())
        }
        root.addView(ScrollView(this).apply {
            isFillViewport = true
            addView(column)
        }, LinearLayout.LayoutParams(-1, 0, 1f))
        Ui.applySystemInsets(root)
        setContentView(root)
    }

    private fun detailTitle() = when (detail) {
        "layout" -> "Layout & size"
        "terminal" -> "Navigation & terminal"
        "assistance" -> "Typing assistance"
        "gestures" -> "Holds & gestures"
        "appearance" -> "Appearance"
        "voice" -> "Voice input"
        else -> "Privacy & data"
    }

    private fun detailSummary() = when (detail) {
        "layout" -> "Rows, alignment and key sizing for the keyboard."
        "terminal" -> "Navigation keys, F-keys and repeat behavior."
        "assistance" -> "Capitalization, word completions and character hints."
        "gestures" -> "Hold timing, vibration and gesture notes."
        "appearance" -> "Theme and key borders."
        "voice" -> "How dictation starts, and where recognition runs."
        else -> "What the keyboard does and does not store."
    }

    private fun practiceSection(): View {
        val context = this
        val section = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        section.addView(Ui.text(context, "Practice message", 16f))
        section.addView(Ui.text(context, "Try your changes here before applying. This text is never saved.", 13f))
        val card = GradientDrawable().apply {
            setColor(Color.parseColor("#242E2B"))
            cornerRadius = Ui.dp(context, 10).toFloat()
        }
        (practiceEditor.parent as? android.view.ViewGroup)?.removeView(practiceEditor)
        practiceEditor.background = card
        practiceEditor.setPadding(Ui.dp(context, 14), Ui.dp(context, 12), Ui.dp(context, 14), Ui.dp(context, 12))
        practiceEditor.setTextColor(Ui.ink)
        practiceEditor.setHintTextColor(Color.parseColor("#71897B"))
        section.addView(practiceEditor, LinearLayout.LayoutParams(-1, Ui.dp(context, 88)).apply {
            topMargin = Ui.dp(context, 6)
        })
        previewContainer = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        section.addView(Ui.text(context, "Keyboard preview", 14f))
        section.addView(previewContainer)
        updatePreview()
        return section
    }

    private fun updatePreview() {
        val generation = ++practiceGeneration
        val preview = previewContainer ?: return
        previewPanel?.dispose()
        preview.removeAllViews()
        previewPanel = TypingPanel(this, staged,
            { value -> TerminalInput.printable(practiceConnection(generation), value) },
            { TerminalInput.send(practiceConnection(generation), android.view.KeyEvent.KEYCODE_DEL) },
            { TerminalInput.printable(practiceConnection(generation), "\n") },
            { left -> TerminalInput.send(practiceConnection(generation),
                if (left) android.view.KeyEvent.KEYCODE_DPAD_LEFT else android.view.KeyEvent.KEYCODE_DPAD_RIGHT) },
            {}, {}, {},
            { code, ctrl, alt, shift ->
                TerminalInput.command(practiceConnection(generation), code, ctrl, alt, shift) },
            { value, ctrl, alt -> TerminalInput.printable(practiceConnection(generation), value, ctrl, alt) },
            quickOptionsChanged = { render() },
            editorAction = { command -> EditorActions.perform(practiceConnection(generation), command, practiceEditor.inputType) },
            spaceLabel = subtypeSpaceLabel().ifBlank { null },
            stageOptions = { staged = it }).apply {
            reset(false, false, "Enter")
        }
        preview.addView(previewPanel!!.view)
    }

    private fun resetRow(): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = Ui.dp(this@KeyboardSettingsActivity, 56)
            setPadding(Ui.dp(this@KeyboardSettingsActivity, 4), Ui.dp(this@KeyboardSettingsActivity, 10), 0,
                Ui.dp(this@KeyboardSettingsActivity, 10))
            background = Ripple()
        }
        row.addView(ImageView(this).apply {
            setImageResource(R.drawable.ic_undo)
            colorFilter = android.graphics.PorterDuffColorFilter(Ui.ink, android.graphics.PorterDuff.Mode.SRC_IN)
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, LinearLayout.LayoutParams(Ui.dp(this, 20), Ui.dp(this, 20)).apply {
            marginEnd = Ui.dp(this@KeyboardSettingsActivity, 16)
        })
        row.addView(Ui.text(this, "Reset preferences", 16f))
        row.contentDescription = "Reset preferences"
        row.setOnClickListener {
            AlertDialog.Builder(this).setTitle("Reset preferences?")
                .setMessage("Restore the redesigned defaults: number row on, extra keys on, system theme, " +
                    "auto-capitalization on, arrow repeat on, key borders on, QWERTY, Full width, standard key " +
                    "size, 320 ms hold and no repeat filtering. Choose Apply to save the reset, or Cancel to keep " +
                    "your preferences. Your models and microphone permission stay unchanged.")
                .setNegativeButton("Cancel", null).setPositiveButton("Reset") { _, _ ->
                    staged = KeyboardOptions()
                    stagedVoiceHold = false
                    render()
                }.show()
        }
        return row
    }

    private fun toggle(label: String, checked: Boolean, update: (Boolean) -> Unit) {
        val context = this
        column2().addView(CheckBox(context).apply {
            text = label; textSize = 16f; setTextColor(Ui.ink); minHeight = Ui.dp(context, 48)
            isChecked = checked
            setOnCheckedChangeListener { _, value ->
                update(value)
                updatePreview()
            }
        })
    }
    private var controlsColumn: LinearLayout? = null
    private fun column2(): LinearLayout = controlsColumn!!

    private fun choice(label: String, options: List<Pair<String, Boolean>>, pick: (Int) -> Unit) {
        val context = this
        column2().addView(RadioGroup(context).apply {
            orientation = RadioGroup.VERTICAL
            options.forEachIndexed { index, (text, checked) ->
                addView(RadioButton(context).apply {
                    this.text = text; textSize = 16f; setTextColor(Ui.ink)
                    minHeight = Ui.dp(context, 44)
                    isChecked = checked
                    setOnClickListener { pick(index); updatePreview() }
                })
            }
        })
    }

    private fun slider(value: Int, max: Int, display: (Int) -> String, update: (Int) -> Unit) {
        val context = this
        val labelView = Ui.text(context, display(value), 14f)
        column2().addView(labelView)
        column2().addView(SeekBar(context).apply {
            this.max = max; progress = value
            contentDescription = display(value)
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(seekBar: SeekBar, progress: Int, fromUser: Boolean) {
                    labelView.text = display(progress)
                    seekBar.contentDescription = display(progress)
                    if (fromUser) {
                        update(progress)
                        updatePreview()
                    }
                }
                override fun onStartTrackingTouch(seekBar: SeekBar) = Unit
                override fun onStopTrackingTouch(seekBar: SeekBar) = Unit
            })
        })
    }

    private fun note(value: String) {
        column2().addView(Ui.text(this, value, 13f).apply {
            setTextColor(Color.parseColor("#97A79E"))
        })
    }

    private fun detailControls(controls: LinearLayout) {
        controlsColumn = controls
        when (detail) {
            "layout" -> {
                toggle("Number row", staged.numberRow) { staged = staged.copy(numberRow = it) }
                toggle("Fold-out extra keys", staged.extraKeys) { staged = staged.copy(extraKeys = it) }
                toggle("Larger keys and labels", staged.large) { staged = staged.copy(large = it) }
                slider(if (staged.keyHeightDp == 0) 0 else staged.keyHeightDp - 47, 33,
                    { progress -> if (progress == 0) "Key height: default" else "Key height: ${progress + 47} dp" },
                    { progress -> staged = staged.copy(keyHeightDp = if (progress == 0) 0 else progress + 47) })
                slider(staged.bottomPaddingDp, 80,
                    { progress -> "Bottom space: $progress dp" },
                    { progress -> staged = staged.copy(bottomPaddingDp = progress) })
                Ui.text(this, "Keyboard alignment", 16f).let { controls.addView(it) }
                choice("alignment", listOf(
                    "Full width" to (staged.alignment == KeyboardAlignment.FULL),
                    "Left hand" to (staged.alignment == KeyboardAlignment.LEFT),
                    "Right hand" to (staged.alignment == KeyboardAlignment.RIGHT))) { index ->
                    staged = staged.copy(alignment = KeyboardAlignment.entries[index])
                }
                note("Left and Right keep every key in a narrower column on wider screens.")
                Ui.text(this, "Letter layout", 16f).let { controls.addView(it) }
                choice("letters", LetterLayout.entries.map { it.label to (staged.letterLayout == it) }) { index ->
                    staged = staged.copy(letterLayout = LetterLayout.entries[index])
                }
                note("Changes letter positions only. It does not add spelling or speech support.")
            }
            "terminal" -> {
                toggle("Arrow repeat", staged.arrowRepeat) { staged = staged.copy(arrowRepeat = it) }
                toggle("Hold Backspace or Delete to repeat", staged.deleteRepeat) { staged = staged.copy(deleteRepeat = it) }
                toggle("Ignore repeated taps on the same key within 250 ms", staged.repeatGuard) {
                    staged = staged.copy(repeatGuard = it)
                }
                note("Open the expand arrow in the toolbar for Esc, Tab, Ctrl, Alt, navigation and F1–F12. " +
                    "Ctrl and Alt apply to the next key, then release. Terminal apps decide which shortcuts they support.")
            }
            "assistance" -> {
                toggle("Auto-capitalization", staged.autoCapitalize) { staged = staged.copy(autoCapitalize = it) }
                note("Arms shift after a sentence-ending period, !, ? or Enter. A tap still types the key.")
                toggle("Suggestions", staged.suggestions) { staged = staged.copy(suggestions = it) }
                note("Completes the word you are typing from a local public-domain English list. Tapping a " +
                    "suggestion replaces only the word being typed; nothing is learned, corrected or sent, and " +
                    "password and terminal fields never show suggestions.")
                toggle("Secondary character hints", staged.secondaryHints) { staged = staged.copy(secondaryHints = it) }
                note("Hold a letter, slide to a highlighted accent or symbol, then release; slide away to cancel. " +
                    "Hiding hints keeps the hold-to-insert and Tools routes available.")
            }
            "gestures" -> {
                fun holdDelayFromProgress(progress: Int) = if (progress == 0) 0 else 250 + ((progress - 1) * 50)
                fun holdDelayProgress(value: Int) = if (value <= 0) 0 else ((value - 250) / 50 + 1).coerceIn(1, 12)
                slider(holdDelayProgress(staged.holdDelayMs), 12,
                    { progress -> if (progress == 0) "Hold timing: system default" else "Hold timing: ${holdDelayFromProgress(progress)} ms" },
                    { progress -> staged = staged.copy(holdDelayMs = holdDelayFromProgress(progress)) })
                note("Hold timing changes how long a press shows accent or punctuation choices. " +
                    "System default uses the device long-press timeout.")
                toggle("Key vibration (respects device settings)", staged.haptics) { staged = staged.copy(haptics = it) }
                note("Slide the spacebar to move the cursor. Hold Shift first, then slide the spacebar with another " +
                    "finger to select text. For taps, use Select all in Tools and the arrows in Extra keys.")
            }
            "appearance" -> {
                choice("theme", listOf(
                    "System" to (staged.theme == ThemeMode.SYSTEM),
                    "Light" to (staged.theme == ThemeMode.LIGHT),
                    "Dark" to (staged.theme == ThemeMode.DARK))) { index ->
                    staged = staged.copy(theme = ThemeMode.entries[index])
                }
                toggle("Key borders", staged.keyBorders) { staged = staged.copy(keyBorders = it) }
            }
            "voice" -> {
                toggle("Hold the mic key to insert", stagedVoiceHold) { value ->
                    stagedVoiceHold = value
                }
                note("Recognition runs on this device with imported models. Import or switch models in Utterleaf Setup. " +
                    "Nothing is sent anywhere and dictation is unavailable in password fields.")
            }
            else -> {
                note("Voice only when requested — microphone permission alone never starts recording.")
                note("No passive learning — the keyboard never learns from what you type.")
                note("No typing history — practice input is cleared when this screen closes and is never saved.")
                note("No clipboard monitoring — paste only reads the clipboard when you tap Paste.")
                note("Screen capture is blocked while the keyboard is visible.")
                note("Speech models stay in app storage; Reset preferences never deletes them.")
            }
        }
        controlsColumn = null
    }

    private fun disposePreview() {
        practiceGeneration++
        previewPanel?.dispose()
        previewPanel = null
        previewContainer?.removeAllViews()
        previewContainer = null
    }

    @Suppress("DEPRECATION")
    @android.annotation.SuppressLint("GestureBackNavigation") // API 33+ uses the platform callback above.
    override fun onBackPressed() {
        navigateBack()
    }

    private fun navigateBack() {
        if (detail != null) { detail = null; render() } else finish()
    }

    private fun clearPractice() {
        practiceActive = false; practiceGeneration++
        disposePreview()
        if (::practiceEditor.isInitialized) practiceEditor.setText("")
    }
    override fun finish() { clearPractice(); super.finish() }
    override fun onStop() { clearPractice(); super.onStop() }
}
