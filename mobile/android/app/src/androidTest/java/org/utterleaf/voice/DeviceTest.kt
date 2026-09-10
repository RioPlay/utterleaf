package org.utterleaf.voice

import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.text.InputType
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.FixMethodOrder
import org.junit.runners.MethodSorters
import org.junit.runner.RunWith
import java.nio.ByteBuffer
import java.nio.ByteOrder

@RunWith(AndroidJUnit4::class)
@FixMethodOrder(MethodSorters.NAME_ASCENDING)
class DeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext
    @Test fun packagedPermissionsAndBackupsAreRestricted() {
        val info = app.packageManager.getPackageInfo(app.packageName, PackageManager.GET_PERMISSIONS)
        assertEquals(setOf("android.permission.RECORD_AUDIO"), info.requestedPermissions.orEmpty().toSet())
        assertEquals(0, app.applicationInfo.flags and ApplicationInfo.FLAG_ALLOW_BACKUP)
    }
    @Test fun passwordFieldsAreBlocked() {
        for (variant in listOf(InputType.TYPE_TEXT_VARIATION_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD, InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD))
            assertFalse(VoiceIme.safeField(InputType.TYPE_CLASS_TEXT or variant))
        assertFalse(VoiceIme.safeField(InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD))
        assertTrue(VoiceIme.safeField(InputType.TYPE_CLASS_TEXT))
    }
    @Test fun systemRecognizesAnAuxiliaryVoiceInputMethod() {
        val manager = app.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        val ime = manager.inputMethodList.single { it.serviceName == VoiceIme::class.java.name }
        assertEquals(1, ime.subtypeCount)
        val subtype = ime.getSubtypeAt(0)
        assertEquals("voice", subtype.mode)
        assertTrue(subtype.isAuxiliary)
        assertTrue(subtype.overridesImplicitlyEnabledSubtype())
        assertEquals("android.permission.BIND_INPUT_METHOD", ime.serviceInfo.permission)
    }
    @Test fun typingKeyboardIsSeparateAndProtected() {
        val manager = app.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        val ime = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }
        assertEquals("android.permission.BIND_INPUT_METHOD", ime.serviceInfo.permission)
        assertEquals("keyboard", ime.getSubtypeAt(0).mode)
        assertFalse(ime.getSubtypeAt(0).isAuxiliary)
        assertTrue(ime.getSubtypeAt(0).isAsciiCapable)
    }
    @Test fun keyboardSettingsPracticeStaysLocalAndProtected() {
        val activity = instrumentation.startActivitySync(android.content.Intent(app, KeyboardSettingsActivity::class.java)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
        var practice: android.widget.EditText? = null
        var oldKey: android.widget.Button? = null
        try {
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                assertTrue(activity.window.attributes.flags and android.view.WindowManager.LayoutParams.FLAG_SECURE != 0)
                // Only the instrumented synthetic capture may temporarily bypass protection.
                assertTrue(app.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0)
                fun descendants(view: android.view.View): List<android.view.View> = listOf(view) +
                    if (view is android.view.ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()
                val views = descendants(activity.findViewById(android.R.id.content))
                practice = views.filterIsInstance<android.widget.EditText>().single()
                assertFalse(practice!!.isSaveEnabled); assertFalse(practice!!.showSoftInputOnFocus)
                oldKey = views.filterIsInstance<android.widget.Button>().single { it.contentDescription == "a" }
                oldKey!!.performClick()
                assertEquals("a", practice!!.text.toString())
                activity.window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
            }
            instrumentation.runOnMainSync {
                val content = activity.findViewById<android.view.ViewGroup>(android.R.id.content)
                (content.getChildAt(0) as android.widget.ScrollView).fullScroll(android.view.View.FOCUS_DOWN)
            }
            instrumentation.waitForIdleSync()
            val screenshot = instrumentation.uiAutomation.takeScreenshot()
            assertNotNull(screenshot)
            screenshot!!.recycle()
            // UTP uninstalls the target after testing. Preserve only this synthetic UI
            // screenshot in shell-owned storage before that cleanup removes app files.
            val command = "screencap -p /data/local/tmp/utterleaf-keyboard-preview.png"
            android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(command)).use { it.readBytes() }
        } finally {
            instrumentation.runOnMainSync { activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE); activity.finish() }
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                oldKey?.performClick()
                practice?.let { assertEquals("Practice text survived leaving the screen", "", it.text.toString()) }
            }
        }
    }
    @Test fun typingKeysWorkWithoutSpeechAndResetSensitiveState() {
        instrumentation.runOnMainSync {
            val inserted = mutableListOf<String>()
            var deletes = 0
            var enters = 0
            val panel = TypingPanel(app, KeyboardOptions(), { inserted.add(it); true },
                { deletes++ }, { enters++ }, {}, { fail("Speech must be disabled") }, {}, {})
            fun buttons(view: android.view.View): List<android.widget.Button> = when (view) {
                is android.widget.Button -> listOf(view)
                is android.view.ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
                else -> emptyList()
            }
            fun key(label: String) = buttons(panel.view).single { it.contentDescription == label }
            panel.reset(false, false, "Done")
            assertFalse(key("Dictate").isEnabled)
            key("Shift off").performClick(); key("A").performClick(); key("a").performClick()
            key("Keyboard tools").performClick()
            key("Caps lock off").performClick(); key("B").performClick(); key("B").performClick()
            key("Shift off").performClick(); key("a").performClick(); key("B").performClick()
            key("Delete").performClick(); key("Done").performClick()
            assertEquals(listOf("A", "a", "B", "B", "a", "B"), inserted)
            assertEquals(1, deletes); assertEquals(1, enters)
            panel.reset(false, true, "Next") // A new numeric/password field cannot retain case state.
            key("1").performClick(); key("$").performClick()
            key("Switch letters and symbols").performClick()
            key("a").performClick()
            assertEquals(listOf("A", "a", "B", "B", "a", "B", "1", "$", "a"), inserted)
            assertTrue(buttons(panel.view).all { !it.contentDescription.isNullOrBlank() })
            assertTrue(key("Shift off").isFocusable)
        }
    }
    @Test fun keyboardToolsAndSymbolPagesRemainAccessible() {
        instrumentation.runOnMainSync {
            val inserted = mutableListOf<String>()
            val panel = TypingPanel(app, KeyboardOptions(), { inserted.add(it); true }, {}, {}, {}, {}, {}, {})
            fun buttons(view: android.view.View): List<android.widget.Button> = when (view) {
                is android.widget.Button -> listOf(view)
                is android.view.ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
                else -> emptyList()
            }
            fun keys() = buttons(panel.view).filter { it.visibility == android.view.View.VISIBLE }
            fun key(label: String) = keys().single { it.contentDescription == label }
            panel.reset(true, false, "Done")
            assertFalse(keys().any { it.contentDescription == "Move cursor left" })
            key("Keyboard tools").performClick()
            for (label in listOf("Caps lock off", "Move cursor left", "Move cursor right", "Keyboard settings", "Switch keyboard")) {
                assertTrue("Tool must be keyboard accessible: $label", key(label).isFocusable)
            }
            key("Keyboard tools").performClick()
            assertFalse(keys().any { it.contentDescription == "Move cursor left" })
            key("Switch letters and symbols").performClick()
            key("$").performClick()
            key("More symbols").performClick()
            key("[").performClick()
            key("More numbers and symbols").performClick()
            key("1").performClick()
            key("Switch letters and symbols").performClick()
            key("a").performClick()
            assertEquals(listOf("$", "[", "1", "a"), inserted)
            assertTrue(keys().all { !it.contentDescription.isNullOrBlank() })
        }
    }
    @Test fun keyboardGeometryFitsNarrowAndWideScreensWithConsistentStagger() {
        instrumentation.runOnMainSync {
            for (widthDp in listOf(320, 412)) for (light in listOf(false, true)) for (large in listOf(false, true)) {
                val description = "${widthDp}dp light=$light large=$large"
                val panel = TypingPanel(app, KeyboardOptions(light=light, large=large), { true }, {}, {}, {}, {}, {}, {})
                fun buttons(view: android.view.View): List<android.widget.Button> = when (view) {
                    is android.widget.Button -> listOf(view)
                    is android.view.ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
                    else -> emptyList()
                }
                fun keys() = buttons(panel.view).filter { it.visibility == android.view.View.VISIBLE }
                fun key(label: String) = keys().single { it.contentDescription == label }
                fun bounds(button: android.widget.Button) = android.graphics.Rect(0, 0, button.width, button.height).also {
                    panel.view.offsetDescendantRectToMyCoords(button, it)
                }
                fun layoutAndCheck() {
                    val width = Ui.dp(app, widthDp)
                    panel.view.measure(android.view.View.MeasureSpec.makeMeasureSpec(width, android.view.View.MeasureSpec.EXACTLY),
                        android.view.View.MeasureSpec.makeMeasureSpec(0, android.view.View.MeasureSpec.UNSPECIFIED))
                    panel.view.layout(0, 0, width, panel.view.measuredHeight)
                    val rectangles = keys().map { button ->
                        val rect = bounds(button)
                        assertTrue("Nonpositive key bounds: $description ${button.contentDescription}", rect.width() > 0 && rect.height() > 0)
                        assertTrue("Key outside panel: $description ${button.contentDescription} rect=$rect panel=${width}x${panel.view.height} " +
                            "local=${button.left},${button.top},${button.right},${button.bottom} scroll=${button.scrollX},${button.scrollY}",
                            rect.left >= 0 && rect.top >= 0 && rect.right <= width && rect.bottom <= panel.view.height)
                        assertTrue("Missing accessibility name: $description", !button.contentDescription.isNullOrBlank())
                        rect
                    }
                    for (index in rectangles.indices) for (other in 0 until index) {
                        assertFalse("Overlapping keys: $description", android.graphics.Rect.intersects(rectangles[index], rectangles[other]))
                    }
                }
                panel.reset(true, false, "Previous")
                layoutAndCheck()
                val letterWidths = "qwertyuiopasdfghjklzxcvbnm".map { bounds(key(it.toString())).width() }
                assertTrue("Letter widths vary by row: $description", letterWidths.maxOrNull()!! - letterWidths.minOrNull()!! <= 2)
                val q = bounds(key("q")); val w = bounds(key("w")); val a = bounds(key("a")); val z = bounds(key("z"))
                val pitch = w.exactCenterX() - q.exactCenterX()
                assertEquals("Home row must stagger half a cell: $description", pitch / 2, a.exactCenterX() - q.exactCenterX(), 3f)
                assertEquals("Bottom letters must follow the wide Shift key: $description", pitch * 1.5f, z.exactCenterX() - q.exactCenterX(), 3f)
                assertTrue("Space must remain broad: $description", bounds(key("Space")).width() >= q.width() * 4)
                key("Keyboard tools").performClick()
                layoutAndCheck()
                key("Switch letters and symbols").performClick()
                layoutAndCheck()
                val digitWidth = bounds(key("1")).width()
                assertTrue("Primary symbol width differs from digits: $description", kotlin.math.abs(bounds(key("@")).width() - digitWidth) <= 2)
                key("More symbols").performClick()
                layoutAndCheck()
                assertTrue("Secondary symbol rows use different widths: $description", kotlin.math.abs(bounds(key("£")).width() - bounds(key("~")).width()) <= 2)
            }
        }
    }
    @Test fun liveKeyboardEditsAndSurvivesFieldAndVisibilityChanges() {
        val automation = instrumentation.uiAutomation
        val previousFlags = automation.serviceInfo.flags
        val manager = app.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
        val keyboardId = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val wasEnabled = manager.enabledInputMethodList.any { it.id == keyboardId }
        val previousKeyboard = android.provider.Settings.Secure.getString(app.contentResolver,
            android.provider.Settings.Secure.DEFAULT_INPUT_METHOD)
        fun shell(value: String): String = android.os.ParcelFileDescriptor.AutoCloseInputStream(
            automation.executeShellCommand(value)).bufferedReader().use { it.readText() }
        fun awaitCondition(message: String, condition: () -> Boolean) {
            val deadline = android.os.SystemClock.elapsedRealtime() + 10000
            while (android.os.SystemClock.elapsedRealtime() < deadline) {
                if (condition()) return
                Thread.sleep(50)
            }
            val windows = automation.windows.joinToString { window ->
                "type=${window.type}, title=${window.title}, focused=${window.isFocused}, active=${window.isActive}"
            }
            fail("$message; windows: $windows")
        }
        fun <T> onMain(block: () -> T): T {
            val result = java.util.concurrent.atomic.AtomicReference<T>()
            instrumentation.runOnMainSync { result.set(block()) }
            return result.get()
        }
        fun findKey(description: String): android.view.accessibility.AccessibilityNodeInfo? {
            fun find(node: android.view.accessibility.AccessibilityNodeInfo): android.view.accessibility.AccessibilityNodeInfo? {
                if (node.contentDescription?.toString() == description && node.isClickable) return node
                for (index in 0 until node.childCount) {
                    val child = node.getChild(index) ?: continue
                    val found = find(child)
                    if (found != null) return found
                }
                return null
            }
            return automation.windows.asSequence()
                .filter { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD }
                .mapNotNull { it.root?.let(::find) }.firstOrNull()
        }
        fun findNativeKey(description: String): android.widget.Button? {
            fun find(view: android.view.View): android.widget.Button? {
                if (view is android.widget.Button && view.contentDescription?.toString() == description) return view
                if (view is android.view.ViewGroup) {
                    for (index in 0 until view.childCount) find(view.getChildAt(index))?.let { return it }
                }
                return null
            }
            return android.view.inspector.WindowInspector.getGlobalWindowViews().asSequence()
                .filter { (it.layoutParams as? android.view.WindowManager.LayoutParams)?.type ==
                    android.view.WindowManager.LayoutParams.TYPE_INPUT_METHOD }
                .mapNotNull(::find).firstOrNull()
        }
        fun press(description: String) {
            awaitCondition("Keyboard key unavailable: $description") { findKey(description)?.isEnabled == true }
            assertTrue("Could not press $description", findKey(description)!!.performAction(
                android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK))
            instrumentation.waitForIdleSync()
        }
        var activity: KeyboardTestActivity? = null
        var dismissedLauncherAnr = false
        try {
            automation.serviceInfo = automation.serviceInfo.apply {
                flags = flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            }
            shell("ime enable $keyboardId")
            shell("ime set $keyboardId")
            awaitCondition("Test keyboard was not selected") {
                android.provider.Settings.Secure.getString(app.contentResolver,
                    android.provider.Settings.Secure.DEFAULT_INPUT_METHOD) == keyboardId
            }
            val screen = instrumentation.startActivitySync(android.content.Intent(app, KeyboardTestActivity::class.java)
                .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)) as KeyboardTestActivity
            activity = screen
            instrumentation.waitForIdleSync()
            fun show(field: android.widget.EditText) {
                awaitCondition("Synthetic editor window did not acquire focus") {
                    val focused = onMain { screen.hasWindowFocus() }
                    if (!focused && !dismissedLauncherAnr) {
                        // API 35 CI occasionally opens the platform launcher's ANR dialog.
                        // Recover that named fixture failure once; never dismiss an app ANR.
                        val launcherDialog = automation.windows.firstOrNull { it.title?.toString() == "Quickstep isn't responding" }
                        val close = launcherDialog?.root?.findAccessibilityNodeInfosByText("Close app")?.firstOrNull { it.isClickable }
                        if (close?.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK) == true) {
                            dismissedLauncherAnr = true
                            println("Recovered the emulator Quickstep launcher dialog before editor validation")
                        }
                    }
                    focused
                }
                onMain { field.requestFocus() }
                awaitCondition("Synthetic ${if (field === screen.editor) "text" else "password"} field did not acquire its input connection") {
                    onMain { manager.isActive(field) }
                }
                onMain { manager.showSoftInput(field, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT) }
                awaitCondition("Typing keyboard did not appear") { findKey("a") != null }
            }
            show(screen.editor)
            press("a"); press("b"); press("c")
            awaitCondition("InputConnection did not commit letters") { onMain { screen.editor.text.toString() == "abc" } }
            press("Keyboard tools")
            press("Move cursor left")
            awaitCondition("InputConnection did not move cursor") { onMain { screen.editor.selectionStart == 2 } }
            press("Delete")
            awaitCondition("InputConnection did not delete before cursor") { onMain { screen.editor.text.toString() == "ac" } }
            press("Move cursor right"); press("d")
            awaitCondition("Cursor-right edit was incorrect") { onMain { screen.editor.text.toString() == "acd" } }
            press("Move cursor left"); press("Delete to right")
            awaitCondition("Forward delete did not remove text after the cursor") { onMain { screen.editor.text.toString() == "ac" } }
            press("d")
            press("Done")
            awaitCondition("Editor action did not reach editor") { onMain { screen.lastEditorAction == android.view.inputmethod.EditorInfo.IME_ACTION_DONE } }
            press("Keyboard tools")

            // Only this debug instrumentation run may expose this synthetic IME
            // window for a screenshot. Production FLAG_SECURE remains unchanged.
            if (android.os.Build.VERSION.SDK_INT >= 29) {
                val imeRoot = onMain {
                    android.view.inspector.WindowInspector.getGlobalWindowViews().single {
                        (it.layoutParams as? android.view.WindowManager.LayoutParams)?.type == android.view.WindowManager.LayoutParams.TYPE_INPUT_METHOD
                    }
                }
                val originalFlags = onMain { (imeRoot.layoutParams as android.view.WindowManager.LayoutParams).flags }
                assertTrue("Production IME window must be secure", originalFlags and android.view.WindowManager.LayoutParams.FLAG_SECURE != 0)
                fun flags(value: Int) = onMain {
                    val params = imeRoot.layoutParams as android.view.WindowManager.LayoutParams
                    params.flags = value
                    (imeRoot.context.getSystemService(android.content.Context.WINDOW_SERVICE) as android.view.WindowManager).updateViewLayout(imeRoot, params)
                }
                try {
                    flags(originalFlags and android.view.WindowManager.LayoutParams.FLAG_SECURE.inv())
                    instrumentation.waitForIdleSync()
                    shell("screencap -p /data/local/tmp/utterleaf-keyboard-live.png")
                    var gestureStart = 0L
                    fun touch(action: Int, x: Float, y: Float) {
                        val now = android.os.SystemClock.uptimeMillis()
                        if (action == android.view.MotionEvent.ACTION_DOWN) gestureStart = now
                        val event = android.view.MotionEvent.obtain(gestureStart, now, action, x, y, 0)
                        event.source = android.view.InputDevice.SOURCE_TOUCHSCREEN
                        try { assertTrue("Touch injection failed", automation.injectInputEvent(event, true)) }
                        finally { event.recycle() }
                        instrumentation.waitForIdleSync()
                    }
                    fun center(label: String): Pair<Float, Float> = onMain {
                        val key = findNativeKey(label) ?: error("Missing touch key: $label")
                        val position = IntArray(2); key.getLocationOnScreen(position)
                        Pair(position[0] + key.width / 2f, position[1] + key.height / 2f)
                    }
                    val space = center("Space")
                    val distance = Ui.dp(app, 32).toFloat()
                    for (direction in listOf(-1, 1)) {
                        touch(android.view.MotionEvent.ACTION_DOWN, space.first, space.second)
                        touch(android.view.MotionEvent.ACTION_MOVE, space.first + direction * distance, space.second)
                        touch(android.view.MotionEvent.ACTION_UP, space.first + direction * distance, space.second)
                        awaitCondition("Space swipe did not move the real editor cursor") {
                            onMain { screen.editor.selectionStart == if (direction < 0) 1 else 3 }
                        }
                        assertEquals("Space swipe inserted text", "acd", onMain { screen.editor.text.toString() })
                    }
                    val letter = center("e")
                    val backspace = center("Delete")
                    touch(android.view.MotionEvent.ACTION_DOWN, backspace.first, backspace.second)
                    Thread.sleep(android.view.ViewConfiguration.getLongPressTimeout().toLong() + 320)
                    touch(android.view.MotionEvent.ACTION_UP, backspace.first, backspace.second)
                    awaitCondition("Held Backspace did not repeatedly delete in the editor") { onMain { screen.editor.text.isEmpty() } }
                    onMain { screen.editor.setText("acd"); screen.editor.setSelection(3) }
                    Thread.sleep(160)
                    assertEquals("Delete continued after release", "acd", onMain { screen.editor.text.toString() })
                    val shiftPosition = center("Shift off")
                    fun chord(action: Int, dx: Float = 0f, two: Boolean = true) {
                        val count = if (two) 2 else 1
                        val props = Array(count) { index -> android.view.MotionEvent.PointerProperties().apply {
                            id = index; toolType = android.view.MotionEvent.TOOL_TYPE_FINGER
                        } }
                        val coords = Array(count) { index -> android.view.MotionEvent.PointerCoords().apply {
                            x = if (index == 0) shiftPosition.first else space.first + dx
                            y = if (index == 0) shiftPosition.second else space.second
                            pressure = 1f; size = 1f
                        } }
                        val now = android.os.SystemClock.uptimeMillis()
                        if (action == android.view.MotionEvent.ACTION_DOWN) gestureStart = now
                        val event = android.view.MotionEvent.obtain(gestureStart, now, action, count, props, coords,
                            0, 0, 1f, 1f, 0, 0, android.view.InputDevice.SOURCE_TOUCHSCREEN, 0)
                        try { assertTrue(automation.injectInputEvent(event, true)) } finally { event.recycle() }
                        instrumentation.waitForIdleSync()
                    }
                    chord(android.view.MotionEvent.ACTION_DOWN, two = false)
                    chord(android.view.MotionEvent.ACTION_POINTER_DOWN or (1 shl android.view.MotionEvent.ACTION_POINTER_INDEX_SHIFT))
                    chord(android.view.MotionEvent.ACTION_MOVE, -distance)
                    chord(android.view.MotionEvent.ACTION_POINTER_UP or (1 shl android.view.MotionEvent.ACTION_POINTER_INDEX_SHIFT), -distance)
                    chord(android.view.MotionEvent.ACTION_UP, two = false)
                    awaitCondition("Shift-space did not select text in the real editor") { onMain {
                        minOf(screen.editor.selectionStart, screen.editor.selectionEnd) == 1 &&
                            maxOf(screen.editor.selectionStart, screen.editor.selectionEnd) == 3
                    } }
                    press("x")
                    awaitCondition("Typing did not replace gesture selection") { onMain { screen.editor.text.toString() == "ax" } }
                    onMain { screen.editor.setText("acd"); screen.editor.setSelection(3) }
                    instrumentation.waitForIdleSync()
                    val imeHeight = onMain { imeRoot.height }
                    touch(android.view.MotionEvent.ACTION_DOWN, letter.first, letter.second)
                    Thread.sleep(android.view.ViewConfiguration.getLongPressTimeout().toLong() + 100)
                    instrumentation.waitForIdleSync()
                    val choice = onMain {
                        fun find(view: android.view.View): AlternateStrip? {
                            if (view is AlternateStrip) return view
                            if (view is android.view.ViewGroup) for (i in 0 until view.childCount) find(view.getChildAt(i))?.let { return it }
                            return null
                        }
                        val strip = find(imeRoot) ?: error("Live hold strip did not appear")
                        assertEquals("Hold resized the IME", imeHeight, imeRoot.height)
                        val position = IntArray(2); strip.getLocationOnScreen(position)
                        Pair(position[0] + strip.cells[0].centerX(), position[1] + strip.cells[0].centerY())
                    }
                    touch(android.view.MotionEvent.ACTION_MOVE, choice.first, choice.second)
                    shell("screencap -p /data/local/tmp/utterleaf-keyboard-hold.png")
                    touch(android.view.MotionEvent.ACTION_UP, choice.first, choice.second)
                    awaitCondition("Hold-slide-release did not insert into the editor") {
                        onMain { screen.editor.text.toString() == "acdé" }
                    }
                    press("Delete")
                    press("Keyboard tools")
                    press("Accents and alternate characters")
                    press("e")
                    shell("screencap -p /data/local/tmp/utterleaf-keyboard-accents.png")
                    press("é")
                    awaitCondition("Alternate character did not reach the editor") {
                        onMain { screen.editor.text.toString() == "acdé" }
                    }
                    press("Delete")
                    press("Keyboard tools")

                    press("Keyboard tools")
                    press("Accents and alternate characters")
                    press("e")
                    val detachedAlternate = onMain {
                        findNativeKey("é") ?: error("Alternate character button unavailable")
                    }
                    show(screen.password)
                    onMain { detachedAlternate.performClick() }
                    instrumentation.waitForIdleSync()
                    assertEquals("Detached alternate button changed the old editor", "acd",
                        onMain { screen.editor.text.toString() })
                    assertEquals("Detached alternate button changed the new field", "",
                        onMain { screen.password.text.toString() })
                    show(screen.editor)
                } finally {
                    flags(originalFlags)
                }
            }

            // Enter the real voice panel, then change fields. No microphone capture is started.
            press("Dictate")
            awaitCondition("Voice panel did not appear") {
                automation.windows.filter { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD }
                    .any { it.root?.findAccessibilityNodeInfosByText("Speak")?.isNotEmpty() == true }
            }
            show(screen.password)
            assertFalse("Password field allowed dictation", findKey("Dictate")!!.isEnabled)
            press("x")
            awaitCondition("Password typing did not work") { onMain { screen.password.text.toString() == "x" } }
            onMain { manager.hideSoftInputFromWindow(screen.password.windowToken, 0) }
            awaitCondition("Keyboard did not hide") { findKey("a") == null }
            show(screen.password)
            assertFalse("Reopened password field allowed dictation", findKey("Dictate")!!.isEnabled)
            press("y")
            awaitCondition("Keyboard failed after reopen") { onMain { screen.password.text.toString() == "xy" } }
            assertEquals("Password input changed the previous field", "acd", onMain { screen.editor.text.toString() })
        } finally {
            activity?.let { screen -> onMain { screen.finish() } }
            try {
                if (!previousKeyboard.isNullOrBlank()) shell("ime set $previousKeyboard")
            } finally {
                if (!wasEnabled) shell("ime disable $keyboardId")
                automation.serviceInfo = automation.serviceInfo.apply { flags = previousFlags }
            }
        }
    }
    @Test fun deniedPermissionCannotStartCapture() {
        assertEquals(PackageManager.PERMISSION_DENIED, app.checkSelfPermission("android.permission.RECORD_AUDIO"))
        instrumentation.runOnMainSync {
            val errors = mutableListOf<String>()
            val session = VoiceSession(app, { fail("Unexpected capture state") }, { fail("Unexpected transcript") }, { errors.add(it) })
            session.start()
            assertTrue(errors.single().contains("permission"))
            session.cancel()
        }
    }
    @Test fun realPanelRejectsLateSpeechAndInsertsOnlyOnce() {
        instrumentation.runOnMainSync {
            val callbacks = mutableListOf<(String) -> Unit>()
            val inserted = mutableListOf<String>()
            var cancellations = 0
            val panel = VoicePanel(app, { inserted.add(it); true }, {}, { _, result, _ ->
                callbacks.add(result)
                object : CaptureSession {
                    override fun start() { }
                    override fun stop() { }
                    override fun cancel() { cancellations++ }
                }
            })
            fun buttons(view: android.view.View): List<android.widget.Button> = when(view) {
                is android.widget.Button -> listOf(view)
                is android.view.ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
                else -> emptyList()
            }
            val speak = buttons(panel.view).first { it.text == "Speak" }
            val insert = speak // The same primary control changes action in place.
            panel.view.measure(android.view.View.MeasureSpec.makeMeasureSpec(Ui.dp(app, 360), android.view.View.MeasureSpec.EXACTLY),
                android.view.View.MeasureSpec.makeMeasureSpec(0, android.view.View.MeasureSpec.UNSPECIFIED))
            assertTrue("Idle voice panel takes too much space", panel.view.measuredHeight <= Ui.dp(app, 300))
            speak.performClick()
            panel.clear() // Same path used by input-field changes and hiding the IME.
            callbacks[0]("stale speech")
            assertEquals("Speak", insert.text.toString())
            assertEquals(1, cancellations)
            speak.performClick()
            callbacks[1]("fresh speech")
            assertTrue(insert.isEnabled)
            insert.performClick()
            insert.performClick()
            assertEquals(listOf("fresh speech"), inserted)
            assertFalse(insert.isEnabled)
            panel.clear()
        }
    }
    @Test fun verifiedModelTranscribesRealSpeechWithoutNetwork() {
        val testAssets = instrumentation.context.assets
        testAssets.open("ggml-tiny.en.bin").use { ModelStore.install(it, app.noBackupFilesDir) }
        assertTrue(ModelStore.ready(app.noBackupFilesDir))
        val wav = testAssets.open("jfk.wav").use { it.readBytes() }
        val buffer = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals("RIFF", String(wav, 0, 4))
        var offset = 12
        var audio = FloatArray(0)
        while (offset + 8 <= wav.size) {
            val type = String(wav, offset, 4)
            val size = buffer.getInt(offset + 4)
            if (type == "fmt ") { assertEquals(1, buffer.getShort(offset + 8).toInt()); assertEquals(16000, buffer.getInt(offset + 12)) }
            if (type == "data") {
                audio = FloatArray(size / 2) { buffer.getShort(offset + 8 + it * 2) / 32768f }; break
            }
            offset += 8 + size + (size % 2)
        }
        assertTrue(audio.size > 16000)
        NativeEngine.reset()
        val result = NativeEngine.decode(ModelStore.file(app.noBackupFilesDir).absolutePath, audio)
        assertNotNull(result)
        val text = result!!.toString(Charsets.UTF_8).lowercase()
        assertTrue("Known speech was not recognized", text.contains("country"))
        NativeEngine.reset(); NativeEngine.cancel()
        assertNull(NativeEngine.decode(ModelStore.file(app.noBackupFilesDir).absolutePath, audio))
        audio.fill(0f); result.fill(0)
    }
    @Test fun zCaptureStopsAndReleasesItsLeaseOnCancel() {
        // Last test: granting a runtime permission persists for this emulator install.
        instrumentation.context.assets.open("ggml-tiny.en.bin").use { ModelStore.install(it, app.noBackupFilesDir) }
        instrumentation.uiAutomation.grantRuntimePermission(app.packageName, "android.permission.RECORD_AUDIO")
        val activity = instrumentation.startActivitySync(android.content.Intent(app, SetupActivity::class.java)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
        val listening = java.util.concurrent.CountDownLatch(1)
        val failure = java.util.concurrent.atomic.AtomicReference<String>()
        lateinit var session: VoiceSession
        try {
            instrumentation.runOnMainSync {
                session = VoiceSession(app, { if (it.startsWith("Listening")) listening.countDown() },
                    { failure.set("Cancelled capture produced text") }, { failure.set(it); listening.countDown() })
                session.start()
            }
            assertTrue("Capture did not start", listening.await(10, java.util.concurrent.TimeUnit.SECONDS))
            assertNull(failure.get())
        } finally {
            instrumentation.runOnMainSync { session.cancel(); activity.finish() }
        }
        val deadline = android.os.SystemClock.elapsedRealtime() + 5000
        var released = false
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (WorkLease.acquire()) { WorkLease.release(); released = true; break }
            Thread.sleep(20)
        }
        assertTrue("Capture did not release its lease", released)
        assertNull(failure.get())
    }
}
