package org.utterleaf.voice

import android.inputmethodservice.InputMethodService
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager

class VoiceIme : InputMethodService() {
    private var panel: VoicePanel? = null
    private var allowed = false
    private var capabilities = EditorCapabilities.resolve(null)
    override fun onEvaluateFullscreenMode() = false
    override fun onCreateInputView(): View {
        window.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        panel = VoicePanel(this, { text ->
            val current = currentInputEditorInfo
            allowed && EditorCapabilities.from(current).dictation &&
                TerminalInput.printable(currentInputConnection, text)
        }, { returnKeyboard() })
        return panel!!.view.also { Ui.applySystemInsets(it, navigationOnly = true) }
    }
    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        panel?.clear()
        capabilities = EditorCapabilities.from(attribute)
        allowed = capabilities.dictation
    }
    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        panel?.clear()
        capabilities = EditorCapabilities.from(info)
        allowed = capabilities.dictation
        panel?.view?.visibility = if (allowed) View.VISIBLE else View.GONE
        if (!allowed) { requestHideSelf(0); returnKeyboard() }
    }
    private fun returnKeyboard() {
        if (android.os.Build.VERSION.SDK_INT < 28 || !switchToPreviousInputMethod())
            (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
    }
    private fun clearEditor() {
        allowed = false
        capabilities = EditorCapabilities.resolve(null)
        panel?.clear()
    }
    override fun onFinishInputView(finishingInput: Boolean) { clearEditor(); super.onFinishInputView(finishingInput) }
    override fun onFinishInput() { clearEditor(); super.onFinishInput() }
    override fun onWindowHidden() { clearEditor(); super.onWindowHidden() }
    override fun onDestroy() { clearEditor(); super.onDestroy() }
    companion object {
        fun safeField(type: Int): Boolean = EditorCapabilities.resolve(type).dictation
    }
}
