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
    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is android.view.ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    @androidx.test.filters.SdkSuppress(minSdkVersion = 29) // WindowInspector locates the reset dialog.
    @Test fun tuningDescriptionsTrackProgressPersistenceCancelAndReset() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        val prefs = context.getSharedPreferences("keyboard", 0)
        val oldHold = prefs.getBoolean("voiceHoldToInsert", false)
        KeyboardOptions(keyHeightDp = 64, bottomPaddingDp = 12).save(context)
        val activity = instrumentation.startActivitySync(android.content.Intent(context, KeyboardSettingsActivity::class.java)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
        fun sliders() = descendants(activity.window.decorView).filterIsInstance<android.widget.SeekBar>()
        fun reset() = descendants(activity.window.decorView).filterIsInstance<android.widget.Button>()
            .single { it.text == "Reset keyboard preferences" }.performClick()
        fun dialogButtons(id: Int) = android.view.inspector.WindowInspector.getGlobalWindowViews()
            .mapNotNull { it.findViewById<android.widget.Button>(id) }.filter { it.isAttachedToWindow && it.isShown }
        val changed = KeyboardOptions(keyHeightDp = 61, bottomPaddingDp = 29)
        try {
            instrumentation.runOnMainSync {
                val currentSliders = sliders()
                assertEquals(listOf("Key height: 64 dp", "Bottom space: 12 dp"), currentSliders.map { it.contentDescription.toString() })
                currentSliders[0].progress = 13; currentSliders[1].progress = 28
                assertEquals(listOf("Key height: 60 dp", "Bottom space: 28 dp"), currentSliders.map { it.contentDescription.toString() })
                for ((slider, value) in currentSliders.zip(listOf(14f, 29f))) {
                    val arguments = android.os.Bundle().apply {
                        putFloat(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE, value)
                    }
                    assertTrue(slider.performAccessibilityAction(
                        android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.id, arguments))
                }
                assertEquals(changed, KeyboardOptions.load(context))
                reset()
            }
            UiAwait.until("Reset dialog did not appear") { dialogButtons(android.R.id.button2).size == 1 }
            instrumentation.runOnMainSync { dialogButtons(android.R.id.button2).single().performClick() }
            // AlertDialog posts dismissal; let the main looper remove it before opening another.
            UiAwait.until("Cancelled reset dialog did not close") { dialogButtons(android.R.id.button2).isEmpty() }
            instrumentation.runOnMainSync {
                assertEquals(changed, KeyboardOptions.load(context))
                assertEquals(listOf("Key height: 61 dp", "Bottom space: 29 dp"), sliders().map { it.contentDescription.toString() })
                reset()
            }
            UiAwait.until("Reset confirmation did not appear") { dialogButtons(android.R.id.button1).size == 1 }
            instrumentation.runOnMainSync { dialogButtons(android.R.id.button1).single().performClick() }
            UiAwait.until("Confirmed reset dialog did not close") { dialogButtons(android.R.id.button1).isEmpty() }
            instrumentation.runOnMainSync {
                assertEquals(KeyboardOptions(), KeyboardOptions.load(context))
                assertEquals(listOf(0, 0), sliders().map { it.progress })
                assertEquals(listOf("Key height: default", "Bottom space: 0 dp"), sliders().map { it.contentDescription.toString() })
            }
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            original.save(context); prefs.edit().putBoolean("voiceHoldToInsert", oldHold).commit()
        }
    }

    @Test fun quickToggleRefreshesUnrelatedOptionsFromSavedSnapshot() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        try {
            KeyboardOptions().save(context)
            instrumentation.runOnMainSync {
                val panel = TypingPanel(context, KeyboardOptions(), { true }, {}, {}, {}, {}, {}, {})
                panel.reset(false, false, "Enter")
                val saved = KeyboardOptions(terminal = true, haptics = true)
                saved.save(context)
                fun key(label: String) = descendants(panel.view).filterIsInstance<android.widget.Button>()
                    .single { it.contentDescription == label }
                key("Number row off").performClick()
                assertEquals(saved.copy(numberRow = true), KeyboardOptions.load(context))
                assertTrue(key("a").isHapticFeedbackEnabled)
                key("Terminal controls on").performClick()
                assertEquals(saved.copy(numberRow = true, terminal = false), KeyboardOptions.load(context))
            }
        } finally { original.save(context) }
    }

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
