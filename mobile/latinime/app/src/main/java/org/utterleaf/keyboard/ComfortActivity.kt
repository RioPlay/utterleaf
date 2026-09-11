package org.utterleaf.keyboard

import android.app.Activity
import android.app.AlertDialog
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.*
import androidx.core.view.ViewCompat
import com.android.inputmethod.latin.R

/** Draft controls are separate from persisted preferences and ephemeral practice text. */
class ComfortActivity : Activity() {
    private lateinit var preferences: ComfortPreferences
    private lateinit var status: TextView
    private lateinit var light: CheckBox
    private lateinit var sound: CheckBox
    private lateinit var vibration: CheckBox
    private lateinit var preview: CheckBox
    private lateinit var height: SeekBar
    private lateinit var bottom: SeekBar
    private lateinit var practice: EditText
    private var binding = false
    private var draft = ComfortOptions()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN or
            WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        preferences = ComfortPreferences(this)
        draft = preferences.read()
        savedInstanceState?.let {
            draft = draft.copy(lightTheme = it.getBoolean("light", draft.lightTheme),
                heightPercent = it.getInt("height", draft.heightPercent).coerceIn(75, 135),
                bottomSpaceDp = it.getInt("bottom", draft.bottomSpaceDp).coerceIn(0, 64),
                sound = it.getBoolean("sound", draft.sound), vibration = it.getBoolean("vibration", draft.vibration),
                keyPreview = it.getBoolean("preview", draft.keyPreview))
        }
        val content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val page = ScrollView(this).apply { isFillViewport = true; addView(content) }
        val padding = dp(20)
        page.applyContentInsets(padding)
        fun text(resource: Int, size: Float = 16f) = TextView(this).apply {
            setText(resource); textSize = size; setPadding(0, dp(8), 0, dp(8)); content.addView(this)
        }
        fun button(resource: Int, action: () -> Unit) = Button(this).apply {
            setText(resource); isAllCaps = false; minHeight = dp(48)
            setOnClickListener { action() }; content.addView(this)
        }
        fun toggle(resource: Int, update: (Boolean) -> Unit) = CheckBox(this).apply {
            setText(resource); minHeight = dp(48)
            setOnCheckedChangeListener { _, checked -> if (!binding) update(checked) }
            content.addView(this)
        }
        fun slider(resource: Int, minimum: Int, maximum: Int, update: (Int) -> Unit): SeekBar {
            val label = TextView(this).apply { content.addView(this) }
            return SeekBar(this).apply {
                minimumHeight = dp(48); max = maximum - minimum
                setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                    override fun onProgressChanged(bar: SeekBar, progress: Int, fromUser: Boolean) {
                        val value = progress + minimum
                        val description = getString(resource, value)
                        label.text = description
                        bar.contentDescription = description
                        if (!binding && fromUser) update(value)
                    }
                    override fun onStartTrackingTouch(bar: SeekBar) = Unit
                    override fun onStopTrackingTouch(bar: SeekBar) = Unit
                })
                // SeekBar may not notify when setting its existing zero value.
                contentDescription = getString(resource, minimum)
                label.text = contentDescription
                content.addView(this)
            }
        }
        text(R.string.comfort_title, 26f)
        text(R.string.comfort_description)
        text(R.string.comfort_appearance, 20f)
        light = toggle(R.string.comfort_light) { draft = draft.copy(lightTheme = it) }
        height = slider(R.string.comfort_height, 75, 135) { draft = draft.copy(heightPercent = it) }
        bottom = slider(R.string.comfort_bottom, 0, 64) { draft = draft.copy(bottomSpaceDp = it) }
        text(R.string.comfort_feedback, 20f)
        sound = toggle(R.string.comfort_sound) { draft = draft.copy(sound = it) }
        vibration = toggle(R.string.comfort_vibration) { draft = draft.copy(vibration = it) }
        preview = toggle(R.string.comfort_preview) { draft = draft.copy(keyPreview = it) }
        button(R.string.comfort_apply) {
            preferences.save(draft)
            status.setText(R.string.comfort_saved)
            if (getSystemService(InputMethodManager::class.java).isActive(practice)) {
                getSystemService(InputMethodManager::class.java).restartInput(practice)
            }
        }
        button(R.string.comfort_discard) {
            draft = preferences.read(); bind(); status.setText(R.string.comfort_discarded)
        }
        button(R.string.comfort_reset) {
            val dialog = AlertDialog.Builder(this).setTitle(R.string.comfort_reset)
                .setMessage(R.string.comfort_reset_description)
                .setNegativeButton(android.R.string.cancel, null)
                .setPositiveButton(R.string.comfort_reset_confirm) { _, _ ->
                    preferences.reset(); draft = preferences.read(); bind(); status.setText(R.string.comfort_reset_done)
                    if (getSystemService(InputMethodManager::class.java).isActive(practice)) {
                        getSystemService(InputMethodManager::class.java).restartInput(practice)
                    }
                }.create()
            dialog.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
            dialog.show()
        }
        status = text(R.string.comfort_status).apply { accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE }
        text(R.string.comfort_practice_title, 20f)
        practice = EditText(this).apply {
            setHint(R.string.comfort_practice_hint)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE
            minLines = 2; isSaveEnabled = false
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
            content.addView(this)
        }
        bind()
        setContentView(page)
        ViewCompat.requestApplyInsets(page)
    }

    private fun bind() {
        binding = true
        try {
            light.isChecked = draft.lightTheme
            height.progress = draft.heightPercent - 75
            bottom.progress = draft.bottomSpaceDp
            sound.isChecked = draft.sound
            vibration.isChecked = draft.vibration
            preview.isChecked = draft.keyPreview
        } finally { binding = false }
    }

    override fun onSaveInstanceState(state: Bundle) {
        state.putBoolean("light", draft.lightTheme); state.putInt("height", draft.heightPercent)
        state.putInt("bottom", draft.bottomSpaceDp); state.putBoolean("sound", draft.sound)
        state.putBoolean("vibration", draft.vibration); state.putBoolean("preview", draft.keyPreview)
        super.onSaveInstanceState(state)
    }

    override fun onPause() {
        if (::practice.isInitialized) practice.text.clear()
        super.onPause()
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
