package org.utterleaf.voice

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Rect
import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class SettingsExperienceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val prefs get() = context.getSharedPreferences("keyboard", 0)
    private fun views(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { views(view.getChildAt(it)) } else emptyList()
    private fun all(activity: Activity) = views(activity.window.decorView)
    private fun button(activity: Activity, label: String) = all(activity).filterIsInstance<Button>()
        .single { it.text.toString() == label }
    private fun key(activity: Activity, label: String) = all(activity).filterIsInstance<Button>()
        .single { it.contentDescription?.toString() == label }
    private fun category(activity: Activity, title: String) {
        all(activity).single { it.contentDescription?.toString()?.startsWith("$title,") == true }.performClick()
    }
    private fun open() = instrumentation.startActivitySync(Intent(context, KeyboardSettingsActivity::class.java)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as KeyboardSettingsActivity
    private fun main(block: () -> Unit) = instrumentation.runOnMainSync(block)
    private fun isolated(block: () -> Unit) {
        val original = KeyboardOptions.load(context)
        val oldHold = prefs.getBoolean("voiceHoldToInsert", false)
        try { KeyboardOptions().save(context); prefs.edit().putBoolean("voiceHoldToInsert", false).commit(); block() }
        finally { original.save(context); prefs.edit().putBoolean("voiceHoldToInsert", oldHold).commit() }
    }

    @Test fun voiceChoiceCancelsThenAppliesAndReopens() = isolated {
        for (apply in listOf(false, true)) {
            val activity = open()
            try {
                main {
                    category(activity, "Voice input")
                    button(activity, "Hold the mic key to insert").performClick()
                    assertFalse(prefs.getBoolean("voiceHoldToInsert", false))
                    if (apply) button(activity, "Apply").performClick()
                    else { activity.onBackPressed(); button(activity, "Cancel").performClick() }
                }
                instrumentation.waitForIdleSync()
                assertEquals(apply, prefs.getBoolean("voiceHoldToInsert", false))
            } finally { main { activity.finish() } }
        }
        val reopened = open()
        try { main {
            category(reopened, "Voice input")
            assertTrue((button(reopened, "Hold the mic key to insert") as CheckBox).isChecked)
        } } finally { main { reopened.finish() } }
    }

    @Test fun radioChoicesRefreshPreviewAndCanReturnToOriginal() = isolated {
        val activity = open()
        try { main {
            category(activity, "Appearance")
            val originalKey = key(activity, "a")
            button(activity, "Light").performClick()
            val lightKey = key(activity, "a")
            assertNotSame(originalKey, lightKey)
            val lightInk = lightKey.currentTextColor
            button(activity, "Dark").performClick()
            assertNotEquals(lightInk, key(activity, "a").currentTextColor)
            button(activity, "System").performClick()
            assertTrue((button(activity, "System") as RadioButton).isChecked)
            activity.onBackPressed()
            category(activity, "Layout & size")
            button(activity, "AZERTY").performClick()
            val azerty = key(activity, "a")
            button(activity, "QWERTY").performClick()
            assertNotSame(azerty, key(activity, "a"))
            button(activity, "Left hand").performClick()
            button(activity, "Full width").performClick()
            button(activity, "Apply").performClick()
        }
            instrumentation.waitForIdleSync()
            assertEquals(KeyboardOptions(), KeyboardOptions.load(context))
        } finally { main { activity.finish() } }
    }

    @Test fun previewQuickControlsKeepOtherDraftChoicesAndCancelWithoutSaving() = isolated {
        val activity = open()
        try { main {
            category(activity, "Layout & size")
            button(activity, "Larger keys and labels").performClick()
            key(activity, "Keyboard tools").performClick()
            val oldToggle = key(activity, "Number row on")
            oldToggle.performClick()
            assertFalse((button(activity, "Number row") as CheckBox).isChecked)
            assertTrue((button(activity, "Larger keys and labels") as CheckBox).isChecked)
            assertEquals(KeyboardOptions(), KeyboardOptions.load(context))
            // A retained view from the disposed preview cannot mutate the draft.
            oldToggle.performClick()
            assertFalse((button(activity, "Number row") as CheckBox).isChecked)
            activity.onBackPressed(); button(activity, "Cancel").performClick()
        }
            assertEquals(KeyboardOptions(), KeyboardOptions.load(context))
        } finally { main { activity.finish() } }
    }

    @androidx.test.filters.SdkSuppress(minSdkVersion = 29)
    @Test fun confirmedResetIsStagedCancelableAndKeepsModelStorage() = isolated {
        val custom = KeyboardOptions(numberRow = false, theme = ThemeMode.DARK, holdDelayMs = 600)
        custom.save(context); prefs.edit().putBoolean("voiceHoldToInsert", true).commit()
        val installed = ModelStore.installed(context.noBackupFilesDir)
        val marker = File(context.noBackupFilesDir, "settings-reset-preserve-test.bin")
        check(!marker.exists())
        marker.writeText("keep")
        fun confirmReset(activity: Activity) {
            main { all(activity).single { it.contentDescription == "Reset preferences" }.performClick() }
            fun confirmations() = android.view.inspector.WindowInspector.getGlobalWindowViews()
                .mapNotNull { it.findViewById<Button>(android.R.id.button1) }.filter { it.isShown }
            UiAwait.until("Reset dialog missing") { confirmations().size == 1 }
            main { confirmations().single().performClick() }
            instrumentation.waitForIdleSync()
        }
        try {
            for (apply in listOf(false, true)) {
                val activity = open()
                try {
                    confirmReset(activity)
                    assertEquals(custom, KeyboardOptions.load(context))
                    assertTrue(prefs.getBoolean("voiceHoldToInsert", false))
                    main { button(activity, if (apply) "Apply" else "Cancel").performClick() }
                    instrumentation.waitForIdleSync()
                    assertEquals(if (apply) KeyboardOptions() else custom, KeyboardOptions.load(context))
                    assertEquals(!apply, prefs.getBoolean("voiceHoldToInsert", false))
                    assertEquals("keep", marker.readText())
                    assertEquals(installed, ModelStore.installed(context.noBackupFilesDir))
                } finally { main { activity.finish() } }
            }
        } finally { marker.delete() }
    }

    @Test fun searchAndDraftSurviveRecreationWithoutRetainingPracticeInput() = isolated {
        ActivityScenario.launch(KeyboardSettingsActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                all(activity).filterIsInstance<EditText>().single().setText("appearance")
                category(activity, "Appearance")
                button(activity, "Dark").performClick()
                all(activity).filterIsInstance<EditText>().single().setText("synthetic private practice")
            }
            scenario.recreate()
            scenario.onActivity { activity ->
                assertTrue((button(activity, "Dark") as RadioButton).isChecked)
                assertTrue(all(activity).filterIsInstance<EditText>().none { it.text.contains("synthetic private") })
                activity.onBackPressed()
                assertEquals("appearance", all(activity).filterIsInstance<EditText>().single().text.toString())
                assertEquals(1, all(activity).count { it.contentDescription?.toString()?.startsWith("Appearance,") == true })
                button(activity, "Apply").performClick()
            }
        }
        assertEquals(ThemeMode.DARK, KeyboardOptions.load(context).theme)
    }

    @Test fun applyRemainsVisibleAboveScrollingControlsAndCaptureOwnedViews() = isolated {
        val activity = open()
        fun capture(name: String) {
            val directoryName = InstrumentationRegistry.getArguments().getString("settingsScreenshots") ?: return
            require(directoryName.matches(Regex("[a-zA-Z0-9_-]{1,40}")))
            main {
                val root = activity.findViewById<View>(android.R.id.content)
                val bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888)
                try {
                    root.draw(Canvas(bitmap))
                    val dir = File(context.getExternalFilesDir(null), directoryName).apply { mkdirs() }
                    File(dir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
                } finally { bitmap.recycle() }
            }
        }
        try {
            instrumentation.waitForIdleSync(); capture("categories")
            main { category(activity, "Layout & size") }
            instrumentation.waitForIdleSync(); capture("layout-controls")
            val before = Rect()
            main {
                assertTrue(button(activity, "Apply").getGlobalVisibleRect(before))
                val scroll = all(activity).filterIsInstance<ScrollView>().single()
                scroll.scrollTo(0, scroll.getChildAt(0).height)
            }
            instrumentation.waitForIdleSync()
            main {
                val apply = button(activity, "Apply")
                val after = Rect()
                assertTrue(apply.getGlobalVisibleRect(after))
                assertEquals(before, after)
                assertEquals(apply.height, after.height())
                val preview = all(activity).filterIsInstance<KeyboardSurface>().single()
                val visible = Rect()
                assertTrue("Preview must be reachable by scrolling", preview.getGlobalVisibleRect(visible))
            }
            capture("layout-practice")
        } finally { main { activity.finish() } }
    }

    @Test fun searchFindsControlsRegardlessOfCurrentPreferenceState() = isolated {
        for (hints in listOf(false, true)) {
            KeyboardOptions(secondaryHints = hints, haptics = hints, deleteRepeat = hints).save(context)
            val original = KeyboardOptions.load(context)
            val activity = open()
            try { main {
                val queries = mapOf("backspace" to "Holds & gestures", "repeat guard" to "Holds & gestures",
                    "vibration" to "Holds & gestures", "height" to "Layout & size",
                    "qwertz" to "Layout & size", "theme" to "Appearance", "borders" to "Appearance",
                    "Key vibration (respects device settings)" to "Holds & gestures",
                    "Hold Backspace or Delete to repeat" to "Holds & gestures",
                    "Ignore repeated taps on the same key within 250 ms" to "Holds & gestures",
                    "Hold the mic key to insert" to "Voice input",
                    "Larger keys and labels" to "Layout & size",
                    "Auto-capitalization" to "Typing assistance")
                queries.forEach { (query, title) ->
                    all(activity).filterIsInstance<EditText>().single().setText(query)
                    assertTrue("Search '$query' did not expose '$title'", all(activity).any {
                        it.contentDescription?.toString()?.startsWith("$title,") == true
                    })
                    category(activity, title)
                    activity.onBackPressed()
                    assertEquals(query, all(activity).filterIsInstance<EditText>().single().text.toString())
                }
                all(activity).filterIsInstance<EditText>().single().setText("")
                val gestures = all(activity).single {
                    it.contentDescription?.toString()?.startsWith("Holds & gestures,") == true
                }.contentDescription.toString()
                assertTrue(gestures.contains(if (hints) "Hints shown" else "Hints hidden"))
                assertTrue(gestures.contains("Hold for accents"))
                button(activity, "Cancel").performClick()
                assertEquals(original, KeyboardOptions.load(context))
            } } finally { main { activity.finish() } }
        }
    }

    @Test fun deletionPreferencesInGesturesRemainStagedUntilApply() = isolated {
        val repeatLabel = "Hold Backspace or Delete to repeat"
        val guardLabel = "Ignore repeated taps on the same key within 250 ms"
        for (apply in listOf(false, true)) {
            val activity = open()
            try { main {
                category(activity, "Navigation & terminal")
                assertTrue(all(activity).filterIsInstance<CheckBox>().none {
                    it.text == repeatLabel || it.text == guardLabel
                })
                activity.onBackPressed()
                category(activity, "Holds & gestures")
                button(activity, repeatLabel).performClick()
                button(activity, guardLabel).performClick()
                assertEquals(KeyboardOptions(), KeyboardOptions.load(context))
                activity.onBackPressed()
                category(activity, "Holds & gestures")
                assertFalse((button(activity, repeatLabel) as CheckBox).isChecked)
                assertTrue((button(activity, guardLabel) as CheckBox).isChecked)
                if (apply) button(activity, "Apply").performClick()
                else { activity.onBackPressed(); button(activity, "Cancel").performClick() }
            }
                instrumentation.waitForIdleSync()
                assertEquals(if (apply) KeyboardOptions(deleteRepeat = false, repeatGuard = true)
                    else KeyboardOptions(), KeyboardOptions.load(context))
            } finally { main { activity.finish() } }
        }
    }

    @Test fun systemBackReturnsToCategoriesBeforeClosing() = isolated {
        val activity = open()
        try {
            main { category(activity, "Appearance") }
            instrumentation.waitForIdleSync()
            instrumentation.sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK)
            UiAwait.until("System Back did not return to categories") {
                !activity.isFinishing && all(activity).filterIsInstance<EditText>()
                    .any { it.hint == "Search settings" }
            }
            instrumentation.sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK)
            UiAwait.until("System Back did not close settings") { activity.isFinishing }
        } finally { main { activity.finish() } }
    }
}
