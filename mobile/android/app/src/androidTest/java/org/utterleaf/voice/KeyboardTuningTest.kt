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

    private fun openSettings() = instrumentation.startActivitySync(
        android.content.Intent(instrumentation.targetContext, KeyboardSettingsActivity::class.java)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))

    private fun buttons(view: View): List<android.widget.Button> =
        (if (view is android.widget.Button) listOf(view) else emptyList()) +
        if (view is android.view.ViewGroup) (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) } else emptyList()

    private fun openDetail(activity: android.app.Activity, title: String) {
        descendants(activity.window.decorView)
            .single { (it.contentDescription as? String)?.startsWith(title) == true }.performClick()
    }

    @androidx.test.filters.SdkSuppress(minSdkVersion = 29) // WindowInspector locates the reset dialog.
    @Test fun layoutSlidersStageUntilApplyAndResetRestoresDefaults() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        val prefs = context.getSharedPreferences("keyboard", 0)
        val oldHold = prefs.getBoolean("voiceHoldToInsert", false)
        KeyboardOptions(keyHeightDp = 64, bottomPaddingDp = 12).save(context)
        val activity = openSettings()
        fun dialogButtons(id: Int) = android.view.inspector.WindowInspector.getGlobalWindowViews()
            .mapNotNull { it.findViewById<android.widget.Button>(id) }.filter { it.isAttachedToWindow && it.isShown }
        try {
            instrumentation.runOnMainSync {
                val views = { descendants(activity.window.decorView) }
                openDetail(activity, "Layout & size")
                val sliders = { views().filterIsInstance<android.widget.SeekBar>() }
                assertEquals(listOf("Key height: 64 dp", "Bottom space: 12 dp"),
                    sliders().map { it.contentDescription.toString() })
                sliders()[0].progress = 13; sliders()[1].progress = 28
                assertEquals(listOf("Key height: 60 dp", "Bottom space: 28 dp"),
                    sliders().map { it.contentDescription.toString() })
                for ((slider, value) in sliders().zip(listOf(14f, 29f))) {
                    val arguments = android.os.Bundle().apply {
                        putFloat(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE, value)
                    }
                    assertTrue(slider.performAccessibilityAction(
                        android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.id, arguments))
                }
                // Staged only: nothing persists until Apply.
                assertEquals(64, KeyboardOptions.load(context).keyHeightDp)
                assertEquals(12, KeyboardOptions.load(context).bottomPaddingDp)
                assertEquals(listOf("Key height: 61 dp", "Bottom space: 29 dp"),
                    sliders().map { it.contentDescription.toString() })
                views().filterIsInstance<android.widget.Button>().single { it.text == "Apply" }.performClick()
            }
            instrumentation.waitForIdleSync()
            assertEquals(61, KeyboardOptions.load(context).keyHeightDp)
            assertEquals(29, KeyboardOptions.load(context).bottomPaddingDp)
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            original.save(context); prefs.edit().putBoolean("voiceHoldToInsert", oldHold).commit()
        }
    }

    @androidx.test.filters.SdkSuppress(minSdkVersion = 29) // WindowInspector locates the reset dialog.
    @Test fun cancelDiscardsStagedChangesAndResetRestoresDefaults() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        val activity = openSettings()
        fun dialogButtons(id: Int) = android.view.inspector.WindowInspector.getGlobalWindowViews()
            .mapNotNull { it.findViewById<android.widget.Button>(id) }.filter { it.isAttachedToWindow && it.isShown }
        try {
            instrumentation.runOnMainSync {
                openDetail(activity, "Appearance")
                descendants(activity.window.decorView).filterIsInstance<android.widget.RadioButton>()
                    .single { it.text == "Light" }.performClick()
                descendants(activity.window.decorView).filterIsInstance<android.widget.CheckBox>()
                    .single { it.text == "Key borders" }.performClick()
                // Staged only.
                assertEquals(ThemeMode.SYSTEM, KeyboardOptions.load(context).theme)
                // Back out with the header back control, then leave via Cancel.
                descendants(activity.window.decorView).filterIsInstance<android.widget.Button>()
                    .single { it.text == "‹ Back" }.performClick()
                descendants(activity.window.decorView).filterIsInstance<android.widget.Button>()
                    .single { it.text == "Cancel" }.performClick()
            }
            instrumentation.waitForIdleSync()
            assertEquals(ThemeMode.SYSTEM, KeyboardOptions.load(context).theme)
            val reopened = openSettings()
            instrumentation.runOnMainSync {
                descendants(reopened.window.decorView)
                    .single { (it.contentDescription as? String) == "Reset preferences" }.performClick()
            }
            UiAwait.until("Reset dialog did not appear") { dialogButtons(android.R.id.button1).size == 1 }
            instrumentation.runOnMainSync { dialogButtons(android.R.id.button1).single().performClick() }
            UiAwait.until("Reset dialog did not close") { dialogButtons(android.R.id.button1).isEmpty() }
            instrumentation.runOnMainSync {
                assertEquals(320, KeyboardOptions.load(context).holdDelayMs)
                assertTrue(KeyboardOptions.load(context).numberRow)
            }
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            original.save(context)
        }
    }

    @Test fun passwordManagerKeyAppearsOnlyWhenOfferedAndLaunchesOnce() {
        instrumentation.runOnMainSync {
            val context = instrumentation.targetContext
            val launched = mutableListOf<Boolean>()
            fun panel(manager: (() -> Boolean)?): TypingPanel =
                TypingPanel(context, KeyboardOptions(numberRow = false), { true }, {}, {}, {}, {}, {}, {},
                    openPasswordManager = manager).apply { reset(true, false, "Enter") }
            fun keyOf(view: TypingPanel, label: String) = descendants(view.view)
                .filterIsInstance<android.widget.Button>().single { it.contentDescription == label }

            val withKey = panel { launched.add(true); true }
            assertEquals("", keyOf(withKey, "Open password manager").text.toString())
            keyOf(withKey, "Open password manager").performClick()
            assertEquals(listOf(true), launched)

            val refusing = panel { launched.add(false); false }
            keyOf(refusing, "Open password manager").performClick()
            assertEquals(listOf(true, false), launched)

            val withoutKey = panel(null)
            assertTrue(descendants(withoutKey.view).filterIsInstance<android.widget.Button>()
                .none { it.contentDescription == "Open password manager" })
            withKey.dispose(); refusing.dispose(); withoutKey.dispose()
        }
    }

    @Test fun hubQuickToggleRefreshesUnrelatedOptionsFromSavedSnapshot() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        try {
            KeyboardOptions().save(context)
            instrumentation.runOnMainSync {
                val panel = TypingPanel(context, KeyboardOptions(numberRow = false), { true }, {}, {}, {}, {}, {}, {})
                panel.reset(false, false, "Enter")
                val saved = KeyboardOptions(numberRow = false, haptics = true)
                saved.save(context)
                fun key(label: String): android.widget.Button {
                    val matches = descendants(panel.view).filterIsInstance<android.widget.Button>()
                        .filter { it.contentDescription == label }
                    check(matches.isNotEmpty()) {
                        "Missing key $label; present=${descendants(panel.view).filterIsInstance<android.widget.Button>().map { it.contentDescription }}"
                    }
                    return matches.single()
                }
                key("Emoji").performLongClick()
                key("Number row off").performClick()
                assertEquals(saved.copy(numberRow = true), KeyboardOptions.load(context))
                key("Close tools and settings").performClick()
                assertTrue(key("a").isHapticFeedbackEnabled)
                key("Emoji").performLongClick()
                key("Extra keys on").performClick()
                assertEquals(saved.copy(numberRow = true, extraKeys = false), KeyboardOptions.load(context))
            }
        } finally { original.save(context) }
    }

    @Test fun previewHubToggleStagesThroughSettingsAndApplyPersists() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        KeyboardOptions().save(context)
        val activity = openSettings()
        try {
            instrumentation.runOnMainSync {
                openDetail(activity, "Layout & size")
                val views = { descendants(activity.window.decorView) }
                views().filterIsInstance<android.widget.Button>()
                    .single { it.contentDescription == "Emoji" }.performLongClick()
                views().filterIsInstance<android.widget.Button>()
                    .single { it.contentDescription == "Number row on" }.performClick()
                // The hub saved directly; the staged controls re-render from the saved snapshot.
                assertFalse(views().filterIsInstance<android.widget.CheckBox>()
                    .single { it.text == "Number row" }.isChecked)
                views().filterIsInstance<android.widget.CheckBox>()
                    .single { it.text == "Number row" }.performClick()
                // Staged only: the hub's save stays until Apply commits the staged value.
                assertFalse(KeyboardOptions.load(context).numberRow)
                views().filterIsInstance<android.widget.Button>().single { it.text == "Apply" }.performClick()
            }
            instrumentation.waitForIdleSync()
            assertTrue(KeyboardOptions.load(context).numberRow)
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            original.save(context)
        }
    }

    @Test fun hubQuickTogglesPersistWithoutChangingOtherPreferences() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        try {
            val initial = KeyboardOptions(keyHeightDp = 60, bottomPaddingDp = 12, deleteRepeat = false, holdDelayMs = 500)
            initial.save(context)
            instrumentation.runOnMainSync {
                val panel = TypingPanel(context, initial, { true }, {}, {}, {}, {}, {}, {})
                panel.reset(true, false, "Enter")
                fun key(description: String) = buttons(panel.view).single { it.contentDescription == description }
                key("Emoji").performLongClick()
                key("Number row on").performClick()
                assertEquals(initial.copy(numberRow = false), KeyboardOptions.load(context))
                key("Extra keys on").performClick()
                assertEquals(initial.copy(numberRow = false, extraKeys = false), KeyboardOptions.load(context))
                key("Number row off").performClick()
                assertEquals(initial.copy(numberRow = true, extraKeys = false), KeyboardOptions.load(context))
                key("Left hand layout").performClick()
                assertEquals(initial.copy(numberRow = true, extraKeys = false,
                    alignment = KeyboardAlignment.LEFT), KeyboardOptions.load(context))
                assertTrue(key("Left hand layout").isSelected)
                key("Right hand layout").performClick()
                assertEquals(initial.copy(numberRow = true, extraKeys = false,
                    alignment = KeyboardAlignment.RIGHT), KeyboardOptions.load(context))
                key("AZERTY letter layout").performClick()
                assertEquals(initial.copy(numberRow = true, extraKeys = false, alignment = KeyboardAlignment.RIGHT,
                    letterLayout = LetterLayout.AZERTY), KeyboardOptions.load(context))
                assertTrue(key("AZERTY letter layout").isSelected)
                key("Full width layout").performClick()
                assertEquals(initial.copy(numberRow = true, extraKeys = false,
                    letterLayout = LetterLayout.AZERTY), KeyboardOptions.load(context))
                key("QWERTY letter layout").performClick()
                assertEquals(initial.copy(numberRow = true, extraKeys = false), KeyboardOptions.load(context))
                key("Close tools and settings").performClick()
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
            KeyboardOptions(holdDelayMs = 90).save(context)
            assertEquals(250, KeyboardOptions.load(context).holdDelayMs)
            KeyboardOptions(holdDelayMs = 500).save(context)
            assertEquals(500, KeyboardOptions.load(context).holdDelayMs)
            KeyboardOptions(holdDelayMs = 0).save(context)
            assertEquals(0, KeyboardOptions.load(context).holdDelayMs)
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
                assertEquals((Ui.dp(context, 8) * 5).toDouble(),
                    (height(KeyboardOptions(keyHeightDp = 68)) - base).toDouble(), 4.0)
            }
        } finally { original.save(context) }
    }
}
