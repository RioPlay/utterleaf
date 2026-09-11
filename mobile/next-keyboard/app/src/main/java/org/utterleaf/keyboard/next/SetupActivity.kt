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
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import org.utterleaf.keyboard.next.settings.PrivacyPreferences

class SetupActivity : Activity() {
    private lateinit var privacy: PrivacyPreferences
    private lateinit var toggle: Button
    private lateinit var retry: Button
    private lateinit var status: TextView
    private val listener: (PrivacyPreferences.State) -> Unit = { render(it) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        privacy = PrivacyPreferences.get(this)
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
        text(R.string.privacy_description)
        toggle = button(R.string.incognito_on) { privacy.setIncognito(!privacy.state.incognito) }
        status = text(R.string.privacy_loading)
        retry = button(R.string.retry_save) { privacy.retry() }
        text(R.string.learning_unavailable)
        button(R.string.reset_preferences) {
            privacy.resetPreferences()
            android.widget.Toast.makeText(this, R.string.reset_description, android.widget.Toast.LENGTH_LONG).show()
        }
        val scroll = ScrollView(this).apply { addView(column) }
        ViewCompat.setOnApplyWindowInsetsListener(scroll) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        setContentView(scroll)
    }

    override fun onStart() { super.onStart(); privacy.observe(listener) }
    override fun onStop() { privacy.removeObserver(listener); super.onStop() }

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
