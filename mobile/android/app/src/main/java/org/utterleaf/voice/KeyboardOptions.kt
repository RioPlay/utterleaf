package org.utterleaf.voice

import android.content.Context
import android.content.res.Configuration

enum class KeyboardAlignment(val stored: String) {
    FULL("full"), LEFT("left"), RIGHT("right");

    companion object {
        fun fromStored(value: String?) = entries.firstOrNull { it.stored == value } ?: FULL
    }
}

enum class ThemeMode(val stored: String) {
    SYSTEM("system"), LIGHT("light"), DARK("dark");

    companion object {
        fun fromStored(value: String?) = entries.firstOrNull { it.stored == value } ?: SYSTEM
    }
}

/** Only explicit UI preferences belong here. Never store input or editor metadata. */
data class KeyboardOptions(val large: Boolean = false, val light: Boolean = false,
    val haptics: Boolean = false, val repeatGuard: Boolean = false,
    val numberRow: Boolean = true, val secondaryHints: Boolean = true,
    val keyHeightDp: Int = 0, val bottomPaddingDp: Int = 0,
    val deleteRepeat: Boolean = true, val holdDelayMs: Int = 320,
    val alignment: KeyboardAlignment = KeyboardAlignment.FULL,
    val letterLayout: LetterLayout = LetterLayout.QWERTY,
    val extraKeys: Boolean = true, val autoCapitalize: Boolean = true,
    val arrowRepeat: Boolean = true, val keyBorders: Boolean = true,
    val suggestions: Boolean = true,
    val theme: ThemeMode = ThemeMode.SYSTEM) {
    /** Panels resolve the stored theme against the system for actual colors. */
    fun resolvedLight(context: Context): Boolean = when (theme) {
        ThemeMode.LIGHT -> true
        ThemeMode.DARK -> false
        ThemeMode.SYSTEM -> (context.resources.configuration.uiMode and
            Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_NO
    }
    fun save(context: Context) {
        context.getSharedPreferences("keyboard", Context.MODE_PRIVATE).edit()
            .putBoolean("large", large).putBoolean("light", light)
            .putBoolean("haptics", haptics).putBoolean("repeatGuard", repeatGuard)
            .putBoolean("numberRow", numberRow)
            .putBoolean("secondaryHints", secondaryHints)
            .putBoolean("deleteRepeat", deleteRepeat)
            .putBoolean("extraKeys", extraKeys)
            .putBoolean("autoCapitalize", autoCapitalize)
            .putBoolean("arrowRepeat", arrowRepeat)
            .putBoolean("keyBorders", keyBorders)
            .putBoolean("suggestions", suggestions)
            .putString("theme", theme.stored)
            .putString("alignment", alignment.stored)
            .putString("letterLayout", letterLayout.stored)
            .putInt("holdDelayMs", boundedHoldDelay(holdDelayMs))
            .putInt("keyHeightDp", boundedKeyHeight(keyHeightDp))
            .putInt("bottomPaddingDp", boundedBottomPadding(bottomPaddingDp))
            .putInt("optionsVersion", VERSION).apply()
    }

    companion object {
        /** One-time default migration for installs saved before the redesign. */
        private const val VERSION = 1
        private fun boundedKeyHeight(value: Int) = if (value == 0) 0 else value.coerceIn(48, 80)
        private fun boundedBottomPadding(value: Int) = value.coerceIn(0, 80)
        private fun boundedHoldDelay(value: Int) = if (value == 0) 0 else value.coerceIn(250, 800)
        fun load(context: Context): KeyboardOptions {
            val prefs = context.getSharedPreferences("keyboard", Context.MODE_PRIVATE)
            val migrated = prefs.getInt("optionsVersion", 0) >= VERSION
            val storedLight = prefs.getBoolean("light", false)
            val theme = when {
                prefs.contains("theme") -> ThemeMode.fromStored(prefs.getString("theme", null))
                storedLight -> ThemeMode.LIGHT
                else -> ThemeMode.SYSTEM
            }
            return KeyboardOptions(prefs.getBoolean("large", false), storedLight,
                prefs.getBoolean("haptics", false), prefs.getBoolean("repeatGuard", false),
                // The redesign flips these defaults once; later explicit choices always win.
                if (migrated) prefs.getBoolean("numberRow", true) else true,
                prefs.getBoolean("secondaryHints", true),
                boundedKeyHeight(prefs.getInt("keyHeightDp", 0)),
                boundedBottomPadding(prefs.getInt("bottomPaddingDp", 0)),
                prefs.getBoolean("deleteRepeat", true),
                boundedHoldDelay(if (migrated) prefs.getInt("holdDelayMs", 320) else 320),
                KeyboardAlignment.fromStored(prefs.getString("alignment", null)),
                LetterLayout.fromStored(prefs.getString("letterLayout", null)),
                if (migrated) prefs.getBoolean("extraKeys", true) else true,
                prefs.getBoolean("autoCapitalize", true),
                prefs.getBoolean("arrowRepeat", true),
                prefs.getBoolean("keyBorders", true),
                if (migrated) prefs.getBoolean("suggestions", true) else true,
                theme)
        }
        /** Restores typing preferences only. Verified models and microphone permission stay. */
        fun resetPreferences(context: Context) {
            KeyboardOptions().save(context)
            context.getSharedPreferences("keyboard", Context.MODE_PRIVATE).edit()
                .remove("voiceHoldToInsert").apply()
        }
    }
}
