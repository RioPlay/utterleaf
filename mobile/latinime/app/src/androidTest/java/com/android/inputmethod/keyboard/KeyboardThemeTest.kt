package com.android.inputmethod.keyboard

import android.content.Context
import android.os.Build
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KeyboardThemeTest {
    @Test fun darkDefaultHonorsLightChoiceAndReturnsAfterPreferenceReset() {
        val app = InstrumentationRegistry.getInstrumentation().targetContext
        val preferences = app.getSharedPreferences("synthetic-theme-test", Context.MODE_PRIVATE)
        val themes = KeyboardTheme.getAvailableThemeArray(app)
        fun current() = KeyboardTheme.getKeyboardTheme(preferences, Build.VERSION.SDK_INT, themes).mThemeId
        try {
            assertTrue(preferences.edit().clear().commit())
            assertEquals(KeyboardTheme.THEME_ID_LXX_DARK, current())
            KeyboardTheme.saveKeyboardThemeId(KeyboardTheme.THEME_ID_LXX_LIGHT, preferences)
            assertEquals(KeyboardTheme.THEME_ID_LXX_LIGHT, current())
            // commit also waits for the preceding asynchronous preference write.
            assertTrue(preferences.edit().commit())
            val reopened = app.getSharedPreferences("synthetic-theme-test", Context.MODE_PRIVATE)
            assertEquals(KeyboardTheme.THEME_ID_LXX_LIGHT,
                KeyboardTheme.getKeyboardTheme(reopened, Build.VERSION.SDK_INT, themes).mThemeId)
            assertTrue(preferences.edit().clear().commit())
            assertEquals(KeyboardTheme.THEME_ID_LXX_DARK, current())
        } finally {
            preferences.edit().clear().commit()
        }
    }
}
