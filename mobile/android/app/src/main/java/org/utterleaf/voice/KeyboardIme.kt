package org.utterleaf.voice

import android.content.Intent
import android.inputmethodservice.InputMethodService
import android.text.InputType
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.view.inputmethod.InputMethodSubtype
import android.widget.FrameLayout
import android.widget.ScrollView

/** Typing stays available without a model or microphone permission. */
class KeyboardIme : InputMethodService() {
    private var root: FrameLayout? = null
    private var voice: VoicePanel? = null
    private var draft: PrivateDraftPanel? = null
    private var active = false
    /** Monotonically identifies the panel and editor session currently on screen.
     *  Every suggestion, composition, speech or editor callback must capture this token. */
    private var uiGeneration = 0L
    private var selectionStart = -1
    private var selectionEnd = -1
    private var backspaceSelection: HostBackspaceSelection? = null
    private var currentSubtype: InputMethodSubtype? = null

    private fun invalidateUiSession() {
        uiGeneration++
    }

    private fun currentUiSession(generation: Long): Boolean = active && uiGeneration == generation

    override fun onEvaluateFullscreenMode() = false
    override fun onCreateInputView(): View {
        window.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        return FrameLayout(this).also { root = it; Ui.applySystemInsets(it, navigationOnly = true) }
    }
    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        invalidateUiSession()
        active = false
        selectionStart = attribute?.initialSelStart ?: -1
        selectionEnd = attribute?.initialSelEnd ?: -1
        backspaceSelection = null; voice?.clear(); draft?.clear(); draft = null
        // Clear the old local query/preview at the field boundary, even if the
        // platform never follows this callback with onStartInputView.
        root?.removeAllViews()
    }
    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        active = info != null && (info.inputType != InputType.TYPE_NULL || KeyboardOptions.load(this).extraKeys)
        showTyping()
        if (!active) requestHideSelf(0)
    }
    override fun onUpdateSelection(oldSelStart: Int, oldSelEnd: Int, newSelStart: Int, newSelEnd: Int,
                                   candidatesStart: Int, candidatesEnd: Int) {
        super.onUpdateSelection(oldSelStart, oldSelEnd, newSelStart, newSelEnd, candidatesStart, candidatesEnd)
        selectionStart = newSelStart; selectionEnd = newSelEnd
        backspaceSelection?.update(newSelStart, newSelEnd)
    }
    /** Mockup space label, e.g. "English (US)"; blank when the subtype has no locale. */
    private fun subtypeSpaceLabel(): String {
        val subtype = currentSubtype ?: return ""
        @Suppress("DEPRECATION")
        val parts = subtype.locale.split("_", "-")
        if (parts.isEmpty() || parts[0].isBlank()) return ""
        val locale = java.util.Locale(parts[0], parts.getOrElse(1) { "" })
        val region = if (locale.displayCountry.length > 3) locale.country else locale.displayCountry
        return if (region.isBlank()) locale.displayLanguage
        else "${locale.displayLanguage} ($region)"
    }

    /** Bounded trailing-letter run before the caret; never a document read. */
    private fun suggestionState(): SuggestionEngine.SuggestionState {
        val connection = currentInputConnection ?: return SuggestionEngine.SuggestionState.EMPTY
        val before = runCatching { connection.getTextBeforeCursor(SuggestionEngine.MAX_COMPOSING, 0) }
            .getOrNull() ?: return SuggestionEngine.SuggestionState.EMPTY
        val composing = buildString {
            for (index in before.length - 1 downTo 0) {
                val char = before[index]
                if (!char.isLetter()) break
                append(char)
            }
        }.reversed()
        if (composing.isEmpty()) return SuggestionEngine.SuggestionState.EMPTY
        return SuggestionEngine.SuggestionState(composing, SuggestionRepository.load(this).completions(composing))
    }

    /**
     * One balanced editor transaction: delete the composing word, insert the
     * candidate. The composing word is re-verified at tap time so a caret
     * that moved since the strip rendered can never delete unrelated text.
     */
    private fun completeSuggestion(composing: String, candidate: String, generation: Long): Boolean {
        if (!currentUiSession(generation)) return false
        val connection = currentInputConnection ?: return false
        val before = runCatching { connection.getTextBeforeCursor(SuggestionEngine.MAX_COMPOSING, 0) }
            .getOrNull() ?: return false
        var trailingLetters = 0
        for (index in before.length - 1 downTo 0) {
            val char = before[index]
            if (!char.isLetter()) break
            trailingLetters++
        }
        if (trailingLetters != composing.length) return false
        return try {
            connection.beginBatchEdit()
            val deleted = connection.deleteSurroundingText(composing.length, 0) == true
            val committed = deleted && connection.commitText(candidate, 1) == true
            if (deleted && !committed) connection.commitText(composing, 1)
            committed
        } catch (_: Exception) {
            false
        } finally {
            runCatching { connection.endBatchEdit() }
        }
    }
    private fun commit(value: String, generation: Long): Boolean {
        if (!currentUiSession(generation)) return false
        return TerminalInput.printable(currentInputConnection, value,
            forceKeyEvents = currentInputEditorInfo?.inputType == InputType.TYPE_NULL)
    }
    private fun keyEvent(code: Int, generation: Long) {
        if (!currentUiSession(generation)) return
        TerminalInput.send(currentInputConnection, code)
    }
    override fun onCurrentInputMethodSubtypeChanged(newSubtype: InputMethodSubtype) {
        super.onCurrentInputMethodSubtypeChanged(newSubtype)
        currentSubtype = newSubtype
        invalidateUiSession()
        voice?.clear()
        draft?.clear(); draft = null
        root?.removeAllViews()
        if (isInputViewShown && active) showTyping()
    }
    private fun showTyping() {
        invalidateUiSession()
        voice?.clear(); voice = null
        draft?.clear(); draft = null
        val info = currentInputEditorInfo
        val action = info?.imeOptions?.and(EditorInfo.IME_MASK_ACTION) ?: EditorInfo.IME_ACTION_NONE
        val useAction = info != null && info.imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION == 0 &&
            action in listOf(EditorInfo.IME_ACTION_GO, EditorInfo.IME_ACTION_SEARCH, EditorInfo.IME_ACTION_SEND,
                EditorInfo.IME_ACTION_NEXT, EditorInfo.IME_ACTION_DONE, EditorInfo.IME_ACTION_PREVIOUS)
        val label = if (useAction) when (action) {
            EditorInfo.IME_ACTION_GO -> "Go"; EditorInfo.IME_ACTION_SEARCH -> "Search"
            EditorInfo.IME_ACTION_SEND -> "Send"; EditorInfo.IME_ACTION_NEXT -> "Next"
            EditorInfo.IME_ACTION_PREVIOUS -> "Previous"; else -> "Done"
        } else "Enter"
        val generation = uiGeneration
        val options = KeyboardOptions.load(this)
        // The credential shortcut exists only on password fields with a
        // configured, launchable autofill application.
        val passwordManager = PasswordManagerKey.launchIntent(this, info?.inputType)?.let { template ->
            {
                try { startActivity(Intent(template).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); true }
                catch (_: Exception) { false }
            }
        }
        // Suggestions complete the current word only: a bounded before-cursor
        // read, no replacement, no learning, and never in restricted fields.
        val suggestionsAllowed = options.suggestions && active && info != null &&
            VoiceIme.safeField(info.inputType) && info.inputType != InputType.TYPE_NULL
        val suggest = if (suggestionsAllowed) ({ suggestionState() }) else null
        val completeWord = if (suggestionsAllowed) {
            { composing: String, candidate: String -> completeSuggestion(composing, candidate, generation) }
        } else null
        backspaceSelection = HostBackspaceSelection(
            current = { currentUiSession(generation) && active && info != null && VoiceIme.safeField(info.inputType) },
            connection = { currentInputConnection }, selection = { selectionStart to selectionEnd })
        val panel = TypingPanel(this, options,
            { value -> commit(value, generation) },
            { keyEvent(KeyEvent.KEYCODE_DEL, generation) },
            { if (currentUiSession(generation)) {
                if (info?.inputType == InputType.TYPE_NULL) TerminalInput.send(currentInputConnection, KeyEvent.KEYCODE_ENTER)
                else if (useAction) currentInputConnection?.performEditorAction(action) else commit("\n", generation)
            }; Unit },
            { left -> keyEvent(if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT, generation) },
            { if (currentUiSession(generation)) showVoice() },
            {
                if (currentUiSession(generation)) {
                    voice?.clear(); requestHideSelf(0)
                    startActivity(Intent(this, KeyboardSettingsActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                }
            },
            { if (currentUiSession(generation))
                (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker() },
            { code, ctrl, alt, shift -> currentUiSession(generation) &&
                TerminalInput.command(currentInputConnection, code, ctrl, alt, shift,
                    raw = info?.inputType == InputType.TYPE_NULL) },
            { text, ctrl, alt -> currentUiSession(generation) &&
                TerminalInput.printable(currentInputConnection, text, ctrl, alt,
                    forceKeyEvents = currentInputEditorInfo?.inputType == InputType.TYPE_NULL) },
            editorAction = { command -> currentUiSession(generation) &&
                EditorActions.perform(currentInputConnection, command, currentInputEditorInfo?.inputType) },
            spaceLabel = subtypeSpaceLabel(),
            rawField = info?.inputType == InputType.TYPE_NULL,
            openPasswordManager = passwordManager,
            suggest = suggest,
            completeWord = completeWord,
            openDraft = if (active && info != null && VoiceIme.safeField(info.inputType))
                { { if (currentUiSession(generation)) showDraft() } } else null,
            backspaceSelection = backspaceSelection)
        val cls = (info?.inputType ?: 0) and InputType.TYPE_MASK_CLASS
        panel.reset(active && info != null && VoiceIme.safeField(info.inputType),
            cls in listOf(InputType.TYPE_CLASS_NUMBER, InputType.TYPE_CLASS_PHONE, InputType.TYPE_CLASS_DATETIME), label,
            allowEmoji = active && info != null && info.inputType != InputType.TYPE_NULL)
        show(panel.view)
    }
    private fun showVoice() {
        val info = currentInputEditorInfo ?: return
        if (!active || !VoiceIme.safeField(info.inputType)) return
        invalidateUiSession()
        val generation = uiGeneration
        draft?.clear(); draft = null; backspaceSelection = null
        voice?.clear()
        voice = VoicePanel(this, { text ->
            val current = currentInputEditorInfo
            current != null && VoiceIme.safeField(current.inputType) && commit(text, generation)
        }, { if (currentUiSession(generation)) showTyping() })
        show(voice!!.view)
        voice?.startFromMicTap()
    }
    private fun showDraft() {
        val info = currentInputEditorInfo ?: return
        // An unmasked private preview is not suitable for password or raw-key fields.
        if (!active || !VoiceIme.safeField(info.inputType)) return
        invalidateUiSession()
        voice?.clear(); voice = null
        draft?.clear(); backspaceSelection = null
        val generation = uiGeneration
        draft = PrivateDraftPanel(this, KeyboardOptions.load(this), { text ->
            val current = currentInputEditorInfo
            if (!currentUiSession(generation) || current == null || !VoiceIme.safeField(current.inputType)) {
                DraftInsertionResult.UNAVAILABLE
            } else {
                val connection = currentInputConnection
                if (connection == null) DraftInsertionResult.UNAVAILABLE
                else try {
                    // One direct call only: no per-key, clipboard or editor-action fallback.
                    if (connection.commitText(text, 1)) DraftInsertionResult.INSERTED
                    else DraftInsertionResult.UNCONFIRMED
                } catch (_: Exception) { DraftInsertionResult.UNCONFIRMED }
            }
        }, { if (currentUiSession(generation)) showTyping() })
        show(draft!!.view)
    }
    private fun show(content: View) {
        root?.removeAllViews()
        root?.addView(ScrollView(this).apply { addView(content) }, FrameLayout.LayoutParams(-1, -2))
    }
    private fun clear() {
        invalidateUiSession()
        active = false; backspaceSelection = null; voice?.clear(); voice = null; draft?.clear(); draft = null; root?.removeAllViews()
    }
    override fun onFinishInputView(finishingInput: Boolean) { clear(); super.onFinishInputView(finishingInput) }
    override fun onFinishInput() { clear(); super.onFinishInput() }
    override fun onWindowHidden() { clear(); super.onWindowHidden() }
    override fun onDestroy() { clear(); super.onDestroy() }
}
