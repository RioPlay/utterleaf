package com.android.inputmethod.keyboard

import android.text.InputType
import android.view.inputmethod.EditorInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.RichInputMethodManager
import com.android.inputmethod.latin.RichInputMethodSubtype
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Verifies theme and locale invalidation retires every cached keyboard reference. */
@RunWith(AndroidJUnit4::class)
class KeyboardCacheRetirementTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Before
    fun initializeRichInputMethodManager() {
        RichInputMethodManager.init(context)
    }

    private fun field(name: String) = KeyboardLayoutSet::class.java.getDeclaredField(name).apply {
        isAccessible = true
    }

    @Suppress("UNCHECKED_CAST")
    private fun forcibleCache(): Array<Keyboard?> =
        field("sForcibleKeyboardCache").get(null) as Array<Keyboard?>

    @Suppress("UNCHECKED_CAST")
    private fun softCache(): Map<*, *> = field("sKeyboardCache").get(null) as Map<*, *>

    private fun buildKeyboard(width: Int): Keyboard = KeyboardLayoutSet.Builder(
        context,
        EditorInfo().apply { inputType = InputType.TYPE_CLASS_TEXT }
    ).setSubtype(RichInputMethodSubtype.getNoLanguageSubtype())
        .setKeyboardGeometry(width, 800)
        .build()
        .getKeyboard(KeyboardId.ELEMENT_ALPHABET)

    @Test
    fun invalidationRetiresStrongEntriesAndReconstructsLayouts() {
        val forcible = forcibleCache()
        try {
            // Remove entries from earlier tests so these four real layouts are the complete
            // forcible cache population. Different widths produce distinct KeyboardIds.
            KeyboardLayoutSet.onKeyboardThemeChanged()
            val retained = (0 until 4).map { buildKeyboard(480 + it * 8) }
            assertEquals(4, forcible.count { it != null })
            val nativeHandles = retained.map { it.proximityInfo.getNativeProximityInfo() }
            assertTrue(nativeHandles.all { it != 0L })

            KeyboardLayoutSet.onKeyboardThemeChanged()
            assertTrue(forcible.all { it == null })
            assertTrue(softCache().isEmpty())
            // The returned Java objects still own their proximity resources after cache retirement.
            retained.zip(nativeHandles).forEach { (keyboard, handle) ->
                assertEquals(handle, keyboard.proximityInfo.getNativeProximityInfo())
            }

            val rebuilt = buildKeyboard(480)
            assertNotSame(retained.first(), rebuilt)
            assertNotEquals(0L, rebuilt.proximityInfo.getNativeProximityInfo())
            assertEquals(1, forcible.count { it != null })

            KeyboardLayoutSet.onSystemLocaleChanged()
            assertTrue(forcible.all { it == null })
            assertTrue(softCache().isEmpty())
        } finally {
            // Leave process-static caches in the same retired state for following tests.
            KeyboardLayoutSet.onKeyboardThemeChanged()
        }
    }
}
