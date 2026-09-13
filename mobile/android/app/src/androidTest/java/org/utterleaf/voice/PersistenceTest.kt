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
            KeyboardOptions(terminal = true, numberRow = true, holdDelayMs = 500,
                alignment = KeyboardAlignment.RIGHT,
                deleteRepeat = false, large = true, letterLayout = LetterLayout.AZERTY).save(context)
            prefs.edit().putBoolean("voiceHoldToInsert", true).commit()
            assertTrue(KeyboardOptions.load(context).terminal)
            assertEquals(KeyboardAlignment.RIGHT, KeyboardOptions.load(context).alignment)
            assertEquals(LetterLayout.AZERTY, KeyboardOptions.load(context).letterLayout)
            KeyboardOptions.resetPreferences(context)
            assertEquals(KeyboardOptions(), KeyboardOptions.load(context))
            assertEquals(LetterLayout.QWERTY, KeyboardOptions.load(context).letterLayout)
            assertFalse(prefs.getBoolean("voiceHoldToInsert", false))
            assertEquals("keep", marker.readText())
            assertEquals(installed, ModelStore.installed(directory))
        } finally {
            marker.delete()
            original.save(context)
            prefs.edit().putBoolean("voiceHoldToInsert", previousHold).commit()
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
