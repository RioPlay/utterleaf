package org.utterleaf.voice

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Rect
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.RadioButton
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class SettingsResetTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val prefs get() = context.getSharedPreferences("keyboard", Context.MODE_PRIVATE)

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
        else emptyList()
    private fun all(activity: Activity) = descendants(activity.window.decorView)
    private fun main(block: () -> Unit) = instrumentation.runOnMainSync(block)
    private fun button(activity: Activity, label: String) = all(activity).filterIsInstance<Button>()
        .single { it.text.toString() == label }
    private fun described(activity: Activity, label: String) = all(activity)
        .single { it.contentDescription?.toString() == label }
    private fun category(activity: Activity, title: String) {
        all(activity).single { it.contentDescription?.toString()?.startsWith("$title,") == true }
            .performClick()
    }
    private fun open() = instrumentation.startActivitySync(
        Intent(context, KeyboardSettingsActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    ) as KeyboardSettingsActivity
    private fun currentActivity(scenario: ActivityScenario<KeyboardSettingsActivity>): KeyboardSettingsActivity {
        var current: KeyboardSettingsActivity? = null
        scenario.onActivity { current = it }
        return checkNotNull(current)
    }
    private fun awaitLandscape(scenario: ActivityScenario<KeyboardSettingsActivity>): KeyboardSettingsActivity {
        val deadline = android.os.SystemClock.elapsedRealtime() + 5_000
        var details = "activity unavailable"
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            runCatching { currentActivity(scenario) }.onSuccess { activity ->
                var orientation = Configuration.ORIENTATION_UNDEFINED
                var focused = false
                main {
                    orientation = activity.resources.configuration.orientation
                    focused = activity.hasWindowFocus()
                }
                details = "orientation=$orientation, focused=$focused"
                if (orientation == Configuration.ORIENTATION_LANDSCAPE && focused) return activity
            }.onFailure { details = "${it.javaClass.simpleName}: ${it.message}" }
            Thread.sleep(20)
        }
        throw AssertionError("Settings did not enter landscape: $details")
    }

    private fun isolated(initial: KeyboardOptions = KeyboardOptions(), voiceHold: Boolean = false,
        block: () -> Unit) {
        val original = KeyboardOptions.load(context)
        val originalHold = prefs.getBoolean("voiceHoldToInsert", false)
        try {
            initial.save(context)
            prefs.edit().putBoolean("voiceHoldToInsert", voiceHold).commit()
            block()
        } finally {
            original.save(context)
            prefs.edit().putBoolean("voiceHoldToInsert", originalHold).commit()
        }
    }

    @Test fun categoryPolicyResetsOnlyRenderedSettings() {
        val custom = KeyboardOptions(
            large = true, light = true, haptics = true, repeatGuard = true,
            numberRow = false, secondaryHints = false, keyHeightDp = 72, bottomPaddingDp = 24,
            deleteRepeat = false, holdDelayMs = 600, alignment = KeyboardAlignment.RIGHT,
            letterLayout = LetterLayout.AZERTY, extraKeys = false, autoCapitalize = false,
            arrowRepeat = false, keyBorders = false, suggestions = false, theme = ThemeMode.DARK,
            splitLandscape = true,
        )
        val values = SettingsDraftValues(custom, voiceHold = true)
        val expected = mapOf(
            "layout" to values.copy(options = custom.copy(
                numberRow = true, extraKeys = true, large = false, keyHeightDp = 0,
                bottomPaddingDp = 0, alignment = KeyboardAlignment.FULL,
                splitLandscape = false, letterLayout = LetterLayout.QWERTY)),
            "terminal" to values.copy(options = custom.copy(arrowRepeat = true)),
            "assistance" to values.copy(options = custom.copy(
                autoCapitalize = true, suggestions = true, secondaryHints = true)),
            "gestures" to values.copy(options = custom.copy(
                deleteRepeat = true, repeatGuard = false, holdDelayMs = 320, haptics = false)),
            "appearance" to values.copy(options = custom.copy(
                theme = ThemeMode.SYSTEM, keyBorders = true)),
            "voice" to values.copy(voiceHold = false),
        )
        expected.forEach { (category, result) ->
            assertTrue(SettingsResetPolicy.isCustomized(category, values))
            assertEquals(result, SettingsResetPolicy.resetCategory(category, values))
            assertFalse(SettingsResetPolicy.isCustomized(category, result))
        }
        assertEquals(values, SettingsResetPolicy.resetCategory("privacy", values))
        assertFalse(SettingsResetPolicy.isCustomized("privacy", values))
    }

    @Test fun individualResetIsNamedSearchableStagedAndPersistsOnlyAfterApply() = isolated(
        KeyboardOptions(numberRow = false, theme = ThemeMode.DARK, holdDelayMs = 600),
    ) {
        val initial = KeyboardOptions.load(context)
        val cancelled = open()
        try {
            main {
                assertTrue(all(cancelled).single {
                    it.contentDescription?.toString()?.startsWith("Layout & size,") == true
                }.contentDescription.toString().endsWith("Customized"))
                assertTrue(all(cancelled).single {
                    it.contentDescription?.toString()?.startsWith("Navigation & terminal,") == true
                }.contentDescription.toString().endsWith("Default"))
                all(cancelled).filterIsInstance<EditText>().single().setText("reset number row")
                assertEquals(1, all(cancelled).count {
                    it.contentDescription?.toString()?.startsWith("Layout & size,") == true
                })
                category(cancelled, "Layout & size")
                val numberRow = button(cancelled, "Number row") as CheckBox
                assertEquals("Number row, Customized", numberRow.contentDescription)
                val reset = described(cancelled, "Reset Number row to default")
                assertTrue(reset.isShown)
                reset.performClick()
                assertTrue(numberRow.isChecked)
                assertEquals("Number row, Default", numberRow.contentDescription)
                assertFalse(reset.isShown)
                assertEquals(initial, KeyboardOptions.load(context))
                cancelled.onBackPressed()
                button(cancelled, "Cancel").performClick()
            }
            instrumentation.waitForIdleSync()
            assertEquals(initial, KeyboardOptions.load(context))
        } finally {
            main { cancelled.finish() }
        }

        val applied = open()
        try {
            main {
                category(applied, "Layout & size")
                described(applied, "Reset Number row to default").performClick()
                button(applied, "Apply").performClick()
            }
            instrumentation.waitForIdleSync()
            assertEquals(initial.copy(numberRow = true), KeyboardOptions.load(context))
        } finally {
            main { applied.finish() }
        }

        val reopened = open()
        try {
            main {
                assertTrue(all(reopened).single {
                    it.contentDescription?.toString()?.startsWith("Appearance,") == true
                }.contentDescription.toString().endsWith("Customized"))
                category(reopened, "Layout & size")
                assertEquals("Number row, Default", button(reopened, "Number row").contentDescription)
                assertFalse(described(reopened, "Reset Number row to default").isShown)
                reopened.onBackPressed()
                category(reopened, "Holds & gestures")
                described(reopened, "Reset Hold timing to default").performClick()
                assertEquals("Hold timing: 320 ms (default)",
                    all(reopened).filterIsInstance<SeekBar>().single().contentDescription)
                button(reopened, "Apply").performClick()
            }
        } finally {
            main { reopened.finish() }
        }
        assertEquals(initial.copy(numberRow = true, holdDelayMs = 320), KeyboardOptions.load(context))
    }

    @Test fun categoryResetSurvivesRecreationAndKeepsOtherSettingsAndModels() = isolated(
        KeyboardOptions(numberRow = false, extraKeys = false, large = true, keyHeightDp = 72,
            bottomPaddingDp = 24, alignment = KeyboardAlignment.RIGHT,
            letterLayout = LetterLayout.AZERTY, splitLandscape = false,
            suggestions = false, haptics = true, theme = ThemeMode.DARK),
        voiceHold = true,
    ) {
        val initial = KeyboardOptions.load(context)
        val expected = SettingsResetPolicy.resetCategory("layout", SettingsDraftValues(initial, true))
        val installed = ModelStore.installed(context.noBackupFilesDir)
        val marker = File(context.noBackupFilesDir, "settings-category-reset-preserve.bin")
        check(!marker.exists())
        marker.writeText("keep")
        try {
            val cancelled = open()
            try {
                main {
                    category(cancelled, "Layout & size")
                    described(cancelled, "Reset Layout & size settings to default").performClick()
                    cancelled.onBackPressed()
                    button(cancelled, "Cancel").performClick()
                }
                instrumentation.waitForIdleSync()
                assertEquals(initial, KeyboardOptions.load(context))
                assertTrue(prefs.getBoolean("voiceHoldToInsert", false))
            } finally {
                main { cancelled.finish() }
            }

            ActivityScenario.launch(KeyboardSettingsActivity::class.java).use { scenario ->
                scenario.onActivity { activity ->
                    category(activity, "Layout & size")
                    described(activity, "Reset Layout & size settings to default").performClick()
                    assertTrue((button(activity, "Number row") as CheckBox).isChecked)
                    assertTrue((button(activity, "Full width") as RadioButton).isChecked)
                    assertFalse((button(activity, "Split keyboard in landscape") as CheckBox).isChecked)
                    assertTrue((button(activity, "QWERTY") as RadioButton).isChecked)
                    assertEquals(initial, KeyboardOptions.load(context))
                }
                scenario.recreate()
                scenario.onActivity { activity ->
                    assertEquals("Number row, Default", button(activity, "Number row").contentDescription)
                    assertFalse(described(activity, "Reset Layout & size settings to default").isShown)
                    button(activity, "Apply").performClick()
                }
            }
            assertEquals(expected.options, KeyboardOptions.load(context))
            assertEquals(expected.voiceHold, prefs.getBoolean("voiceHoldToInsert", false))
            assertEquals("keep", marker.readText())
            assertEquals(installed, ModelStore.installed(context.noBackupFilesDir))
        } finally {
            marker.delete()
        }
    }

    @Test fun alignmentAndSplitIndividualResetsKeepTheirExistingDependencyRules() = isolated(
        KeyboardOptions(alignment = KeyboardAlignment.RIGHT),
    ) {
        val initial = KeyboardOptions.load(context)
        val activity = open()
        try {
            main {
                category(activity, "Layout & size")
                described(activity, "Reset Keyboard alignment to default").performClick()
                assertTrue((button(activity, "Full width") as RadioButton).isChecked)
                assertFalse((button(activity, "Split keyboard in landscape") as CheckBox).isChecked)

                button(activity, "Split keyboard in landscape").performClick()
                assertTrue((button(activity, "Full width") as RadioButton).isChecked)
                assertTrue((button(activity, "Split keyboard in landscape") as CheckBox).isChecked)
                described(activity, "Reset Split keyboard in landscape to default").performClick()
                assertFalse((button(activity, "Split keyboard in landscape") as CheckBox).isChecked)
                assertTrue((button(activity, "Full width") as RadioButton).isChecked)

                button(activity, "Right hand").performClick()
                assertTrue((button(activity, "Right hand") as RadioButton).isChecked)
                assertFalse((button(activity, "Split keyboard in landscape") as CheckBox).isChecked)
                activity.onBackPressed()
                button(activity, "Cancel").performClick()
            }
            assertEquals(initial, KeyboardOptions.load(context))
        } finally {
            main { activity.finish() }
        }
    }

    @Test fun customizedResetActionsFitSyntheticNarrowLargeTextHierarchyInLandscape() = isolated(
        KeyboardOptions(theme = ThemeMode.DARK, keyBorders = false),
    ) {
        ActivityScenario.launch(KeyboardSettingsActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                category(activity, "Appearance")
                activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            }
            awaitLandscape(scenario)
            scenario.onActivity { activity ->
                val resetButtons = all(activity).filterIsInstance<Button>().filter {
                    it.isShown && it.contentDescription?.toString()?.startsWith("Reset ") == true
                }
                assertEquals(3, resetButtons.size)
                verifySyntheticHierarchy(activity, resetButtons)
            }
        }
    }

    /** Synthetic rendering only: this is not a physical-phone or system-font-scale claim. */
    private fun verifySyntheticHierarchy(activity: Activity, resetButtons: List<Button>) {
        val content = activity.findViewById<ViewGroup>(android.R.id.content)
        val root = content.getChildAt(0) as ViewGroup
        val rootIndex = content.indexOfChild(root)
        val rootParams = root.layoutParams
        val textSizes = descendants(root).filterIsInstance<TextView>().associateWith { it.textSize }
        content.removeViewAt(rootIndex)
        var scroll: ScrollView? = null
        var oldScrollX = 0
        var oldScrollY = 0
        try {
            textSizes.keys.forEach { it.setTextSize(TypedValue.COMPLEX_UNIT_SP, 24f) }
            val width = Ui.dp(activity, 320)
            val height = Ui.dp(activity, 240)
            root.measure(
                View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY),
            )
            root.layout(0, 0, root.measuredWidth, root.measuredHeight)
            assertEquals(width, root.width)
            assertEquals(height, root.height)
            val scrollView = descendants(root).filterIsInstance<ScrollView>().single()
            scroll = scrollView
            oldScrollX = scrollView.scrollX
            oldScrollY = scrollView.scrollY
            val column = scrollView.getChildAt(0) as ViewGroup
            val columnBounds = boundsIn(root, column)
            val contentBounds = Rect(columnBounds.left + column.paddingLeft, 0,
                columnBounds.right - column.paddingRight, root.height)
            resetButtons.forEachIndexed { index, reset ->
                val actionRow = reset.parent as View
                val rowInScroll = Rect(0, 0, actionRow.width, actionRow.height)
                scrollView.offsetDescendantRectToMyCoords(actionRow, rowInScroll)
                val rowContentTop = rowInScroll.top - scrollView.paddingTop
                scrollView.scrollTo(0, rowContentTop)
                val scrollBounds = boundsIn(root, scrollView)
                val resetBounds = boundsIn(root, reset)
                val visibleScrollHeight = scrollView.height - scrollView.paddingTop - scrollView.paddingBottom
                val maxScrollY = (column.height - visibleScrollHeight).coerceAtLeast(0)
                val geometry = "root=${root.width}x${root.height} " +
                    "rootPadding=${root.paddingLeft},${root.paddingTop},${root.paddingRight},${root.paddingBottom} " +
                    "scroll=$scrollBounds size=${scrollView.width}x${scrollView.height} " +
                    "scrollPadding=${scrollView.paddingLeft},${scrollView.paddingTop}," +
                    "${scrollView.paddingRight},${scrollView.paddingBottom} requestedY=$rowContentTop " +
                    "actualY=${scrollView.scrollY} maxY=$maxScrollY rowInScroll=$rowInScroll " +
                    "rowSize=${actionRow.width}x${actionRow.height} reset=$resetBounds " +
                    "resetSize=${reset.width}x${reset.height} content=$contentBounds"
                captureSyntheticHierarchyIfRequested(root, index)
                if (reset.text.toString() == "Reset category") {
                    val status = descendants(actionRow).filterIsInstance<TextView>().single {
                        it !is Button && it.text.toString() == "Customized"
                    }
                    assertEquals("Category Customized status wrapped; $geometry", 1, status.lineCount)
                    assertEquals("Category Customized status was truncated; $geometry",
                        status.text.length, status.layout.getLineEnd(0))
                    assertEquals("Category Customized status was ellipsized; $geometry",
                        0, status.layout.getEllipsisCount(0))
                }
                assertTrue("${reset.contentDescription} was not fully visible in the synthetic viewport; $geometry",
                    resetBounds.top >= scrollBounds.top && resetBounds.bottom <= scrollBounds.bottom)
                assertTrue("${reset.contentDescription} escaped the padded content bounds; $geometry",
                    resetBounds.left >= contentBounds.left && resetBounds.right <= contentBounds.right)
                assertTrue("${reset.contentDescription} lost its touch height; $geometry",
                    reset.height >= Ui.dp(activity, 48))
                assertTrue("${reset.contentDescription} lost its touch width; $geometry",
                    reset.width >= Ui.dp(activity, 48))
                descendants(scrollView).filter { control ->
                    control.visibility == View.VISIBLE && (control is Button || control is CheckBox ||
                        control is RadioButton || control is SeekBar)
                }.forEach { control ->
                    val bounds = boundsIn(root, control)
                    if (Rect.intersects(bounds, scrollBounds)) {
                        assertTrue("Visible ${control.contentDescription ?: (control as? TextView)?.text} " +
                            "escaped the synthetic content width", bounds.left >= contentBounds.left &&
                            bounds.right <= contentBounds.right)
                    }
                }
            }
        } finally {
            scroll?.scrollTo(oldScrollX, oldScrollY)
            textSizes.forEach { (view, size) -> view.setTextSize(TypedValue.COMPLEX_UNIT_PX, size) }
            if (root.parent == null) content.addView(root, rootIndex, rootParams)
            content.requestLayout()
        }
    }

    private fun boundsIn(root: ViewGroup, target: View): Rect = Rect().also {
        target.getDrawingRect(it)
        root.offsetDescendantRectToMyCoords(target, it)
    }

    private fun captureSyntheticHierarchyIfRequested(root: View, index: Int) {
        val name = InstrumentationRegistry.getArguments().getString("settingsResetScreenshots") ?: return
        require(name.matches(Regex("[a-zA-Z0-9_-]{1,40}")))
        val directory = File(checkNotNull(context.getExternalFilesDir(null)), name).apply { mkdirs() }
        val bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888)
        try {
            root.draw(Canvas(bitmap))
            File(directory, "synthetic-settings-reset-hierarchy-${index + 1}.png").outputStream().use {
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
            }
        } finally {
            bitmap.recycle()
        }
    }
}
