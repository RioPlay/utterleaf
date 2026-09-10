package org.utterleaf.voice

import android.content.Context

/** Only explicit UI preferences belong here. Never store input or editor metadata. */
data class KeyboardOptions(val large: Boolean = false, val light: Boolean = false,
    val haptics: Boolean = false, val repeatGuard: Boolean = false) {
    fun save(context: Context) {
        context.getSharedPreferences("keyboard", Context.MODE_PRIVATE).edit()
            .putBoolean("large", large).putBoolean("light", light)
            .putBoolean("haptics", haptics).putBoolean("repeatGuard", repeatGuard).apply()
    }
    companion object {
        fun load(context: Context): KeyboardOptions {
            val prefs = context.getSharedPreferences("keyboard", Context.MODE_PRIVATE)
            return KeyboardOptions(prefs.getBoolean("large", false), prefs.getBoolean("light", false),
                prefs.getBoolean("haptics", false), prefs.getBoolean("repeatGuard", false))
        }
    }
}
