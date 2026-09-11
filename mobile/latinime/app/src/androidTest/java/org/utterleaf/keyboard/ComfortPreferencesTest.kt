package org.utterleaf.keyboard

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.accessibility.AccessibilityNodeInfo
import android.view.inspector.WindowInspector
import android.widget.Button
import android.widget.SeekBar
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.R
import com.android.inputmethod.latin.settings.DebugSettings
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class ComfortPreferencesTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    @Test fun boundedPreferencesRecoverFromInvalidValuesWithoutClearingUnrelatedData() {
        val preferences = app.getSharedPreferences("synthetic-comfort-test", Context.MODE_PRIVATE)
        val store = ComfortPreferences(preferences)
        try {
            preferences.edit().clear().putString("unrelated", "kept").commit()
            store.save(ComfortOptions(heightPercent = 999, bottomSpaceDp = -1, lightTheme = true))
            assertEquals(135, store.read().heightPercent)
            assertEquals(0, store.read().bottomSpaceDp)
            preferences.edit().putFloat(DebugSettings.PREF_KEYBOARD_HEIGHT_SCALE, Float.NaN).commit()
            assertEquals(100, store.read().heightPercent)
            preferences.edit().putString(DebugSettings.PREF_KEYBOARD_HEIGHT_SCALE, "invalid").commit()
            assertEquals(100, store.read().heightPercent)
            store.reset()
            assertEquals(ComfortOptions(), store.read())
            assertEquals("kept", preferences.getString("unrelated", null))
        } finally { preferences.edit().clear().commit() }
    }

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
        else emptyList()

    private fun pressDialog(resource: Int) {
        val deadline = SystemClock.uptimeMillis() + 5_000
        while (SystemClock.uptimeMillis() < deadline) {
            instrumentation.waitForIdleSync()
            var pressed: Button? = null
            instrumentation.runOnMainSync {
                val button = WindowInspector.getGlobalWindowViews().flatMap(::descendants)
                    .filterIsInstance<Button>().singleOrNull { it.isShown && it.text == app.getString(resource) }
                if (button?.performClick() == true) pressed = button
            }
            if (pressed != null) {
                while (SystemClock.uptimeMillis() < deadline) {
                    instrumentation.waitForIdleSync()
                    var detached = false
                    instrumentation.runOnMainSync { detached = !pressed!!.isAttachedToWindow }
                    if (detached) return
                    SystemClock.sleep(20)
                }
                fail("Dialog did not close after its action")
            }
            SystemClock.sleep(20)
        }
        fail("Dialog action unavailable: ${app.getString(resource)}")
    }

    @Test fun draftsSurviveRecreationDiscardDoesNotSaveAndResetPreservesAssets() {
        val store = ComfortPreferences(app)
        val sentinel = File(app.noBackupFilesDir, "synthetic-preservation-${UUID.randomUUID()}")
        sentinel.writeText("synthetic-model-sentinel")
        store.reset()
        try {
            ActivityScenario.launch<ComfortActivity>(Intent(app, ComfortActivity::class.java)).use { screen ->
                fun views(activity: ComfortActivity) = descendants(activity.findViewById(android.R.id.content))
                fun height(activity: ComfortActivity) = views(activity).filterIsInstance<SeekBar>().first()
                screen.onActivity { activity ->
                    val page = views(activity).filterIsInstance<android.widget.ScrollView>().single()
                    val margin = (20 * activity.resources.displayMetrics.density).toInt()
                    assertTrue(page.paddingLeft >= margin)
                    assertTrue(page.paddingRight >= margin)
                }
                fun press(resource: Int) = screen.onActivity { activity ->
                    assertTrue(views(activity).filterIsInstance<Button>().single { it.text == app.getString(resource) }.performClick())
                }
                fun adjust() = screen.onActivity { activity ->
                    assertTrue(height(activity).performAccessibilityAction(
                        AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.id,
                        Bundle().apply { putFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE, 55f) }))
                    assertEquals(app.getString(R.string.comfort_height, 130), height(activity).contentDescription)
                }
                adjust()
                assertEquals(100, store.read().heightPercent)
                screen.recreate()
                screen.onActivity { assertEquals(app.getString(R.string.comfort_height, 130), height(it).contentDescription) }
                press(R.string.comfort_discard)
                screen.onActivity { assertEquals(app.getString(R.string.comfort_height, 100), height(it).contentDescription) }
                adjust()
                press(R.string.comfort_apply)
                assertEquals(130, ComfortPreferences(app).read().heightPercent)
                press(R.string.comfort_reset)
                pressDialog(android.R.string.cancel)
                assertEquals(130, store.read().heightPercent)
                press(R.string.comfort_reset)
                pressDialog(R.string.comfort_reset_confirm)
                instrumentation.waitForIdleSync()
                assertEquals(ComfortOptions(), store.read())
                screen.onActivity { assertEquals(app.getString(R.string.comfort_height, 100), height(it).contentDescription) }
                assertEquals("synthetic-model-sentinel", sentinel.readText())
                var capture: ComfortActivity? = null
                screen.onActivity { capture = it }
                captureSyntheticUi(capture!!, "keyboard-comfort")
            }
        } finally {
            store.reset()
            check(sentinel.delete())
        }
    }
}
