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
    override fun onEvaluateFullscreenMode() = false
    override fun onCreateInputView(): View {
        window.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        return FrameLayout(this).also { root = it }
    }
    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        active = false; voice?.clear()
    }
    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        active = info != null && info.inputType != InputType.TYPE_NULL
        showTyping()
        if (!active) requestHideSelf(0)
    }
    private fun commit(value: String) = active && currentInputConnection?.commitText(value, 1) == true
    private fun keyEvent(code: Int) {
        if (!active) return
        val connection = currentInputConnection ?: return
        connection.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, code))
        connection.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, code))
    }
    private fun showTyping() {
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
        val panel = TypingPanel(this, KeyboardOptions.load(this), ::commit,
            { keyEvent(KeyEvent.KEYCODE_DEL) },
            { if (active) { if (useAction) currentInputConnection?.performEditorAction(action) else commit("\n") }; Unit },
            { left -> keyEvent(if (left) KeyEvent.KEYCODE_DPAD_LEFT else KeyEvent.KEYCODE_DPAD_RIGHT) },
            { showVoice() },
            {
                voice?.clear(); requestHideSelf(0)
                startActivity(Intent(this, KeyboardSettingsActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            },
            { (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker() })
        val cls = (info?.inputType ?: 0) and InputType.TYPE_MASK_CLASS
        panel.reset(active && info != null && VoiceIme.safeField(info.inputType),
            cls in listOf(InputType.TYPE_CLASS_NUMBER, InputType.TYPE_CLASS_PHONE, InputType.TYPE_CLASS_DATETIME), label)
        show(panel.view)
    }
    private fun showVoice() {
        val info = currentInputEditorInfo ?: return
        if (!active || !VoiceIme.safeField(info.inputType)) return
        voice?.clear()
        voice = VoicePanel(this, { text ->
            val current = currentInputEditorInfo
            active && current != null && VoiceIme.safeField(current.inputType) && commit(text)
        }, { showTyping() })
        show(voice!!.view)
    }
    private fun show(content: View) {
        root?.removeAllViews()
        root?.addView(ScrollView(this).apply { addView(content) }, FrameLayout.LayoutParams(-1, -2))
    }
    private fun clear() { active = false; voice?.clear(); voice = null; root?.removeAllViews() }
    override fun onFinishInputView(finishingInput: Boolean) { clear(); super.onFinishInputView(finishingInput) }
    override fun onFinishInput() { clear(); super.onFinishInput() }
    override fun onWindowHidden() { clear(); super.onWindowHidden() }
    override fun onDestroy() { clear(); super.onDestroy() }
}
