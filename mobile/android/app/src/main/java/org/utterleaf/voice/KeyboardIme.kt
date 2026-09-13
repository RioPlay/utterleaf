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
        active = false; voice?.clear(); draft?.clear(); draft = null
        // Clear the old local query/preview at the field boundary, even if the
        // platform never follows this callback with onStartInputView.
        root?.removeAllViews()
    }
    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        active = info != null && (info.inputType != InputType.TYPE_NULL || KeyboardOptions.load(this).terminal)
        showTyping()
        if (!active) requestHideSelf(0)
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
        val panel = TypingPanel(this, KeyboardOptions.load(this),
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
                if (shift && !ctrl && !alt && info?.inputType != InputType.TYPE_NULL && code in listOf(
                        KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_UP,
                        KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_MOVE_HOME, KeyEvent.KEYCODE_MOVE_END))
                    TerminalInput.select(currentInputConnection, code)
                else TerminalInput.send(currentInputConnection, code, ctrl, alt, shift) },
            { text, ctrl, alt -> currentUiSession(generation) &&
                TerminalInput.printable(currentInputConnection, text, ctrl, alt,
                    forceKeyEvents = currentInputEditorInfo?.inputType == InputType.TYPE_NULL) },
            editorAction = { command -> currentUiSession(generation) &&
                EditorActions.perform(currentInputConnection, command, currentInputEditorInfo?.inputType) },
            openDraft = if (active && info != null && VoiceIme.safeField(info.inputType))
                { { if (currentUiSession(generation)) showDraft() } } else null)
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
        draft?.clear(); draft = null
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
        draft?.clear()
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
        active = false; voice?.clear(); voice = null; draft?.clear(); draft = null; root?.removeAllViews()
    }
    override fun onFinishInputView(finishingInput: Boolean) { clear(); super.onFinishInputView(finishingInput) }
    override fun onFinishInput() { clear(); super.onFinishInput() }
    override fun onWindowHidden() { clear(); super.onWindowHidden() }
    override fun onDestroy() { clear(); super.onDestroy() }
}
