package org.utterleaf.keyboard.next

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.CheckBox
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import org.utterleaf.keyboard.next.settings.PrivacyPreferences
import org.utterleaf.keyboard.next.settings.TypingPreferences

class SetupActivity : Activity() {
    private lateinit var privacy: PrivacyPreferences
    private lateinit var toggle: Button
    private lateinit var retry: Button
    private lateinit var status: TextView
    private val listener: (PrivacyPreferences.State) -> Unit = { render(it) }
    private lateinit var typing: TypingPreferences
    private lateinit var numberRow: CheckBox
    private lateinit var accentLongPress: CheckBox
    private lateinit var applyTyping: Button
    private lateinit var discardTyping: Button
    private lateinit var resetTyping: Button
    private lateinit var typingStatus: TextView
    private var renderingTyping = false
    private val typingListener: (TypingPreferences.State) -> Unit = { renderTyping(it) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        privacy = PrivacyPreferences.get(this)
        typing = TypingPreferences.get(this)
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(20), dp(20), dp(20))
        }
        fun text(resource: Int, size: Float = 16f) = TextView(this).also {
            it.setText(resource); it.textSize = size
            it.setPadding(0, dp(8), 0, dp(8)); column.addView(it)
        }
        fun button(resource: Int, action: () -> Unit) = Button(this).also {
            it.setText(resource); it.minHeight = dp(48)
            it.setOnClickListener { action() }; column.addView(it)
        }
        text(R.string.core_title, 26f)
        text(R.string.core_description)
        button(R.string.enable_keyboard) { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) }
        button(R.string.choose_keyboard) { getSystemService(InputMethodManager::class.java).showInputMethodPicker() }
        text(R.string.typing_preferences, 20f)
        numberRow = CheckBox(this).apply {
            id = R.id.typing_number_row; setText(R.string.number_row); minHeight = dp(48)
            setOnCheckedChangeListener { _, checked ->
                if (!renderingTyping) typing.edit(typing.state.draft.copy(numberRow = checked))
            }
        }.also { column.addView(it) }
        accentLongPress = CheckBox(this).apply {
            id = R.id.typing_accent_long_press; setText(R.string.accent_long_press); minHeight = dp(48)
            setOnCheckedChangeListener { _, checked ->
                if (!renderingTyping) typing.edit(typing.state.draft.copy(accentLongPress = checked))
            }
        }.also { column.addView(it) }
        text(R.string.accent_tap_help)
        typingStatus = text(R.string.typing_loading)
        applyTyping = button(R.string.apply_typing) { typing.apply() }.apply { id = R.id.typing_apply }
        discardTyping = button(R.string.discard_typing) { typing.discard() }.apply { id = R.id.typing_discard }
        text(R.string.privacy_description)
        toggle = button(R.string.incognito_on) { privacy.setIncognito(!privacy.state.incognito) }
        status = text(R.string.privacy_loading)
        retry = button(R.string.retry_save) { privacy.retry() }
        text(R.string.learning_unavailable)
        resetTyping = button(R.string.reset_preferences) {
            typing.reset()
            privacy.resetPreferences()
        }.apply { id = R.id.typing_reset }
        text(R.string.reset_description)
        val scroll = ScrollView(this).apply { addView(column) }
        ViewCompat.setOnApplyWindowInsetsListener(scroll) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        setContentView(scroll)
    }

    override fun onStart() { super.onStart(); privacy.observe(listener); typing.observe(typingListener) }
    override fun onStop() {
        privacy.removeObserver(listener); typing.removeObserver(typingListener)
        if (!isChangingConfigurations) typing.discard()
        super.onStop()
    }

    private fun renderTyping(state: TypingPreferences.State) {
        renderingTyping = true
        numberRow.isChecked = state.draft.numberRow
        accentLongPress.isChecked = state.draft.accentLongPress
        renderingTyping = false
        val enabled = state.ready && !state.saving
        numberRow.isEnabled = enabled; accentLongPress.isEnabled = enabled
        applyTyping.isEnabled = enabled && (state.draft != state.saved || state.failed)
        discardTyping.isEnabled = enabled && state.draft != state.saved
        resetTyping.isEnabled = enabled
        typingStatus.setText(when {
            !state.ready -> R.string.typing_loading
            state.saving -> R.string.typing_saving
            state.failed -> R.string.typing_save_failed
            state.draft != state.saved -> R.string.typing_unsaved
            else -> R.string.privacy_saved
        })
    }

    private fun render(state: PrivacyPreferences.State) {
        toggle.isEnabled = state.ready && !state.saving
        toggle.setText(when {
            !state.ready -> R.string.privacy_loading
            state.saving -> R.string.incognito_pending
            state.failed -> R.string.incognito_unsaved
            state.incognito -> R.string.incognito_on
            else -> R.string.incognito_off
        })
        status.setText(when {
            !state.ready -> R.string.privacy_loading
            state.saving -> R.string.incognito_pending
            state.failed -> R.string.privacy_failed
            else -> R.string.privacy_saved
        })
        retry.visibility = if (state.failed) android.view.View.VISIBLE else android.view.View.GONE
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
