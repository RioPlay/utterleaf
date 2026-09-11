package org.utterleaf.keyboard

import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import android.preference.PreferenceManager
import com.android.inputmethod.keyboard.KeyboardTheme
import com.android.inputmethod.latin.settings.DebugSettings
import com.android.inputmethod.latin.settings.Settings
import kotlin.math.roundToInt

internal data class ComfortOptions(
    val lightTheme: Boolean = false,
    val heightPercent: Int = 100,
    val bottomSpaceDp: Int = 0,
    val sound: Boolean = false,
    val vibration: Boolean = true,
    val keyPreview: Boolean = true
)

/** Explicit preferences only. Reset never clears the preference file or touches user assets. */
internal class ComfortPreferences(private val preferences: SharedPreferences) {
    constructor(context: Context) : this(PreferenceManager.getDefaultSharedPreferences(context))

    private val themeKey = KeyboardTheme.getPreferenceKey(Build.VERSION.SDK_INT)

    private fun <T> readOr(default: T, read: () -> T): T = try { read() }
        catch (_: ClassCastException) { default }

    fun read(): ComfortOptions {
        val scale = readOr(1f) { preferences.getFloat(DebugSettings.PREF_KEYBOARD_HEIGHT_SCALE, 1f) }
        return ComfortOptions(
            lightTheme = readOr(false) { preferences.getString(themeKey, null) == KeyboardTheme.THEME_ID_LXX_LIGHT.toString() },
            heightPercent = if (scale.isFinite()) (scale.coerceIn(.75f, 1.35f) * 100).roundToInt() else 100,
            bottomSpaceDp = readOr(0) { preferences.getInt(BOTTOM_SPACE, 0) }.coerceIn(0, 64),
            sound = readOr(false) { preferences.getBoolean(Settings.PREF_SOUND_ON, false) },
            vibration = readOr(true) { preferences.getBoolean(Settings.PREF_VIBRATE_ON, true) },
            keyPreview = readOr(true) { preferences.getBoolean(Settings.PREF_POPUP_ON, true) }
        )
    }

    fun save(options: ComfortOptions) {
        preferences.edit()
            .putString(themeKey, (if (options.lightTheme) KeyboardTheme.THEME_ID_LXX_LIGHT else KeyboardTheme.THEME_ID_LXX_DARK).toString())
            .putFloat(DebugSettings.PREF_KEYBOARD_HEIGHT_SCALE, options.heightPercent.coerceIn(75, 135) / 100f)
            .putBoolean(DebugSettings.PREF_RESIZE_KEYBOARD, options.heightPercent.coerceIn(75, 135) != 100)
            .putInt(BOTTOM_SPACE, options.bottomSpaceDp.coerceIn(0, 64))
            .putBoolean(Settings.PREF_SOUND_ON, options.sound)
            .putBoolean(Settings.PREF_VIBRATE_ON, options.vibration)
            .putBoolean(Settings.PREF_POPUP_ON, options.keyPreview)
            .apply()
    }

    fun reset() {
        preferences.edit().remove(themeKey).remove(DebugSettings.PREF_KEYBOARD_HEIGHT_SCALE)
            .remove(DebugSettings.PREF_RESIZE_KEYBOARD)
            .remove(BOTTOM_SPACE).remove(Settings.PREF_SOUND_ON).remove(Settings.PREF_VIBRATE_ON)
            .remove(Settings.PREF_POPUP_ON).apply()
    }

    private companion object { const val BOTTOM_SPACE = "utterleaf_bottom_space_dp" }
}
