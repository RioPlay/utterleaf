package org.utterleaf.keyboard

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.view.ViewCompat

/** Synthetic practice surface for the isolated full-IME build, not release onboarding. */
class FoundationActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        val page = ScrollView(this).apply { isFillViewport = true; addView(panel) }
        page.applyContentInsets((20 * resources.displayMetrics.density).toInt())
        panel.addView(TextView(this).apply {
            text = "Utterleaf foundation experiment\nSynthetic input only. Voice, correction and power controls are not ready."
            textSize = 20f
        })
        panel.addView(Button(this).apply {
            text = "Enable test keyboard"
            setOnClickListener { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) }
        })
        panel.addView(Button(this).apply {
            text = "Choose keyboard"
            setOnClickListener { getSystemService(InputMethodManager::class.java).showInputMethodPicker() }
        })
        panel.addView(Button(this).apply {
            setText(com.android.inputmethod.latin.R.string.comfort_title)
            setOnClickListener { startActivity(Intent(this@FoundationActivity, ComfortActivity::class.java)) }
        })
        for (label in listOf("First practice field", "Second practice field")) {
            panel.addView(EditText(this).apply {
                hint = label
                contentDescription = label
                isSaveEnabled = false
                importantForAutofill = android.view.View.IMPORTANT_FOR_AUTOFILL_NO
            })
        }
        panel.addView(Button(this).apply {
            setText(com.android.inputmethod.latin.R.string.notices_title)
            setOnClickListener { startActivity(Intent(this@FoundationActivity, NoticesActivity::class.java)) }
        })
        setContentView(page)
        ViewCompat.requestApplyInsets(page)
    }
}
