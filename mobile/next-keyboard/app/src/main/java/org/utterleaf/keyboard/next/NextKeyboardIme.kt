package org.utterleaf.keyboard.next

import android.content.Intent
import android.content.res.Configuration
import android.inputmethodservice.InputMethodService
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import org.utterleaf.keyboard.next.core.EditorGateway
import org.utterleaf.keyboard.next.core.Outcome
import org.utterleaf.keyboard.next.core.SelectionUpdate
import org.utterleaf.keyboard.next.settings.PrivacyPreferences
import org.utterleaf.keyboard.next.ui.KeyAction
import org.utterleaf.keyboard.next.ui.KeyboardSurface

/** Lifecycle adapter. All owned editor operations go through the main-thread gateway. */
class NextKeyboardIme : InputMethodService() {
    internal val gateway = EditorGateway()
    private lateinit var privacy: PrivacyPreferences
    private var surface: KeyboardSurface? = null
    private var privacyButton: Button? = null
    private var status: TextView? = null
    private var active = false
    private var shift = false
    private var symbols = false
    private var imeOptions = 0
    private val privacyListener: (PrivacyPreferences.State) -> Unit = { state ->
        val previous = gateway.effectiveIncognito()
        gateway.setManualIncognito(state.incognito)
        if (previous != gateway.effectiveIncognito()) surface?.cancelPointers()
        refresh()
    }

    override fun onCreate() {
        super.onCreate()
        window?.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        privacy = PrivacyPreferences.get(this)
        privacy.observe(privacyListener)
    }

    override fun onEvaluateFullscreenMode() = false

    override fun onEvaluateInputViewShown(): Boolean {
        val shown = super.onEvaluateInputViewShown()
        if (!shown) retire()
        return shown
    }

