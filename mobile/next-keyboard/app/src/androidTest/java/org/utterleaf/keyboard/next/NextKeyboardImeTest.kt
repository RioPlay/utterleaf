package org.utterleaf.keyboard.next

import android.app.Activity
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.os.PowerManager
import android.graphics.Rect
import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.provider.Settings
import android.app.KeyguardManager
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.view.inspector.WindowInspector
import android.widget.EditText
import android.widget.CheckBox
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.SdkSuppress
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.Before
import org.junit.runner.RunWith
import org.utterleaf.keyboard.next.core.Outcome
import org.utterleaf.keyboard.next.settings.PrivacyPreferences
import org.utterleaf.keyboard.next.settings.TypingPreferences
import org.utterleaf.keyboard.next.settings.TypingOptions
import org.utterleaf.keyboard.next.ui.KeyboardSurface
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Real framework-created IME, screen-coordinate touches, and disposable synthetic text. */
@RunWith(AndroidJUnit4::class)
@SdkSuppress(minSdkVersion = 30)
class NextKeyboardImeTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext
    private val touchTrace = ArrayDeque<String>()
    private var tracedSurface: KeyboardSurface? = null
    private fun isInteractive() = app.getSystemService(PowerManager::class.java)?.isInteractive == true
    private fun isLocked() = app.getSystemService(KeyguardManager::class.java)?.isKeyguardLocked != false
    @Suppress("DEPRECATION")
    private fun focusedAccessibilityWindowPackage(): String {
        return runCatching {
            val node = instrumentation.uiAutomation.rootInActiveWindow
            try { node?.packageName?.toString() ?: "none" } finally { node?.recycle() }
        }.getOrElse { "unavailable:${it::class.java.simpleName}" }
    }
    private fun focusFailureDetails(activity: Activity?) = buildString {
        append("; interactive=").append(isInteractive())
        append(", keyguardLocked=").append(isLocked())
        append(", activityDestroyed=").append(activity?.isDestroyed)
        append(", activityWindowFocus=").append(activity?.hasWindowFocus())
        append(", accessibilityFocusedWindowPackage=").append(focusedAccessibilityWindowPackage())
    }
    @Before
    fun wakeAndUnlockForImeTests() {
        shell("input keyevent KEYCODE_WAKEUP")
        shell("wm dismiss-keyguard")
        await("Device not interactive or keyguard still locked", details = { focusFailureDetails(null) }) {
            isInteractive() && !isLocked()
        }
    }
    private fun trace(value: String) {
        if (touchTrace.size == 64) touchTrace.removeFirst()
        touchTrace.addLast(value)
    }
    private fun syntheticDetails(activity: CoreTestActivity): String =
        "; synthetic actual=${activity.first.text}, ready=${(keyboard()?.context as? NextKeyboardIme)?.isReadyForInput}, touches=$touchTrace"
    private fun shell(command: String) = ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command)
    ).bufferedReader().use { it.readText().trim() }
    private fun <T> main(block: () -> T): T {
        var result: Result<T>? = null
        instrumentation.runOnMainSync { result = runCatching(block) }
        return result!!.getOrThrow()
    }
    private fun await(label: String, details: () -> String = { "" }, block: () -> Boolean) {
        val deadline = SystemClock.uptimeMillis() + 10_000
        while (SystemClock.uptimeMillis() < deadline) {
            instrumentation.waitForIdleSync()
            if (main(block)) return
            SystemClock.sleep(20)
        }
        fail(label + main(details))
    }
    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()
    private fun keyboard(): KeyboardSurface? = WindowInspector.getGlobalWindowViews()
        .flatMap(::descendants).filterIsInstance<KeyboardSurface>()
        .singleOrNull { it.isShown && it.isLaidOut && !it.isLayoutRequested && it.width > 0 }

    private fun show(activity: CoreTestActivity, field: EditText) {
        await("Fixture must own a focused window before requesting IME", details = { focusFailureDetails(activity) }) { activity.hasWindowFocus() }
        main {
            field.requestFocus()
            field.setSelection(field.length())
            activity.getSystemService(InputMethodManager::class.java).showSoftInput(field, 0)
        }
        await("Framework keyboard did not become visible", details = {
            val surfaces = WindowInspector.getGlobalWindowViews().flatMap(::descendants).filterIsInstance<KeyboardSurface>()
            "; focused=${field.hasFocus()}, window=${activity.hasWindowFocus()}, animating=${activity.imeAnimating}, insets=${activity.window.decorView.rootWindowInsets?.isVisible(WindowInsets.Type.ime())}, expectedField=${field.id}, surfaces=" + surfaces.map { view ->
                val ime = view.context as NextKeyboardIme
                "shown=${view.isShown},layout=${view.isLaidOut}/${view.isLayoutRequested},size=${view.width}x${view.height},ready=${ime.isReadyForInput},field=${ime.currentInputEditorInfo?.fieldId}"
            }
        }) {
            val ime = keyboard()?.context as? NextKeyboardIme
            field.hasFocus() && !activity.imeAnimating &&
                activity.window.decorView.rootWindowInsets?.isVisible(WindowInsets.Type.ime()) == true &&
                ime?.isReadyForInput == true && ime.currentInputEditorInfo?.fieldId == field.id
        }
        awaitKeyboardFrame()
    }

    /** Wait for a submitted frame before resolving coordinates or creating a DOWN timestamp. */
    private fun awaitKeyboardFrame() {
        val deadline = SystemClock.uptimeMillis() + 10_000
        while (SystemClock.uptimeMillis() < deadline) {
            val submitted = CountDownLatch(1)
            val callback = Runnable { submitted.countDown() }
            val (view, observer, size) = main {
                val surface = keyboard() ?: error("No visible IME for frame synchronization")
                check(surface.isHardwareAccelerated) { "Frame synchronization requires hardware rendering" }
                val observer = surface.viewTreeObserver
                observer.registerFrameCommitCallback(callback)
                surface.postInvalidateOnAnimation()
                Triple(surface, observer, surface.width to surface.height)
            }
            val committed = try { submitted.await(2, TimeUnit.SECONDS) } finally {
                main { if (observer.isAlive) observer.unregisterFrameCommitCallback(callback) }
            }
            if (committed && main {
                keyboard() === view && view.width == size.first && view.height == size.second &&
                    (view.context as NextKeyboardIme).isReadyForInput
            }) return
            // Retrying readiness is safe: no gesture has been injected yet.
        }
        fail("IME did not submit a stable frame before input")
    }

    private fun point(label: String): Pair<Float, Float> = main {
        val view = keyboard() ?: error("No real IME view")
        if (tracedSurface !== view) {
            tracedSurface?.setOnTouchListener(null)
            tracedSurface = view
            // Test-only bounded diagnostics. Return false to leave all real touch handling intact.
            view.setOnTouchListener { _, event ->
                trace("received=${event.actionMasked}@${event.x},${event.y} age=${SystemClock.uptimeMillis() - event.downTime} popup=${view.hasAlternatePopup}")
                false
            }
        }
        val key = view.alternateBounds(label) ?: view.keyBounds(label) ?: error("Missing key $label")
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
        trace("aim=$label@$x,$y")
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
            main { tracedSurface?.setOnTouchListener(null); tracedSurface = null }
            try {
                activity?.let { fixture ->
                    main { fixture.finish() }
                    await("Fixture activity did not finish teardown") { fixture.isDestroyed }
                }
            } finally {
                try {
                    if (oldIme.isNotBlank() && oldIme != "null") shell("ime set $oldIme")
                    // If this IME was already selected, it may legitimately serve another host.
                    if (oldIme != component) await("Test IME window survived restoration") {
                        WindowInspector.getGlobalWindowViews().flatMap(::descendants)
                            .none { it is KeyboardSurface && it.isShown }
                    }
                } finally {
                    if (!enabled) shell("ime disable $component")
                    if (oldHardware == "null") shell("settings delete secure show_ime_with_hard_keyboard")
                    else shell("settings put secure show_ime_with_hard_keyboard $oldHardware")
                }
            }
        }
    }

    @Test fun actualTypingSymbolsDeleteAndTwoThumbs() = withIme { activity ->
        show(activity, activity.first)
        type("hello world")
        await("Typed text missing", details = { syntheticDetails(activity) }) { activity.first.text.toString() == "hello world" }
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

    @Test fun longOrdinaryFieldBackspaceKeepsWholeGrapheme() = withIme { activity ->
        val prefix = "a".repeat(200)
        main { activity.first.setText(prefix + "e\u0301") }
        show(activity, activity.first)
        touch("⌫")
        await("Long-field Backspace must remove the whole final grapheme", details = { syntheticDetails(activity) }) {
            activity.first.text.toString() == prefix
        }
        type("z")
        await("Typing after long-field deletion failed") { activity.first.text.toString() == prefix + "z" }
    }

    @Test fun incognitoPersistenceAndSyntheticScreenshots() = withIme { activity ->
        val preferences = main { PrivacyPreferences.get(app) }
        await("Privacy preferences did not initialize") { preferences.state.ready && !preferences.state.saving }
        val original = main { preferences.state.incognito }
        try {
            main { preferences.setIncognito(false) }
            await("Off preference did not save") { !preferences.state.saving && !preferences.state.incognito }
            show(activity, activity.first); type("hello from utterleaf")
            await("Synthetic capture must contain the complete touch-typed text", details = { syntheticDetails(activity) }) { activity.first.text.toString() == "hello from utterleaf" }
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

    @Test fun numberRowApplyResetAndBothAccentPathsUseRealTouches() = withIme { activity ->
        val prefs = main { TypingPreferences.get(app) }
        await("Typing preferences did not initialize") { prefs.state.ready && !prefs.state.saving }
        val original = main { prefs.state.saved }
        try {
            main { prefs.edit(TypingOptions()); prefs.apply() }
            await("Defaults did not save") { !prefs.state.saving && prefs.state.saved == TypingOptions() }
            show(activity, activity.first); type("cafe")
            val oldHeight = main { keyboard()!!.height }
            main { prefs.edit(TypingOptions(numberRow = true)) }
            assertEquals(oldHeight, main { keyboard()!!.height })
            main { prefs.apply() }
            await("Applied number row must resize live IME") {
                !prefs.state.saving && !activity.imeAnimating && keyboard()?.keyBounds("1") != null && keyboard()!!.height > oldHeight
            }
            awaitKeyboardFrame()
            type("123")
            await("Number row must commit digits", details = { syntheticDetails(activity) }) { activity.first.text.toString() == "cafe123" }
            capture(activity, "next-core-number-row")

            touch("⇧")
            main {
                val surface = keyboard()!!
                val accents = descendants(surface.rootView).filterIsInstance<android.widget.Button>()
                    .single { it.text.toString() == app.getString(R.string.accents) }
                assertTrue(accents.performClick())
            }
            touch("e")
            await("Tap route must expose uppercase alternatives") { keyboard()?.alternateBounds("É") != null }
            touch("É")
            await("Tap accent must commit once") { activity.first.text.toString() == "cafe123É" }

            val (x, y) = point("a")
            val down = SystemClock.uptimeMillis()
            fun inject(action: Int, at: Pair<Float, Float>) {
                val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, at.first, at.second, 0)
                event.source = InputDevice.SOURCE_TOUCHSCREEN
                try { assertTrue(instrumentation.uiAutomation.injectInputEvent(event, true)) } finally { event.recycle() }
            }
            inject(MotionEvent.ACTION_DOWN, x to y)
            await("Hold must open accent picker") { keyboard()?.hasAlternatePopup == true }
            capture(activity, "next-core-accents")
            val accented = point("á")
            inject(MotionEvent.ACTION_MOVE, accented); inject(MotionEvent.ACTION_UP, accented)
            await("Hold-slide-release must commit only the selected accent") { activity.first.text.toString() == "cafe123Éá" }

            main { prefs.reset() }
            await("Reset must remove number row in same editor") {
                !prefs.state.saving && !activity.imeAnimating && keyboard()?.keyBounds("1") == null && keyboard()?.height == oldHeight
            }
            awaitKeyboardFrame()
            type("z")
            await("Typing after reset failed") { activity.first.text.toString() == "cafe123Éáz" }
        } finally {
            main { prefs.edit(original); prefs.apply() }
            await("Restore typing preferences") { !prefs.state.saving }
        }
    }

    @Test fun settingsControlsApplyDiscardAndResetWithoutExitingIncognito() {
        val prefs = main { TypingPreferences.get(app) }
        val privacy = main { PrivacyPreferences.get(app) }
        await("Preferences not ready") { prefs.state.ready && privacy.state.ready && !prefs.state.saving && !privacy.state.saving }
        val original = main { prefs.state.saved }
        val originalPrivacy = main { privacy.state.incognito }
        var setup: SetupActivity? = null
        try {
            main { prefs.reset(); privacy.setIncognito(true) }
            await("Seed preferences") { !prefs.state.saving && !privacy.state.saving }
            val screen = instrumentation.startActivitySync(Intent(app, SetupActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as SetupActivity
            setup = screen
            await("Settings activity did not gain focus", details = { focusFailureDetails(screen) }) { screen.hasWindowFocus() }
            main {
                screen.findViewById<CheckBox>(R.id.typing_number_row).performClick()
                assertTrue(prefs.state.draft.numberRow); assertFalse(prefs.state.saved.numberRow)
                screen.findViewById<View>(R.id.typing_discard).performClick()
                assertFalse(prefs.state.draft.numberRow)
                screen.findViewById<CheckBox>(R.id.typing_number_row).performClick()
                screen.findViewById<View>(R.id.typing_apply).performClick()
            }
            await("Apply control did not persist number row") { !prefs.state.saving && prefs.state.saved.numberRow }
            main { screen.findViewById<View>(R.id.typing_reset).performClick() }
            await("Reset control did not restore defaults") { !prefs.state.saving && prefs.state.saved == TypingOptions() }
            main {
                assertTrue(privacy.state.incognito)
                screen.findViewById<CheckBox>(R.id.typing_number_row).performClick()
                screen.finish()
            }
            await("Leaving settings must discard unapplied draft") { prefs.state.draft == prefs.state.saved }
        } finally {
            main { setup?.finish(); prefs.edit(original); prefs.apply(); privacy.setIncognito(originalPrivacy) }
            await("Restore settings") { !prefs.state.saving && !privacy.state.saving }
            await("Settings activity did not finish teardown") { setup?.isDestroyed != false }
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
