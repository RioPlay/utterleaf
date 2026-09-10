package org.utterleaf.voice

import android.content.Intent
import android.inputmethodservice.InputMethodService
import android.text.InputType
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.FrameLayout
import android.widget.ScrollView

/** Typing stays available without a model or microphone permission. */
class KeyboardIme : InputMethodService() {
    private var root: FrameLayout? = null
    private var voice: VoicePanel? = null
    private var active = false
    /** Monotonically identifies the panel and editor session currently on screen. */
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
        active = false; voice?.clear()
    }
    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        active = info != null && (info.inputType != InputType.TYPE_NULL || KeyboardOptions.load(this).terminal)
        showTyping()
        if (!active) requestHideSelf(0)
    }
    private fun commit(value: String): Boolean {
        if (!active) return false
        return TerminalInput.printable(currentInputConnection, value,
            forceKeyEvents = currentInputEditorInfo?.inputType == InputType.TYPE_NULL)
    }
    private fun keyEvent(code: Int) {
        if (!active) return
        TerminalInput.send(currentInputConnection, code)
    }
    private fun showTyping() {
        invalidateUiSession()
        voice?.clear(); voice = null
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
            { value -> if (currentUiSession(generation)) commit(value) else false },
            { if (currentUiSession(generation)) keyEvent(KeyEvent.KEYCODE_DEL) },
            { if (currentUiSession(generation)) {
                if (info?.inputType == InputType.TYPE_NULL) TerminalInput.send(currentInputConnection, KeyEvent.KEYCODE_ENTER)
                else if (useAction) currentInputConnection?.performEditorAction(action) else commit("\n")
            }; Unit },
            { left -> if (currentUiSession(generation)) keyEvent(if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT) },
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
                TerminalInput.send(currentInputConnection, code, ctrl, alt, shift) },
            { text, ctrl, alt -> currentUiSession(generation) &&
                TerminalInput.printable(currentInputConnection, text, ctrl, alt,
                    forceKeyEvents = currentInputEditorInfo?.inputType == InputType.TYPE_NULL) })
        val cls = (info?.inputType ?: 0) and InputType.TYPE_MASK_CLASS
        panel.reset(active && info != null && VoiceIme.safeField(info.inputType),
            cls in listOf(InputType.TYPE_CLASS_NUMBER, InputType.TYPE_CLASS_PHONE, InputType.TYPE_CLASS_DATETIME), label)
        show(panel.view)
    }
    private fun showVoice() {
        val info = currentInputEditorInfo ?: return
        if (!active || !VoiceIme.safeField(info.inputType)) return
        invalidateUiSession()
        val generation = uiGeneration
        voice?.clear()
        voice = VoicePanel(this, { text ->
            val current = currentInputEditorInfo
            currentUiSession(generation) && current != null && VoiceIme.safeField(current.inputType) && commit(text)
        }, { if (currentUiSession(generation)) showTyping() })
        show(voice!!.view)
    }
    private fun show(content: View) {
        root?.removeAllViews()
        root?.addView(ScrollView(this).apply { addView(content) }, FrameLayout.LayoutParams(-1, -2))
    }
    private fun clear() {
        invalidateUiSession()
        active = false; voice?.clear(); voice = null; root?.removeAllViews()
    }
    override fun onFinishInputView(finishingInput: Boolean) { clear(); super.onFinishInputView(finishingInput) }
    override fun onFinishInput() { clear(); super.onFinishInput() }
    override fun onWindowHidden() { clear(); super.onWindowHidden() }
    override fun onDestroy() { clear(); super.onDestroy() }
}
