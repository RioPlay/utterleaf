package org.utterleaf.voice

import android.view.View
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KeyboardTuningTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    @Test fun previewQuickToggleUpdatesSettingsAndSurvivesAnotherChange() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        KeyboardOptions().save(context)
        val activity = instrumentation.startActivitySync(android.content.Intent(context, KeyboardSettingsActivity::class.java)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            instrumentation.runOnMainSync {
                fun descendants(view: View): List<View> = listOf(view) +
                    if (view is android.view.ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()
                fun views() = descendants(activity.window.decorView)
                views().filterIsInstance<android.widget.Button>().single { it.contentDescription == "Number row off" }.performClick()
                assertTrue(views().filterIsInstance<android.widget.CheckBox>().single { it.text == "Number row" }.isChecked)
                views().filterIsInstance<android.widget.CheckBox>().single { it.text == "Light keyboard" }.performClick()
                assertTrue(KeyboardOptions.load(context).numberRow)
                assertTrue(KeyboardOptions.load(context).light)
            }
        } finally { instrumentation.runOnMainSync { activity.finish() }; original.save(context) }
    }
    @Test fun quickToolbarTogglesPersistWithoutChangingOtherPreferences() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        try {
            val initial = KeyboardOptions(keyHeightDp = 60, bottomPaddingDp = 12, deleteRepeat = false)
            initial.save(context)
            instrumentation.runOnMainSync {
                fun buttons(view: View): List<android.widget.Button> =
                    (if (view is android.widget.Button) listOf(view) else emptyList()) +
                    if (view is android.view.ViewGroup) (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) } else emptyList()
                val panel = TypingPanel(context, initial, { true }, {}, {}, {}, {}, {}, {})
                panel.reset(true, false, "Enter")
                fun key(description: String) = buttons(panel.view).single { it.contentDescription == description }
                key("Number row off").performClick()
                assertEquals(initial.copy(numberRow = true), KeyboardOptions.load(context))
                key("Terminal controls off").performClick()
                assertEquals(initial.copy(numberRow = true, terminal = true), KeyboardOptions.load(context))
                key("Terminal controls on").performClick()
                key("Number row on").performClick()
                assertEquals(initial, KeyboardOptions.load(context))
                assertEquals("", key("Dictate").text.toString())
                assertTrue(key("Dictate").isEnabled)
                panel.reset(false, true, "Enter")
                assertFalse(key("Dictate").isEnabled)
            }
        } finally { original.save(context) }
    }
    @Test fun dimensionsAreIndependentBoundedAndResettable() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        try {
            KeyboardOptions(keyHeightDp = 200, bottomPaddingDp = -5).save(context)
            assertEquals(80, KeyboardOptions.load(context).keyHeightDp)
            assertEquals(0, KeyboardOptions.load(context).bottomPaddingDp)
            KeyboardOptions(keyHeightDp = 60, bottomPaddingDp = 28).save(context)
            assertEquals(KeyboardOptions(keyHeightDp = 60, bottomPaddingDp = 28), KeyboardOptions.load(context))
            KeyboardOptions(deleteRepeat = false).save(context)
            assertFalse(KeyboardOptions.load(context).deleteRepeat)
            KeyboardOptions().save(context)
            assertEquals(KeyboardOptions(), KeyboardOptions.load(context))
            assertTrue(KeyboardOptions.load(context).deleteRepeat)
            instrumentation.runOnMainSync {
                fun height(options: KeyboardOptions): Int {
                    val panel = TypingPanel(context, options, { true }, {}, {}, {}, {}, {}, {})
                    panel.reset(false, false, "Enter")
                    panel.view.measure(View.MeasureSpec.makeMeasureSpec(Ui.dp(context, 320), View.MeasureSpec.EXACTLY),
                        View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                    return panel.view.measuredHeight
                }
                val base = height(KeyboardOptions(keyHeightDp = 60))
                assertEquals(Ui.dp(context, 28).toDouble(),
                    (height(KeyboardOptions(keyHeightDp = 60, bottomPaddingDp = 28)) - base).toDouble(), 1.0)
                assertEquals((Ui.dp(context, 8) * 4).toDouble(),
                    (height(KeyboardOptions(keyHeightDp = 68)) - base).toDouble(), 4.0)
            }
        } finally { original.save(context) }
    }
}
