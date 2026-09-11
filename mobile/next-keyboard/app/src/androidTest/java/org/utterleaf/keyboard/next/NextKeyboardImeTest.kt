package org.utterleaf.keyboard.next

import android.content.Intent
import android.content.pm.ApplicationInfo
import android.graphics.Rect
import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.provider.Settings
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.view.inspector.WindowInspector
import android.widget.EditText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.SdkSuppress
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.utterleaf.keyboard.next.core.Outcome
import org.utterleaf.keyboard.next.settings.PrivacyPreferences
import org.utterleaf.keyboard.next.ui.KeyboardSurface
import java.io.File

/** Real framework-created IME, screen-coordinate touches, and disposable synthetic text. */
@RunWith(AndroidJUnit4::class)
@SdkSuppress(minSdkVersion = 30)
class NextKeyboardImeTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext
    private fun shell(command: String) = ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command)
    ).bufferedReader().use { it.readText().trim() }
    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }
    private fun await(label: String, block: () -> Boolean) {
        val deadline = SystemClock.uptimeMillis() + 10_000
        while (SystemClock.uptimeMillis() < deadline) {
            instrumentation.waitForIdleSync()
            if (main(block)) return
            SystemClock.sleep(20)
        }
        fail(label)
    }
    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()
    private fun keyboard(): KeyboardSurface? = WindowInspector.getGlobalWindowViews()
        .flatMap(::descendants).filterIsInstance<KeyboardSurface>()
        .singleOrNull { it.isShown && it.isLaidOut && !it.isLayoutRequested && it.width > 0 }

    private fun show(activity: CoreTestActivity, field: EditText) {
        await("Fixture must own a focused window before requesting IME") { activity.hasWindowFocus() }
        main {
            field.requestFocus()
            field.setSelection(field.length())
            activity.getSystemService(InputMethodManager::class.java).showSoftInput(field, 0)
        }
        await("Framework keyboard did not become visible") {
            val ime = keyboard()?.context as? NextKeyboardIme
            field.hasFocus() && !activity.imeAnimating &&
                activity.window.decorView.rootWindowInsets?.isVisible(WindowInsets.Type.ime()) == true &&
                ime?.isInputViewShown == true && ime.currentInputEditorInfo?.fieldId == field.id &&
                ime.gateway.currentToken() != null
        }
    }

    private fun point(label: String): Pair<Float, Float> = main {
        val view = keyboard() ?: error("No real IME view")
        val key = view.keyBounds(label) ?: error("Missing key $label")
        val location = IntArray(2); view.getLocationOnScreen(location)
        val x = location[0] + (key.left + key.right) / 2f
        val y = location[1] + (key.top + key.bottom) / 2f
        // Global visible rectangles use the window's coordinates; injected events use the screen.
        val visible = Rect(); assertTrue(view.getLocalVisibleRect(visible))
        visible.offset(location[0], location[1])
        val metrics = view.context.getSystemService(WindowManager::class.java).maximumWindowMetrics
        val safe = Rect(metrics.bounds)
        val navigation = metrics.windowInsets.getInsets(WindowInsets.Type.navigationBars())
        safe.inset(navigation.left, navigation.top, navigation.right, navigation.bottom)
        val geometry = "key=$label center=$x,$y view=${location.contentToString()} visible=$visible safe=$safe"
        assertTrue("Key center is outside visible keyboard: $geometry", visible.contains(x.toInt(), y.toInt()))
        assertTrue("Key center overlaps navigation: $geometry", safe.contains(x.toInt(), y.toInt()))
        x to y
    }

    private fun touch(label: String) {
        val (x, y) = point(label)
        val down = SystemClock.uptimeMillis()
        listOf(MotionEvent.ACTION_DOWN, MotionEvent.ACTION_UP).forEach { action ->
            val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, x, y, 0)
            event.source = InputDevice.SOURCE_TOUCHSCREEN
            try { assertTrue(instrumentation.uiAutomation.injectInputEvent(event, true)) } finally { event.recycle() }
        }
        instrumentation.waitForIdleSync()
    }

    private fun type(text: String) = text.forEach { touch(if (it == ' ') "space" else it.toString()) }

    private fun twoThumbs() {
        val positions = listOf(point("a"), point("s"))
        val down = SystemClock.uptimeMillis()
        fun send(action: Int, ids: List<Int>) {
            val props = ids.map { id -> MotionEvent.PointerProperties().apply { this.id = id; toolType = MotionEvent.TOOL_TYPE_FINGER } }.toTypedArray()
            val coords = ids.map { id -> MotionEvent.PointerCoords().apply {
                x = positions[id].first; y = positions[id].second; pressure = 1f; size = 1f
            } }.toTypedArray()
            val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, ids.size, props, coords,
                0, 0, 1f, 1f, 0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0)
            try { assertTrue(instrumentation.uiAutomation.injectInputEvent(event, true)) } finally { event.recycle() }
        }
        send(MotionEvent.ACTION_DOWN, listOf(0))
        send(MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(0, 1))
        send(MotionEvent.ACTION_POINTER_UP, listOf(0, 1))
        send(MotionEvent.ACTION_UP, listOf(1))
        instrumentation.waitForIdleSync()
    }

    private fun withIme(block: (CoreTestActivity) -> Unit) {
        val oldIme = shell("settings get secure default_input_method")
        val oldHardware = shell("settings get secure show_ime_with_hard_keyboard")
        val component = "${app.packageName}/.NextKeyboardIme"
        val enabled = shell("ime list -s").lineSequence().contains(component)
        var activity: CoreTestActivity? = null
        try {
            shell("settings put secure show_ime_with_hard_keyboard 1")
            shell("ime enable $component"); shell("ime set $component")
            activity = instrumentation.startActivitySync(Intent(app, CoreTestActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)) as CoreTestActivity
            block(activity)
        } finally {
            activity?.let { main { it.finish() } }
            if (oldIme.isNotBlank() && oldIme != "null") shell("ime set $oldIme")
            if (!enabled) shell("ime disable $component")
            if (oldHardware == "null") shell("settings delete secure show_ime_with_hard_keyboard")
            else shell("settings put secure show_ime_with_hard_keyboard $oldHardware")
        }
    }

    @Test fun actualTypingSymbolsDeleteAndTwoThumbs() = withIme { activity ->
        show(activity, activity.first)
        type("hello world")
        await("Typed text missing") { activity.first.text.toString() == "hello world" }
        touch("⌫")
        await("Direct deletion failed") { activity.first.text.toString() == "hello worl" }
        touch("?123"); type("29")
        await("Symbols must include digits") { activity.first.text.toString() == "hello worl29" }
        touch("ABC")
        twoThumbs()
        await("Overlapping pointers must each commit exactly once") { activity.first.text.toString() == "hello worl29as" }
    }

    @Test fun fieldRestartHideAndPrivatePolicyRejectOldTokens() = withIme { activity ->
        show(activity, activity.first); type("a")
        val ime = main { keyboard()!!.context as NextKeyboardIme }
        val first = main { ime.gateway.currentToken()!! }
        show(activity, activity.second)
        await("Field switch did not retire token") { ime.gateway.currentToken()?.session != first.session }
        assertEquals(Outcome.STALE, main { ime.gateway.commit(first, "stale") })
        type("s")
        val beforeRestart = main { ime.gateway.currentToken()!! }
        main { activity.getSystemService(InputMethodManager::class.java).restartInput(activity.second) }
        await("Same editor restart did not retire token") { ime.gateway.currentToken()?.session != beforeRestart.session }
        assertEquals(Outcome.STALE, main { ime.gateway.commit(beforeRestart, "stale") })
        val beforeHide = main { ime.gateway.currentToken()!! }
        main { activity.getSystemService(InputMethodManager::class.java).hideSoftInputFromWindow(activity.second.windowToken, 0) }
        await("Hide did not retire editor") { ime.gateway.currentToken() == null }
        assertEquals(Outcome.STALE, main { ime.gateway.commit(beforeHide, "stale") })
        show(activity, activity.second); type("d")
        show(activity, activity.password)
        await("Password policy did not become required") { ime.gateway.currentPolicy()?.forcedIncognito == true }
        type("a"); touch("⌫")
        await("Password deletion failed") { activity.password.length() == 0 }
        show(activity, activity.privateField)
        await("No-learning policy not enforced") { ime.gateway.currentPolicy()?.noPersonalizedLearning == true }
        main { assertEquals("a", activity.first.text.toString()); assertEquals("sd", activity.second.text.toString()) }
    }

    @Test fun incognitoPersistenceAndSyntheticScreenshots() = withIme { activity ->
        val preferences = main { PrivacyPreferences.get(app) }
        await("Privacy preferences did not initialize") { preferences.state.ready && !preferences.state.saving }
        val original = main { preferences.state.incognito }
        try {
            main { preferences.setIncognito(false) }
            await("Off preference did not save") { !preferences.state.saving && !preferences.state.incognito }
            show(activity, activity.first); type("hello from utterleaf")
            await("Synthetic capture must contain the complete touch-typed text") { activity.first.text.toString() == "hello from utterleaf" }
            capture(activity, "next-core-typing")
            val ime = main { keyboard()!!.context as NextKeyboardIme }
            val old = main { ime.gateway.currentToken()!! }
            main { preferences.setIncognito(true) }
            await("Incognito not applied") { ime.gateway.effectiveIncognito() && !preferences.state.saving }
            assertEquals(Outcome.STALE, main { ime.gateway.commit(old, "stale") })
            main { preferences.resetPreferences() }
            assertTrue(main { preferences.state.incognito })
            type(" in private")
            capture(activity, "next-core-incognito")
            show(activity, activity.password)
            capture(activity, "next-core-password")
        } finally {
            main { preferences.setIncognito(original) }
            await("Privacy restore did not finish") { !preferences.state.saving }
        }
    }

    private fun capture(activity: CoreTestActivity, name: String) {
        if (InstrumentationRegistry.getArguments().getString("captureScreenshots") != "true") return
        assertTrue(app.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0)
        require(name.matches(Regex("[a-z-]+")))
        val restored = mutableListOf<Pair<View, Int>>()
        try {
            main {
                assertTrue(activity.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE != 0)
                activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
                WindowInspector.getGlobalWindowViews().filter { it.isShown && descendants(it).any { child -> child is KeyboardSurface } }.forEach { root ->
                    val params = root.layoutParams as WindowManager.LayoutParams
                    assertTrue(params.flags and WindowManager.LayoutParams.FLAG_SECURE != 0)
                    restored += root to params.flags
                    params.flags = params.flags and WindowManager.LayoutParams.FLAG_SECURE.inv()
                    root.context.getSystemService(WindowManager::class.java).updateViewLayout(root, params)
                }
            }
            instrumentation.uiAutomation.waitForIdle(100, 5_000)
            val (keyX, keyY) = point("q")
            val deadline = SystemClock.uptimeMillis() + 3_000
            var captured = false
            while (!captured && SystemClock.uptimeMillis() < deadline) {
                val bitmap = instrumentation.uiAutomation.takeScreenshot()
                if (bitmap != null) {
                    try {
                        // A PNG file alone is not screenshot evidence: reject black secure/renderer frames.
                        if (bitmap.getPixel(keyX.toInt(), keyY.toInt()) and 0x00ffffff != 0) {
                            val directory = File(app.externalCacheDir!!, "synthetic-captures").apply { mkdirs() }
                            val output = File(directory, "$name.png")
                            output.outputStream().use {
                                assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it))
                            }
                            // Gradle uninstalls the fixture after tests; retain only opt-in synthetic captures.
                            // executeShellCommand tokenizes arguments; quotes are not shell quoting here.
                            require(output.absolutePath.matches(Regex("[A-Za-z0-9_./-]+")))
                            shell("cp ${output.absolutePath} /data/local/tmp/utterleaf-$name.png")
                            assertEquals(output.length(), shell("stat -c %s /data/local/tmp/utterleaf-$name.png").toLong())
                            captured = true
                        }
                    } finally { bitmap.recycle() }
                }
                if (!captured) SystemClock.sleep(50)
            }
            assertTrue("Emulator did not produce a visible synthetic keyboard frame", captured)
        } finally {
            main {
                activity.window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
                restored.forEach { (root, flags) ->
                    val params = root.layoutParams as WindowManager.LayoutParams; params.flags = flags
                    root.context.getSystemService(WindowManager::class.java).updateViewLayout(root, params)
                }
            }
        }
    }
}
