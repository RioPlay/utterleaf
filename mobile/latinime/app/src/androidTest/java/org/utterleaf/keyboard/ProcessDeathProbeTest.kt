package org.utterleaf.keyboard

import android.content.Intent
import android.os.Process
import android.os.SystemClock
import android.preference.PreferenceManager
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.SeekBar
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.R
import com.android.inputmethod.latin.settings.DebugSettings
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.ObjectInputStream
import java.io.ObjectOutputStream

/** External-only SIGKILL/cold-launch probe. Run tools/process_death_probe.py, not alone.
 * This does not simulate saved-task restoration or establish real IME session recovery.
 */
@RunWith(AndroidJUnit4::class)
class ProcessDeathProbeTest {
    @Test fun externalProcessDeath() {
        val arguments = InstrumentationRegistry.getArguments()
        val phase = arguments.getString("deathPhase")
        assumeTrue("Requires external PID-killing coordinator", phase != null)
        val token = requireNotNull(arguments.getString("deathToken"))
        require(token.matches(Regex("[a-f0-9]{32}")))
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val app = instrumentation.targetContext
        val directory = File(app.noBackupFilesDir, "process-death-$token")
        val backup = File(directory, "preferences.bin")
        val sentinel = File(directory, "asset-canary")
        val prefs = PreferenceManager.getDefaultSharedPreferences(app)
        when (phase) {
            "prepare" -> {
                check(directory.mkdir()) { "Probe directory already exists" }
                val original = HashMap<String, Any?>()
                prefs.all.forEach { (key, value) ->
                    original[key] = if (value is Set<*>) HashSet(value) else value
                }
                ObjectOutputStream(backup.outputStream()).use { it.writeObject(original) }
                sentinel.writeText("synthetic-asset-$token")
                val targetHeight = if (ComfortPreferences(app).read().heightPercent == 130) 125 else 130
                File(directory, "expected-height").writeText(targetHeight.toString())
                ActivityScenario.launch<ComfortActivity>(Intent(app, ComfortActivity::class.java)).use { screen ->
                    screen.onActivity { activity ->
                        val views = descendants(activity.findViewById(android.R.id.content))
                        val height = views.filterIsInstance<SeekBar>().first()
                        assertTrue(height.performAccessibilityAction(
                            AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.id,
                            Bundle().apply { putFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE,
                                (targetHeight - 75).toFloat()) }))
                        assertTrue(views.filterIsInstance<Button>().single {
                            it.text == app.getString(R.string.comfort_apply)
                        }.performClick())
                        views.filterIsInstance<EditText>().single().setText("synthetic-practice-$token")
                    }
                    // Observe the production apply reaching disk; do not substitute a test commit.
                    val xml = File(app.applicationInfo.dataDir,
                        "shared_prefs/${app.packageName}_preferences.xml")
                    val expectedScale = "value=\"${targetHeight / 100f}\""
                    fun persistedHeight() = runCatching { xml.readLines().any {
                        it.contains("name=\"${DebugSettings.PREF_KEYBOARD_HEIGHT_SCALE}\"") &&
                            it.contains(expectedScale)
                    } }.getOrDefault(false)
                    val deadline = SystemClock.uptimeMillis() + 10_000
                    while (!persistedHeight() &&
                        SystemClock.uptimeMillis() < deadline) SystemClock.sleep(20)
                    assertTrue("Height Apply did not reach disk", persistedHeight())
                    assertEquals(targetHeight, ComfortPreferences(app).read().heightPercent)
                    screen.onActivity { activity ->
                        assertEquals("synthetic-practice-$token", descendants(
                            activity.findViewById(android.R.id.content)).filterIsInstance<EditText>()
                            .single().text.toString())
                    }
                    File(directory, "ready").writeText(Process.myPid().toString())
                    // Coordinator kills this process while the practice canary is live.
                    SystemClock.sleep(120_000)
                    fail("Coordinator did not kill the prepared process")
                }
            }
            "verify" -> {
                assertNotEquals(File(directory, "ready").readText().toInt(), Process.myPid())
                val targetHeight = File(directory, "expected-height").readText().toInt()
                assertEquals(targetHeight, ComfortPreferences(app).read().heightPercent)
                assertEquals("synthetic-asset-$token", sentinel.readText())
                ActivityScenario.launch<ComfortActivity>(Intent(app, ComfortActivity::class.java)).use { screen ->
                    screen.onActivity { activity ->
                        val views = descendants(activity.findViewById(android.R.id.content))
                        assertEquals("", views.filterIsInstance<EditText>().single().text.toString())
                        assertEquals(targetHeight - 75, views.filterIsInstance<SeekBar>().first().progress)
                    }
                }
                File(directory, "verified").writeText(Process.myPid().toString())
            }
            "restore" -> {
                if (backup.exists()) {
                    @Suppress("UNCHECKED_CAST")
                    val original = ObjectInputStream(backup.inputStream()).use {
                        it.readObject() as Map<String, Any?>
                    }
                    val edit = prefs.edit().clear()
                    original.forEach { (key, value) -> when (value) {
                        is String -> edit.putString(key, value)
                        is Boolean -> edit.putBoolean(key, value)
                        is Int -> edit.putInt(key, value)
                        is Long -> edit.putLong(key, value)
                        is Float -> edit.putFloat(key, value)
                        is Set<*> -> edit.putStringSet(key, value.map { it as String }.toSet())
                        else -> error("Unsupported preference type")
                    } }
                    assertTrue(edit.commit())
                    assertEquals(original, prefs.all)
                    check(backup.delete())
                }
                // Delete only this invocation's synthetic files, never user assets.
                listOf("asset-canary", "ready", "verified", "expected-height").forEach { name ->
                    File(directory, name).let { if (it.exists()) check(it.delete()) }
                }
                if (directory.exists()) check(directory.delete())
            }
            else -> error("Unknown phase")
        }
    }

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
        else emptyList()
}
