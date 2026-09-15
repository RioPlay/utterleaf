package org.utterleaf.voice

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Reset restores typing prefs only. Models stay. Not a signed-APK upgrade fixture. */
@RunWith(AndroidJUnit4::class)
class PersistenceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    @Test fun resetPreferencesRestoresDefaultsAndLeavesModelFiles() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        val prefs = context.getSharedPreferences("keyboard", Context.MODE_PRIVATE)
        val previousHold = prefs.getBoolean("voiceHoldToInsert", false)
        val directory = context.noBackupFilesDir
        val installed = ModelStore.installed(directory)
        val marker = File(directory, "preserve-reset.bin")
        try {
            marker.writeText("keep")
            KeyboardOptions(extraKeys = false, numberRow = true, holdDelayMs = 500,
                alignment = KeyboardAlignment.RIGHT, autoCapitalize = false, arrowRepeat = false,
                keyBorders = false, theme = ThemeMode.LIGHT,
                deleteRepeat = false, large = true, letterLayout = LetterLayout.AZERTY).save(context)
            prefs.edit().putBoolean("voiceHoldToInsert", true).commit()
            assertFalse(KeyboardOptions.load(context).extraKeys)
            assertFalse(KeyboardOptions.load(context).autoCapitalize)
            assertEquals(ThemeMode.LIGHT, KeyboardOptions.load(context).theme)
            assertEquals(KeyboardAlignment.RIGHT, KeyboardOptions.load(context).alignment)
            assertEquals(LetterLayout.AZERTY, KeyboardOptions.load(context).letterLayout)
            KeyboardOptions.resetPreferences(context)
            val reset = KeyboardOptions.load(context)
            assertTrue(reset.numberRow && reset.extraKeys && reset.autoCapitalize)
            assertTrue(reset.arrowRepeat && reset.keyBorders)
            assertEquals(320, reset.holdDelayMs)
            assertEquals(ThemeMode.SYSTEM, reset.theme)
            assertEquals(KeyboardAlignment.FULL, reset.alignment)
            assertEquals(LetterLayout.QWERTY, reset.letterLayout)
            assertFalse(prefs.getBoolean("voiceHoldToInsert", false))
            assertEquals("keep", marker.readText())
            assertEquals(installed, ModelStore.installed(directory))
        } finally {
            marker.delete()
            original.save(context)
            prefs.edit().putBoolean("voiceHoldToInsert", previousHold).commit()
        }
    }

    @Test fun legacyPreferencesMigrateOnceToRedesignDefaults() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        val prefs = context.getSharedPreferences("keyboard", Context.MODE_PRIVATE)
        try {
            prefs.edit().clear().commit()
            prefs.edit().putBoolean("light", true).putBoolean("numberRow", false)
                .putInt("holdDelayMs", 600).commit()
            val legacy = KeyboardOptions.load(context)
            assertEquals(ThemeMode.LIGHT, legacy.theme)
            assertTrue(legacy.numberRow)
            assertEquals(320, legacy.holdDelayMs)
            assertTrue(legacy.extraKeys)
            legacy.save(context)
            prefs.edit().putBoolean("numberRow", false).commit()
            assertFalse(KeyboardOptions.load(context).numberRow)
        } finally {
            original.save(context)
        }
    }

    @Test fun unknownStoredAlignmentFallsBackToFullWidth() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        val prefs = context.getSharedPreferences("keyboard", Context.MODE_PRIVATE)
        try {
            prefs.edit().putString("alignment", "future-or-corrupt-value").commit()
            assertEquals(KeyboardAlignment.FULL, KeyboardOptions.load(context).alignment)
        } finally {
            original.save(context)
        }
    }

    @Test fun letterLayoutRoundTripsAndUnknownStoredValueFallsBackToQwerty() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        val prefs = context.getSharedPreferences("keyboard", Context.MODE_PRIVATE)
        try {
            LetterLayout.entries.forEach { layout ->
                original.copy(letterLayout = layout).save(context)
                assertEquals(layout, KeyboardOptions.load(context).letterLayout)
            }
            prefs.edit().putString("letterLayout", "future-or-corrupt-value").commit()
            assertEquals(LetterLayout.QWERTY, KeyboardOptions.load(context).letterLayout)
            prefs.edit().remove("letterLayout").commit()
            assertEquals(LetterLayout.QWERTY, KeyboardOptions.load(context).letterLayout)
        } finally {
            original.save(context)
        }
    }
}