    override fun onCreateInputView(): View {
        surface?.cancelPointers()
        window?.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xff181d1b.toInt())
            setPadding(dp(4), 0, dp(4), 0)
        }
        val bar = LinearLayout(this)
        privacyButton = Button(this).also { button ->
            button.isAllCaps = false
            button.textSize = 13f
            button.setOnClickListener {
                if (gateway.currentPolicy()?.forcedIncognito != true) {
                    surface?.cancelPointers()
                    privacy.setIncognito(!privacy.state.incognito)
                }
            }
            bar.addView(button, LinearLayout.LayoutParams(0, dp(48), 1f))
        }
        bar.addView(Button(this).apply {
            setText(R.string.settings); isAllCaps = false; textSize = 13f
            setOnClickListener {
                retire()
                requestHideSelf(0)
                startActivity(Intent(this@NextKeyboardIme, SetupActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
        }, LinearLayout.LayoutParams(0, dp(48), 1f))
        bar.addView(Button(this).apply {
            text = "🌐"; contentDescription = getString(R.string.switch_keyboard)
            setOnClickListener { surface?.cancelPointers(); getSystemService(InputMethodManager::class.java).showInputMethodPicker() }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
        root.addView(bar)
        val keyboard = KeyboardSurface(this)
        surface = keyboard
        keyboard.onKey = { action ->
            if (surface === keyboard && active && isInputViewShown && keyboard.isShown) dispatch(action)
        }
        root.addView(keyboard, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(236)))
        status = TextView(this).apply {
            setTextColor(0xffb5c3b7.toInt()); textSize = 12f
            gravity = android.view.Gravity.CENTER
            setPadding(0, dp(3), 0, dp(3))
        }.also { root.addView(it) }
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.navigationBars())
            view.setPadding(dp(4) + bars.left, 0, dp(4) + bars.right, bars.bottom)
            insets
        }
        refresh()
        return root
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        retire()
        super.onStartInput(attribute, restarting)
        open(attribute)
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        retire()
        super.onStartInputView(info, restarting)
        open(info)
        active = gateway.currentToken() != null
        refresh()
    }

    private fun open(info: EditorInfo?) {
        imeOptions = info?.imeOptions ?: 0
        gateway.open(if (info == null) null else currentInputConnection, info?.inputType,
            imeOptions, info?.initialSelStart ?: -1, info?.initialSelEnd ?: -1)
        refresh()
    }

    override fun onUpdateSelection(oldSelStart: Int, oldSelEnd: Int, newSelStart: Int, newSelEnd: Int,
        candidatesStart: Int, candidatesEnd: Int) {
        if (gateway.updateSelection(newSelStart, newSelEnd, candidatesStart, candidatesEnd) == SelectionUpdate.EXTERNAL) {
            surface?.cancelPointers()
        }
    }

    // Framework defaults finish composing through the current connection. N1 owns no
    // composition, so override those defaults instead of performing an unscoped write.
    override fun onFinishInputView(finishingInput: Boolean) = retire()
    override fun onFinishInput() = retire()
    override fun onFinishCandidatesView(finishingInput: Boolean) = retire()
    override fun onWindowHidden() { retire(); super.onWindowHidden() }
    override fun onUnbindInput() { retire(); super.onUnbindInput() }
    override fun onConfigurationChanged(newConfig: Configuration) { retire(); super.onConfigurationChanged(newConfig) }
    override fun onDestroy() {
        retire()
        privacy.removeObserver(privacyListener)
        surface = null; privacyButton = null; status = null
        super.onDestroy()
    }

    private fun retire() {
        active = false
        surface?.cancelPointers()
        gateway.retire()
        shift = false; symbols = false
    }

    private fun dispatch(action: KeyAction) {
        val token = gateway.currentToken() ?: return
        val outcome = when (action.kind) {
            KeyAction.Kind.SHIFT -> { shift = !shift; refresh(); return }
            KeyAction.Kind.SYMBOLS -> { symbols = !symbols; shift = false; refresh(); return }
            KeyAction.Kind.BACKSPACE -> gateway.backspace(token)
            KeyAction.Kind.ENTER -> gateway.enter(token)
            KeyAction.Kind.SPACE -> gateway.commit(token, " ")
            KeyAction.Kind.PUNCTUATION -> gateway.commit(token, action.value)
            KeyAction.Kind.TEXT -> gateway.commit(token, if (shift) action.value.uppercase(java.util.Locale.ROOT) else action.value)
        }
        if (outcome == Outcome.APPLIED && action.kind == KeyAction.Kind.TEXT && shift) {
            shift = false; refresh()
        }
        if (outcome != Outcome.APPLIED) {
            status?.setText(R.string.action_unavailable)
            surface?.announceForAccessibility(getString(R.string.action_unavailable))
        }
    }

    private fun refresh() {
        if (!::privacy.isInitialized) return
        val state = privacy.state
        val forced = gateway.currentPolicy()?.forcedIncognito == true
        privacyButton?.apply {
            isEnabled = state.ready && !state.saving && !forced
            setText(when {
                forced -> R.string.incognito_required
                !state.ready -> R.string.privacy_loading
                state.saving -> R.string.incognito_pending
                state.failed -> R.string.incognito_unsaved
                state.incognito -> R.string.incognito_on
                else -> R.string.incognito_off
            })
        }
        val action = imeOptions and EditorInfo.IME_MASK_ACTION
        val enter = if (imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION != 0) R.string.enter_newline else when (action) {
            EditorInfo.IME_ACTION_DONE -> R.string.enter_done
            EditorInfo.IME_ACTION_GO -> R.string.enter_go
            EditorInfo.IME_ACTION_NEXT -> R.string.enter_next
            EditorInfo.IME_ACTION_SEARCH -> R.string.enter_search
            EditorInfo.IME_ACTION_SEND -> R.string.enter_send
            EditorInfo.IME_ACTION_PREVIOUS -> R.string.enter_previous
            else -> R.string.enter_newline
        }
        surface?.bindState(shift, symbols, getString(enter))
        status?.setText(if (gateway.currentToken() == null) R.string.unsupported_field else R.string.literal_status)
    }

    private fun dp(value: Int) = kotlin.math.ceil(value * resources.displayMetrics.density).toInt()
}
