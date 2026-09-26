package org.utterleaf.voice

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.provider.Settings
import android.view.View
import android.view.ViewGroup
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.SdkSuppress
import androidx.test.platform.app.InstrumentationRegistry
import java.util.concurrent.atomic.AtomicReference
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Live fixture evidence for host rotation followed by an explicit IME reopen. */
@RunWith(AndroidJUnit4::class)
class KeyboardLifecycleTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun shell(command: String) = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command),
    ).bufferedReader().use { it.readText() }

    private fun <T> main(block: () -> T): T {
        val result = AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }

    private fun await(message: String, condition: () -> Boolean) {
        val deadline = android.os.SystemClock.elapsedRealtime() + 10_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return
            Thread.sleep(50)
        }
        throw AssertionError(message)
    }

    private fun findNode(description: String): AccessibilityNodeInfo? {
        if (android.os.Build.VERSION.SDK_INT >= 34) instrumentation.uiAutomation.clearCache()
        fun find(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (node.contentDescription?.toString() == description) return node
            for (index in 0 until node.childCount) node.getChild(index)?.let(::find)?.let { return it }
            return null
        }
        return instrumentation.uiAutomation.windows.asSequence()
            .filter { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .mapNotNull { it.root?.let(::find) }
            .firstOrNull()
    }

    private fun press(description: String) {
        var target: AccessibilityNodeInfo? = null
        await("Missing enabled $description") {
            findNode(description)?.takeIf { it.isEnabled }?.also { target = it } != null
        }
        if (target?.performAction(AccessibilityNodeInfo.ACTION_CLICK) != true) {
            throw AssertionError("Enabled $description rejected its single click")
        }
        instrumentation.waitForIdleSync()
    }

    private fun descendants(view: View): List<View> = listOf(view) + if (view is ViewGroup) {
        (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) }
    } else {
        emptyList()
    }

    private fun currentSurface(): KeyboardSurface? = main {
        android.view.inspector.WindowInspector.getGlobalWindowViews().flatMap(::descendants)
            .filterIsInstance<KeyboardSurface>()
            .singleOrNull { it.isShown }
    }

    private fun currentButton(description: String): Button = main {
        android.view.inspector.WindowInspector.getGlobalWindowViews().flatMap(::descendants)
            .filterIsInstance<Button>()
            .single { it.isShown && it.contentDescription?.toString() == description }
    }

    private fun currentActivity(
        scenario: ActivityScenario<KeyboardTestActivity>,
    ): KeyboardTestActivity {
        var current: KeyboardTestActivity? = null
        scenario.onActivity { current = it }
        return checkNotNull(current)
    }

    private fun awaitOrientation(
        scenario: ActivityScenario<KeyboardTestActivity>,
        previous: KeyboardTestActivity?,
        expected: Int,
        phase: String,
    ): KeyboardTestActivity {
        val deadline = android.os.SystemClock.elapsedRealtime() + 10_000
        var observed: KeyboardTestActivity? = null
        var details = "not sampled"
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            val sample = runCatching { currentActivity(scenario) }
            sample.onSuccess { activity ->
                observed = activity
                val orientation = main { activity.resources.configuration.orientation }
                val focused = main { activity.hasWindowFocus() }
                details = "orientation=$orientation, focused=$focused, recreated=${activity !== previous}"
                if (orientation == expected && focused && (previous == null || activity !== previous)) {
                    return activity
                }
            }.onFailure { details = "activity unavailable: ${it.javaClass.simpleName}: ${it.message}" }
            Thread.sleep(50)
        }
        throw AssertionError(
            "$phase did not produce a focused recreated activity in orientation=$expected; " +
                "$details, activityPresent=${observed != null}",
        )
    }

    private fun requestOrientation(
        scenario: ActivityScenario<KeyboardTestActivity>,
        previous: KeyboardTestActivity,
        requested: Int,
        expected: Int,
        phase: String,
    ): KeyboardTestActivity {
        scenario.onActivity { it.requestedOrientation = requested }
        return awaitOrientation(scenario, previous, expected, phase)
    }

    private fun establishPortrait(
        scenario: ActivityScenario<KeyboardTestActivity>,
    ): KeyboardTestActivity {
        val before = currentActivity(scenario)
        val alreadyPortrait = main {
            before.resources.configuration.orientation == Configuration.ORIENTATION_PORTRAIT
        }
        scenario.onActivity { it.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT }
        return if (alreadyPortrait) {
            awaitOrientation(scenario, null, Configuration.ORIENTATION_PORTRAIT, "Initial portrait")
        } else {
            awaitOrientation(scenario, before, Configuration.ORIENTATION_PORTRAIT, "Initial portrait")
        }
    }

    private fun showKeyboardOnce(
        scenario: ActivityScenario<KeyboardTestActivity>,
        manager: InputMethodManager,
    ): KeyboardTestActivity {
        val activity = currentActivity(scenario)
        scenario.onActivity { it.editor.requestFocus() }
        await("Portrait editor never became active") { main { manager.isActive(activity.editor) } }
        scenario.onActivity {
            manager.restartInput(it.editor)
            manager.showSoftInput(it.editor, InputMethodManager.SHOW_IMPLICIT)
        }
        await("Typing keyboard did not appear after one restart/show request") {
            findNode("Editing tools") != null && currentSurface() != null
        }
        return activity
    }

    private fun openExtraKeysAndEnableControl() {
        press("Editing tools")
        await("Editing tools did not open after its single click") {
            findNode("Select neighboring word") != null
        }
        press("Extra keys")
        await("Accessory keys did not open after its single click") {
            findNode("Control off") != null && findNode("Escape") != null
        }
        press("Control off")
        await("Control modifier did not arm after its single click") {
            findNode("Control on") != null
        }
    }

    private fun assertDailyResetAndOldKeyInert(
        phase: String,
        activity: KeyboardTestActivity,
        oldSurface: KeyboardSurface,
        oldKey: Button,
        literal: String,
    ): KeyboardSurface {
        var replacement: KeyboardSurface? = null
        val deadline = android.os.SystemClock.elapsedRealtime() + 10_000
        var observation = "not sampled"
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            val surface = currentSurface()
            val editingTools = findNode("Editing tools") != null
            val controlOn = findNode("Control on") != null
            val controlOff = findNode("Control off") != null
            val escape = findNode("Escape") != null
            val daily = editingTools && !controlOn && !controlOff && !escape
            observation = "surfacePresent=${surface != null}, " +
                "surfaceReplaced=${surface != null && surface !== oldSurface}, " +
                "labels={editingTools=$editingTools, controlOn=$controlOn, " +
                "controlOff=$controlOff, escape=$escape}, " +
                "defaultIme=${Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)}"
            if (surface != null && surface !== oldSurface && daily) replacement = surface
            if (replacement != null) break
            Thread.sleep(50)
        }
        if (replacement == null) {
            throw AssertionError(
                "$phase did not replace the keyboard surface and restore the daily layer; $observation",
            )
        }
        assertNotSame("$phase reused the old keyboard surface", oldSurface, replacement)
        assertTrue("$phase left the prior literal key attached", main { !oldKey.isAttachedToWindow })
        main { oldKey.performClick() }
        instrumentation.waitForIdleSync()
        assertEquals("$phase accepted a stale key callback", "", main { activity.editor.text.toString() })
        press(literal)
        await("$phase replacement keyboard did not commit $literal") {
            main { activity.editor.text.toString() == literal }
        }
        return checkNotNull(replacement)
    }

    private fun reopenAfterRotationOnce(
        scenario: ActivityScenario<KeyboardTestActivity>,
        activity: KeyboardTestActivity,
        manager: InputMethodManager,
        phase: String,
    ) {
        scenario.onActivity {
            check(it === activity) { "$phase changed activity before refocus" }
            it.editor.requestFocus()
        }
        await("$phase editor did not become active after refocus") {
            main { manager.isActive(activity.editor) }
        }
        var accepted = false
        scenario.onActivity {
            check(it === activity) { "$phase changed activity before IME reopen" }
            accepted = manager.showSoftInput(it.editor, InputMethodManager.SHOW_IMPLICIT)
        }
        await(
            "$phase IME reopen did not expose a surface after one show request; " +
                "showAccepted=$accepted, editorFocused=${main { activity.editor.hasFocus() }}, " +
                "windowFocused=${main { activity.hasWindowFocus() }}",
        ) { currentSurface() != null }
    }

    private fun reopenExtraKeysWithControlOff(phase: String) {
        press("Editing tools")
        await("$phase editing tools did not open") { findNode("Select neighboring word") != null }
        press("Extra keys")
        await("$phase did not reopen accessory keys with cleared modifiers") {
            findNode("Control off") != null && findNode("Control on") == null
        }
    }

    private fun restoreOrientation(
        scenario: ActivityScenario<KeyboardTestActivity>,
        originalRequested: Int,
        originalConfiguration: Int,
    ) {
        val requested = when (originalConfiguration) {
            Configuration.ORIENTATION_LANDSCAPE -> ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            else -> ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
        }
        val current = currentActivity(scenario)
        val alreadyRestored = main {
            current.resources.configuration.orientation == originalConfiguration
        }
        if (!alreadyRestored && originalConfiguration != Configuration.ORIENTATION_UNDEFINED) {
            scenario.onActivity { it.requestedOrientation = requested }
            awaitOrientation(scenario, current, originalConfiguration, "Original orientation restore")
        }
        scenario.onActivity { it.requestedOrientation = originalRequested }
    }

    @Test
    @SdkSuppress(minSdkVersion = 29)
    fun portraitLandscapePortraitRebuildsImeAndClearsTransientTools() {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val id = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previousIme = Settings.Secure.getString(
            app.contentResolver,
            Settings.Secure.DEFAULT_INPUT_METHOD,
        )
        val wasEnabled = manager.enabledInputMethodList.any { it.id == id }
        val options = KeyboardOptions.load(app)
        val automation = instrumentation.uiAutomation
        val automationFlags = automation.serviceInfo.flags
        var scenario: ActivityScenario<KeyboardTestActivity>? = null
        var originalRequested = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        var originalConfiguration = Configuration.ORIENTATION_UNDEFINED
        var primaryFailure: Throwable? = null
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                flags = automationFlags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            shell("ime enable $id")
            shell("ime set $id")
            options.copy(extraKeys = true).save(app)
            ImeTestReadiness.awaitDefaultImeStable(app, manager, id, "Lifecycle IME setup")

            scenario = ActivityScenario.launch(KeyboardTestActivity::class.java)
            currentActivity(scenario).also { activity ->
                originalRequested = main { activity.requestedOrientation }
                originalConfiguration = main { activity.resources.configuration.orientation }
            }
            var activity = establishPortrait(scenario)
            activity = showKeyboardOnce(scenario, manager)
            assertEquals(Configuration.ORIENTATION_PORTRAIT, main {
                activity.resources.configuration.orientation
            })

            openExtraKeysAndEnableControl()
            var oldSurface = checkNotNull(currentSurface())
            var oldKey = currentButton("x")
            val portraitActivity = activity
            activity = requestOrientation(
                scenario,
                portraitActivity,
                ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE,
                Configuration.ORIENTATION_LANDSCAPE,
                "Portrait-to-landscape rotation",
            )
            reopenAfterRotationOnce(
                scenario,
                activity,
                manager,
                "Portrait-to-landscape rotation",
            )
            val landscapeSurface = assertDailyResetAndOldKeyInert(
                "Portrait-to-landscape rotation",
                activity,
                oldSurface,
                oldKey,
                "x",
            )
            reopenExtraKeysWithControlOff("Landscape")
            press("Control off")
            await("Landscape control modifier did not arm") { findNode("Control on") != null }
            main { activity.editor.text.clear() }

            oldSurface = landscapeSurface
            oldKey = currentButton("x")
            val landscapeActivity = activity
            activity = requestOrientation(
                scenario,
                landscapeActivity,
                ActivityInfo.SCREEN_ORIENTATION_PORTRAIT,
                Configuration.ORIENTATION_PORTRAIT,
                "Landscape-to-portrait rotation",
            )
            reopenAfterRotationOnce(
                scenario,
                activity,
                manager,
                "Landscape-to-portrait rotation",
            )
            assertDailyResetAndOldKeyInert(
                "Landscape-to-portrait rotation",
                activity,
                oldSurface,
                oldKey,
                "y",
            )
            reopenExtraKeysWithControlOff("Restored portrait")
        } catch (error: Throwable) {
            primaryFailure = error
            throw error
        } finally {
            ImeTestReadiness.cleanupPreserving(
                primaryFailure,
                {
                    scenario?.let {
                        restoreOrientation(it, originalRequested, originalConfiguration)
                    }
                },
                { scenario?.close() },
                {
                    if (!previousIme.isNullOrBlank()) {
                        shell("ime set $previousIme")
                        ImeTestReadiness.awaitDefaultImeStable(
                            app,
                            manager,
                            previousIme,
                            "Previous IME restore",
                        )
                    }
                },
                { if (!wasEnabled) shell("ime disable $id") },
                { options.save(app) },
                {
                    automation.serviceInfo = automation.serviceInfo.apply {
                        flags = automationFlags
                    }
                },
            )
        }
    }
}
