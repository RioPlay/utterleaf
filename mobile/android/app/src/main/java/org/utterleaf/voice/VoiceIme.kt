package org.utterleaf.voice

import android.inputmethodservice.InputMethodService
import android.text.InputType
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager

class VoiceIme : InputMethodService() {
    private var panel: VoicePanel? = null
    private var allowed = false
    override fun onEvaluateFullscreenMode() = false
    override fun onCreateInputView(): View {
        window.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        panel = VoicePanel(this, { text ->
            allowed && currentInputConnection?.commitText(text, 1) == true
        }, { returnKeyboard() })
        return panel!!.view.also { Ui.applySystemInsets(it, navigationOnly = true) }
    }
    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        panel?.clear()
        allowed = attribute != null && safeField(attribute.inputType)
    }
    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        panel?.clear()
        allowed = info != null && safeField(info.inputType)
        panel?.view?.visibility = if (allowed) View.VISIBLE else View.GONE
        if (!allowed) { requestHideSelf(0); returnKeyboard() }
    }
    private fun returnKeyboard() {
        if (android.os.Build.VERSION.SDK_INT < 28 || !switchToPreviousInputMethod())
            (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
    }
    override fun onFinishInputView(finishingInput: Boolean) { panel?.clear(); super.onFinishInputView(finishingInput) }
    override fun onFinishInput() { allowed = false; panel?.clear(); super.onFinishInput() }
    override fun onWindowHidden() { panel?.clear(); super.onWindowHidden() }
    override fun onDestroy() { panel?.clear(); super.onDestroy() }
    companion object {
        fun safeField(type: Int): Boolean {
            val cls = type and InputType.TYPE_MASK_CLASS
            val variant = type and InputType.TYPE_MASK_VARIATION
            if (cls == InputType.TYPE_NULL) return false
            return !(cls == InputType.TYPE_CLASS_TEXT && variant in listOf(
                InputType.TYPE_TEXT_VARIATION_PASSWORD, InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
                InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD)) &&
                !(cls == InputType.TYPE_CLASS_NUMBER && variant == InputType.TYPE_NUMBER_VARIATION_PASSWORD)
        }
    }
}
