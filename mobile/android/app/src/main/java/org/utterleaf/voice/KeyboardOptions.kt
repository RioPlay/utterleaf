package org.utterleaf.voice

import android.content.Context

enum class KeyboardAlignment(val stored: String) {
    FULL("full"), LEFT("left"), RIGHT("right");

    companion object {
        fun fromStored(value: String?) = entries.firstOrNull { it.stored == value } ?: FULL
    }
}

/** Only explicit UI preferences belong here. Never store input or editor metadata. */
data class KeyboardOptions(val large: Boolean = false, val light: Boolean = false,
    val haptics: Boolean = false, val repeatGuard: Boolean = false, val terminal: Boolean = false,
    val numberRow: Boolean = false, val secondaryHints: Boolean = true,
    val keyHeightDp: Int = 0, val bottomPaddingDp: Int = 0,
    val deleteRepeat: Boolean = true, val holdDelayMs: Int = 0,
    val alignment: KeyboardAlignment = KeyboardAlignment.FULL,
    val letterLayout: LetterLayout = LetterLayout.QWERTY) {
    fun save(context: Context) {
        context.getSharedPreferences("keyboard", Context.MODE_PRIVATE).edit()
            .putBoolean("large", large).putBoolean("light", light)
            .putBoolean("haptics", haptics).putBoolean("repeatGuard", repeatGuard)
            .putBoolean("terminal", terminal).putBoolean("numberRow", numberRow)
            .putBoolean("secondaryHints", secondaryHints)
            .putBoolean("deleteRepeat", deleteRepeat)
            .putString("alignment", alignment.stored)
            .putString("letterLayout", letterLayout.stored)
            .putInt("holdDelayMs", boundedHoldDelay(holdDelayMs))
            .putInt("keyHeightDp", boundedKeyHeight(keyHeightDp))
            .putInt("bottomPaddingDp", boundedBottomPadding(bottomPaddingDp)).apply()
    }
    companion object {
        private fun boundedKeyHeight(value: Int) = if (value == 0) 0 else value.coerceIn(48, 80)
        private fun boundedBottomPadding(value: Int) = value.coerceIn(0, 80)
        private fun boundedHoldDelay(value: Int) = if (value == 0) 0 else value.coerceIn(250, 800)
        fun load(context: Context): KeyboardOptions {
            val prefs = context.getSharedPreferences("keyboard", Context.MODE_PRIVATE)
            return KeyboardOptions(prefs.getBoolean("large", false), prefs.getBoolean("light", false),
                prefs.getBoolean("haptics", false), prefs.getBoolean("repeatGuard", false),
                prefs.getBoolean("terminal", false), prefs.getBoolean("numberRow", false),
                prefs.getBoolean("secondaryHints", true),
                boundedKeyHeight(prefs.getInt("keyHeightDp", 0)),
                boundedBottomPadding(prefs.getInt("bottomPaddingDp", 0)),
                prefs.getBoolean("deleteRepeat", true),
                boundedHoldDelay(prefs.getInt("holdDelayMs", 0)),
                KeyboardAlignment.fromStored(prefs.getString("alignment", null)),
                LetterLayout.fromStored(prefs.getString("letterLayout", null)))
        }
        /** Restores typing preferences only. Verified models and microphone permission stay. */
        fun resetPreferences(context: Context) {
            KeyboardOptions().save(context)
            context.getSharedPreferences("keyboard", Context.MODE_PRIVATE).edit()
                .remove("voiceHoldToInsert").apply()
        }
    }
}
