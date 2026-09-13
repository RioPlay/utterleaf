package org.utterleaf.voice

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.Intent
import android.graphics.Rect
import android.provider.Settings
import android.view.View
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream

/** Geometry contracts for the original keyboard's independent daily and power layers. */
@RunWith(AndroidJUnit4::class)
class KeyboardGeometryTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun <T> main(block: () -> T): T {
        val result = java.util.concurrent.atomic.AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is android.view.ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    private fun key(panel: TypingPanel, label: String): android.widget.Button =
        descendants(panel.view).filterIsInstance<android.widget.Button>().single { it.contentDescription == label }

    private fun layout(panel: TypingPanel, widthDp: Int): Int {
        val width = Ui.dp(app, widthDp)
        panel.view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
        panel.view.layout(0, 0, width, panel.view.measuredHeight)
        return panel.view.height
    }

    private fun bounds(panel: TypingPanel, label: String): Rect = Rect(0, 0, key(panel, label).width, key(panel, label).height).also {
        panel.view.offsetDescendantRectToMyCoords(key(panel, label), it)
    }

    @Test fun numberRowIsIndependentAndFailureDoesNotMoveDirectPanelKeys() = main {
        fun panel(options: KeyboardOptions, accepted: Boolean = true) = TypingPanel(app, options,
            { accepted }, {}, {}, {}, {}, {}, {})
        val ordinary = panel(KeyboardOptions())
        ordinary.reset(false, false, "Enter")
        val ordinaryHeight = layout(ordinary, 320)
            val ordinaryKeys = listOf("Keyboard tools", "Edit actions", "Emoji", "Dictate",
            "Switch letters and symbols", "Space", "Enter")
        ordinaryKeys.forEach { label ->
            val rect = bounds(ordinary, label)
            assertTrue("$label is clipped", rect.left >= 0 && rect.right <= ordinary.view.width && rect.top >= 0 && rect.bottom <= ordinaryHeight)
        }

        val rejected = panel(KeyboardOptions(), accepted = false)
        rejected.reset(false, false, "Enter")
        layout(rejected, 320)
        val before = listOf("Keyboard tools", "Dictate", "Space", "Enter").associateWith { bounds(rejected, it) }
        val beforeHeight = rejected.view.height
        key(rejected, "q").performClick()
        assertEquals("Rejected input must not add a row", beforeHeight, layout(rejected, 320))
        before.forEach { (label, rect) -> assertEquals("Rejected input moved $label", rect, bounds(rejected, label)) }
        assertFalse(descendants(rejected.view).filterIsInstance<android.widget.TextView>()
            .any { it.text == "Key unavailable" && it.visibility == View.VISIBLE })

        val terminalOnly = panel(KeyboardOptions(terminal = true))
        terminalOnly.reset(false, false, "Enter")
        layout(terminalOnly, 320)
        assertNotNull(key(terminalOnly, "Escape"))
        assertFalse("Terminal controls must not imply a number row", descendants(terminalOnly.view)
            .filterIsInstance<android.widget.Button>().any { it.contentDescription == "1" })

        val withNumbers = panel(KeyboardOptions(terminal = true, numberRow = true))
        withNumbers.reset(false, false, "Enter")
        layout(withNumbers, 320)
        assertNotNull(key(withNumbers, "1"))

        for (options in listOf(KeyboardOptions(large = true, light = true), KeyboardOptions(large = true, light = false))) {
            val large = panel(options)
            large.reset(false, false, "Enter")
            val height = layout(large, 320)
            listOf("Keyboard tools", "Dictate", "Space", "Enter").forEach { label ->
                val rect = bounds(large, label)
                assertTrue("$label is clipped with $options", rect.left >= 0 && rect.right <= large.view.width && rect.top >= 0 && rect.bottom <= height)
            }
        }
    }

    private fun shell(command: String) = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command)).bufferedReader().use { it.readText() }

    @Test fun subsequentActionsAndResetCancelEarlierFailureFeedback() = main {
        val panel = TypingPanel(app, KeyboardOptions(terminal = true),
            { true }, {}, {}, {}, {}, {}, {}, terminalKey = { _, _, _, _ -> true }, editorAction = { true })
        panel.reset(false, false, "Enter")
        layout(panel, 320)
        val owner = TypingPanel::class.java.getDeclaredField("unavailableToast").apply { isAccessible = true }
        fun verify(action: () -> Unit) {
            var cancelled = false
            val previous = object : android.widget.Toast(app) { override fun cancel() { cancelled = true } }
            owner.set(panel, previous)
            action()
            assertTrue("A later action left stale failure feedback", cancelled)
            assertTrue(owner.get(panel) == null)
        }
        verify { key(panel, "q").performClick() }
        verify { key(panel, "Tab").performClick() }
        verify { key(panel, "Left arrow").performClick() }
        key(panel, "Edit actions").performClick()
        verify { key(panel, "Copy").performClick() }
        verify { panel.reset(false, false, "Enter") }
    }

    private fun await(message: String, condition: () -> Boolean) {
        val deadline = android.os.SystemClock.elapsedRealtime() + 10_000
        while (android.os.SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return
            Thread.sleep(50)
        }
        throw AssertionError(message)
    }

    private fun node(label: String): AccessibilityNodeInfo? {
        fun find(current: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (current.contentDescription?.toString() == label && current.isClickable) return current
            for (index in 0 until current.childCount) current.getChild(index)?.let(::find)?.let { return it }
            return null
        }
        return instrumentation.uiAutomation.windows.asSequence().filter { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
            .mapNotNull { it.root?.let(::find) }.firstOrNull()
    }

    private fun press(label: String) {
        await("Missing $label") { node(label)?.isEnabled == true }
        assertTrue("Could not press $label", node(label)!!.performAction(AccessibilityNodeInfo.ACTION_CLICK))
        instrumentation.waitForIdleSync()
    }

    private fun screenBounds(label: String): Rect = Rect().also { node(label)?.getBoundsInScreen(it) ?: error("Missing $label") }

    private fun launch(password: Boolean = false): KeyboardEditorContractActivity {
        val activity = instrumentation.startActivitySync(Intent(app, KeyboardEditorContractActivity::class.java)
            .putExtra("ime_options", EditorInfo.IME_ACTION_DONE).putExtra("password", password)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as KeyboardEditorContractActivity
        await("Editor never focused") { main { activity.hasWindowFocus() } }
        main { activity.editor.requestFocus() }
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        await("Editor never became active") { main { manager.isActive(activity.editor) } }
        main { manager.showSoftInput(activity.editor, InputMethodManager.SHOW_IMPLICIT) }
        await("Typing IME did not appear") { node("Keyboard tools") != null }
        return activity
    }

    @Test fun liveImeKeepsDailyUtilitiesReachableAcrossNumberAndTerminalLayers() {
        val manager = app.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val id = manager.inputMethodList.single { it.serviceName == KeyboardIme::class.java.name }.id
        val previousIme = Settings.Secure.getString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        val wasEnabled = manager.enabledInputMethodList.any { it.id == id }
        val original = KeyboardOptions.load(app)
        val automation = instrumentation.uiAutomation
        val flags = automation.serviceInfo.flags
        var activity: KeyboardEditorContractActivity? = null
        try {
            automation.serviceInfo = automation.serviceInfo.apply { this.flags = flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS }
            shell("ime enable $id"); shell("ime set $id")
            KeyboardOptions().save(app)
            activity = launch()
            fun closeEditor() {
                activity?.let { editor -> main {
                    manager.hideSoftInputFromWindow(editor.editor.windowToken, 0)
                    editor.finish()
                } }
                await("Previous IME did not close") { node("Keyboard tools") == null }
                activity = null
            }
            val display = app.resources.displayMetrics
            fun settled(labels: List<String>) {
                var previous: List<Rect>? = null
                await("IME utilities did not settle inside the display") {
                    if (android.os.Build.VERSION.SDK_INT >= 34) assertTrue(automation.clearCache())
                    val current = labels.map { runCatching { screenBounds(it) }.getOrNull() ?: return@await false }
                    val visible = current.all { rect -> rect.width() > 0 && rect.height() > 0 &&
                        rect.left >= 0 && rect.top >= 0 && rect.right <= display.widthPixels && rect.bottom <= display.heightPixels }
                    val stable = current == previous
                    previous = current
                    visible && stable
                }
            }
            fun screenshot(state: String) {
                val name = InstrumentationRegistry.getArguments().getString("r2Screenshots") ?: return
                check(android.os.Build.VERSION.SDK_INT >= 29) { "Live keyboard view capture requires Android 10 (API 29) or newer" }
                require(name.matches(Regex("[a-zA-Z0-9_-]{1,32}")))
                val directory = File(checkNotNull(app.getExternalFilesDir(null)), name)
                check(directory.isDirectory || directory.mkdirs()) { "Cannot create screenshot directory" }
                // Render only our own live keyboard view in this test process;
                // never capture the display, editor, notifications or system UI,
                // and never relax the production window flag.
                val keyboardBitmap = main {
                    val keyboard = android.view.inspector.WindowInspector.getGlobalWindowViews()
                        .flatMap { descendants(it) }.filterIsInstance<KeyboardSurface>().single { it.isShown }
                    android.graphics.Bitmap.createBitmap(keyboard.width, keyboard.height,
                        android.graphics.Bitmap.Config.ARGB_8888).also { keyboard.draw(android.graphics.Canvas(it)) }
                }
                FileOutputStream(File(directory, "$state-keyboard.png")).use {
                    keyboardBitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
                }
                keyboardBitmap.recycle()
            }
            fun capture(state: String, labels: List<String>) {
                try { settled(labels) } catch (error: AssertionError) { screenshot("$state-failed"); throw error }
                screenshot(state)
                labels.forEach { label ->
                    val rect = screenBounds(label)
                    assertTrue("$state $label is outside display: $rect", rect.width() > 0 && rect.height() > 0 &&
                        rect.left >= 0 && rect.top >= 0 && rect.right <= display.widthPixels && rect.bottom <= display.heightPixels)
                    println("R2 geometry $state $label=$rect")
                }
            }
            fun assertKeysInColumn(state: String, left: Int, right: Int) {
                // A render replaces all key views. Cached nodes can otherwise
                // mix old letter bounds with the newly expanded Tools rows.
                if (android.os.Build.VERSION.SDK_INT >= 34) assertTrue(automation.clearCache())
                fun collect(current: AccessibilityNodeInfo): List<Pair<String, Rect>> {
                    val own = if (current.className == "android.widget.Button" && current.isVisibleToUser)
                        listOf(current.contentDescription.toString() to Rect().also { current.getBoundsInScreen(it) })
                        else emptyList()
                    return own + (0 until current.childCount).flatMap { index -> current.getChild(index)?.let(::collect) ?: emptyList() }
                }
                val keys = automation.windows.filter { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
                    .flatMap { it.root?.let(::collect) ?: emptyList() }
                assertTrue("No visible keyboard buttons in $state", keys.isNotEmpty())
                keys.forEach { (label, rect) ->
                    assertTrue("$state $label escaped its column: $rect", rect.left >= left && rect.right <= right)
                    assertTrue("$state $label is clipped", rect.width() > 0 && rect.height() > 0 &&
                        rect.top >= 0 && rect.bottom <= display.heightPixels)
                }
                keys.forEachIndexed { index, (label, rect) ->
                    keys.drop(index + 1).forEach { (otherLabel, otherRect) ->
                        assertFalse("$state $label $rect overlaps $otherLabel $otherRect", Rect.intersects(rect, otherRect))
                    }
                }
            }
            capture("normal", listOf("Keyboard tools", "Edit actions", "Emoji", "Dictate", "Space", "Done"))
            val fullLeft = screenBounds("Keyboard tools").left
            val fullRight = screenBounds("Dictate").right
            val horizontalPadding = Ui.dp(app, 3) * 2
            val fullAvailableWidth = fullRight - fullLeft + horizontalPadding
            closeEditor()
            activity = launch(password = true)
            main {
                activity!!.editor.setText("Synthetic protected text")
                activity!!.editor.setSelection(0, activity!!.editor.length())
            }
            instrumentation.waitForIdleSync()
            settled(listOf("Keyboard tools", "Edit actions", "Dictate", "Space"))
            press("Edit actions")
            settled(listOf("Keyboard tools", "Dictate", "Cut"))
            val beforeFailure = mapOf("Keyboard tools" to screenBounds("Keyboard tools"), "Dictate" to screenBounds("Dictate"), "Cut" to screenBounds("Cut"))
            // The controlled password field rejects Cut. Verify actual failure
            // feedback separately from the keyboard-only geometry render.
            val rejection = automation.executeAndWaitForEvent({ press("Cut") }, { event ->
                event.eventType == android.view.accessibility.AccessibilityEvent.TYPE_ANNOUNCEMENT &&
                    event.text.any { it.toString() == "This key is not supported in the current field" }
            }, 3_000)
            rejection.recycle()
            main {
                assertEquals("Synthetic protected text", activity!!.editor.text.toString())
                assertEquals(0, activity!!.editor.selectionStart)
                assertEquals(activity!!.editor.length(), activity!!.editor.selectionEnd)
            }
            capture("failure-status", listOf("Keyboard tools", "Close edit actions", "Dictate", "Cut", "Copy", "Return to typing"))
            assertEquals(beforeFailure["Keyboard tools"], screenBounds("Keyboard tools"))
            assertEquals(beforeFailure["Dictate"], screenBounds("Dictate"))
            assertEquals(beforeFailure["Cut"], screenBounds("Cut"))
            press("Close edit actions")
            press("Keyboard tools"); press("Number row off"); press("Keyboard tools")
            await("Number row did not appear") { node("1") != null }
            capture("number", listOf("Keyboard tools", "Dictate", "Space", "Done", "1"))
            press("Keyboard tools"); press("Number row on"); press("Keyboard tools")
            await("Number row did not close") { node("1") == null }
            press("Keyboard tools"); press("Terminal controls off"); press("Keyboard tools")
            await("Terminal controls did not appear") { node("Escape") != null }
            assertTrue("Terminal-only layer showed a number row", node("1") == null)
            capture("terminal", listOf("Keyboard tools", "Dictate", "Space", "Done", "Escape", "Function keys"))
            for (light in listOf(false, true)) {
                closeEditor()
                KeyboardOptions(large = true, light = light).save(app)
                activity = launch()
                capture(if (light) "large-light" else "large-dark",
                    listOf("Keyboard tools", "Dictate", "Space", "Done"))
            }
            for (alignment in listOf(KeyboardAlignment.LEFT, KeyboardAlignment.RIGHT)) {
                closeEditor()
                KeyboardOptions(alignment = alignment, light = alignment == KeyboardAlignment.RIGHT,
                    large = true).save(app)
                activity = launch()
                val side = alignment.name.lowercase(java.util.Locale.ROOT)
                val daily = listOf("Keyboard tools", "Edit actions", "Dictate", "Space", "Done", "q", "p")
                capture("$side-normal", daily)
                val sideLeft = screenBounds("Keyboard tools").left
                val sideRight = screenBounds("Dictate").right
                val expectedColumn = if (fullAvailableWidth <= Ui.dp(app, 320)) fullAvailableWidth
                    else (fullAvailableWidth * .82).toInt().coerceIn(Ui.dp(app, 320), Ui.dp(app, 360))
                assertEquals("Live column width violates the layout contract", expectedColumn.toDouble(),
                    (sideRight - sideLeft + horizontalPadding).toDouble(), 1.0)
                if (fullAvailableWidth > Ui.dp(app, 320)) {
                    assertTrue("One-hand layout did not narrow the toolbar", sideRight - sideLeft < fullRight - fullLeft)
                    if (alignment == KeyboardAlignment.LEFT) assertEquals(fullLeft, sideLeft)
                    else assertEquals(fullRight, sideRight)
                }
                fun sideCapture(state: String, labels: List<String>) {
                    capture("$side-$state", labels)
                    assertEquals("$state moved the left edge", sideLeft, screenBounds("Keyboard tools").left)
                    assertEquals("$state moved the right edge", sideRight, screenBounds("Dictate").right)
                    assertKeysInColumn("$side-$state", sideLeft, sideRight)
                }
                press("Keyboard tools")
                sideCapture("tools", listOf("Keyboard tools", "Dictate", "Full width layout", "Left hand layout", "Right hand layout", "Keyboard settings", "Space", "Done"))
                assertTrue(node(if (alignment == KeyboardAlignment.LEFT) "Left hand layout" else "Right hand layout")!!.isSelected)
                assertFalse(node("Full width layout")!!.isSelected)
                press("Keyboard tools")
                press("Keyboard tools"); press("Number row off"); press("Keyboard tools")
                sideCapture("number", daily + listOf("1", "0"))
                press("Keyboard tools"); press("Number row on"); press("Keyboard tools")
                press("Switch letters and symbols")
                sideCapture("symbols", listOf("Keyboard tools", "Dictate", "Switch letters and symbols", "Space", "Done", "1", "0", "@", "/"))
                press("More symbols")
                sideCapture("more-symbols", listOf("Keyboard tools", "Dictate", "More numbers and symbols", "Space", "Done", "~", "∆"))
                press("Switch letters and symbols")
                press("Keyboard tools"); press("Terminal controls off"); press("Keyboard tools")
                sideCapture("terminal", daily + listOf("Escape", "Function keys"))
                press("Function keys")
                sideCapture("functions", listOf("Keyboard tools", "Dictate", "F1", "F12", "Insert", "Forward delete", "Space", "Done"))
                press("Return to letters")
                press("Keyboard tools"); press("Terminal controls on"); press("Keyboard tools")
                press("Edit actions")
                sideCapture("edit", listOf("Keyboard tools", "Dictate", "Cut", "Copy", "Paste", "Return to typing"))
                press("Close edit actions")
                press("Keyboard tools")
                press("Full width layout")
                capture("$side-full-return", listOf("Keyboard tools", "Dictate", "Full width layout"))
                assertTrue(node("Full width layout")!!.isSelected)
                assertEquals(KeyboardAlignment.FULL, KeyboardOptions.load(app).alignment)
                assertEquals(fullLeft, screenBounds("Keyboard tools").left)
                assertEquals(fullRight, screenBounds("Dictate").right)
            }
            for (alignment in KeyboardAlignment.entries) {
                closeEditor()
                KeyboardOptions(alignment = alignment, light = alignment == KeyboardAlignment.RIGHT,
                    large = true).save(app)
                activity = launch()
                var expectedText = ""
                val left = screenBounds("Keyboard tools").left
                val right = screenBounds("Dictate").right
                for (layout in LetterLayout.entries) {
                    val state = "${layout.stored}-${alignment.stored}"
                    val choices = LetterLayout.entries.map { "${it.label} letter layout" }
                    press("Keyboard tools")
                    press("${layout.label} letter layout")
                    capture("$state-tools", choices + listOf("Keyboard settings", "Space", "Done"))
                    LetterLayout.entries.forEach { choice ->
                        assertEquals(choice == layout, node("${choice.label} letter layout")!!.isSelected)
                    }
                    assertEquals(layout, KeyboardOptions.load(app).letterLayout)
                    assertEquals(alignment, KeyboardOptions.load(app).alignment)
                    assertKeysInColumn("$state-tools", left, right)
                    press("Keyboard tools")
                    val letters = layout.rows.joinToString("").map { it.toString() }
                    capture(state, letters + listOf("Keyboard tools", "Dictate", "Shift off", "Delete", "Space", "Done"))
                    assertKeysInColumn(state, left, right)
                    var priorRowBottom = -1
                    layout.rows.forEach { row ->
                        val positions = row.map { screenBounds(it.toString()) }
                        assertTrue("$state rows are out of order", positions.first().top >= priorRowBottom)
                        positions.forEach { assertEquals(positions.first().top, it.top) }
                        positions.zipWithNext().forEach { (a, b) ->
                            assertTrue("$state letters are out of order", a.right <= b.left)
                        }
                        priorRowBottom = positions.first().bottom
                    }
                    val sample = "${layout.top.first()}${layout.home.first()}${layout.bottom.first()}"
                    sample.forEach { press(it.toString()) }
                    expectedText += sample
                    await("$state visible keys did not reach the native editor") {
                        main { activity!!.editor.text.toString() == expectedText }
                    }
                }
            }
            InstrumentationRegistry.getArguments().getString("r2Screenshots")?.let { name ->
                require(name.matches(Regex("[a-zA-Z0-9_-]{1,32}")))
                closeEditor()
                KeyboardOptions().save(app)
                val preferences = instrumentation.startActivitySync(Intent(app, KeyboardSettingsActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                try {
                    await("Preferences never focused") { main { preferences.hasWindowFocus() } }
                    instrumentation.waitForIdleSync()
                    // This fresh settings screen contains an empty private practice
                    // field. Render the owned view without changing FLAG_SECURE.
                    val bitmap = main {
                        val decor = preferences.window.decorView
                        val views = descendants(decor)
                        assertTrue(views.filterIsInstance<android.widget.EditText>().all { it.text.isEmpty() })
                        for (label in listOf("Full width", "Left hand", "Right hand")) {
                            val radio = views.filterIsInstance<android.widget.RadioButton>().single { it.text == label }
                            val bounds = Rect()
                            assertTrue("$label is not visible in Settings", radio.getGlobalVisibleRect(bounds) &&
                                bounds.width() == radio.width && bounds.height() == radio.height)
                            assertEquals(label == "Full width", radio.isChecked)
                        }
                        for (choice in LetterLayout.entries) {
                            val radio = views.filterIsInstance<android.widget.RadioButton>().single { it.text == choice.label }
                            val bounds = Rect()
                            assertTrue("${choice.label} is not visible in Settings", radio.getGlobalVisibleRect(bounds) &&
                                bounds.width() == radio.width && bounds.height() == radio.height)
                            assertEquals(choice == LetterLayout.QWERTY, radio.isChecked)
                        }
                        android.graphics.Bitmap.createBitmap(decor.width, decor.height,
                            android.graphics.Bitmap.Config.ARGB_8888).also { decor.draw(android.graphics.Canvas(it)) }
                    }
                    try {
                        val directory = File(checkNotNull(app.getExternalFilesDir(null)), name)
                        check(directory.isDirectory || directory.mkdirs())
                        FileOutputStream(File(directory, "settings-alignment.png")).use {
                            bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
                        }
                    } finally { bitmap.recycle() }
                } finally { main { preferences.finish() } }
            }
        } finally {
            activity?.let { main { it.finish() } }
            if (!previousIme.isNullOrBlank()) shell("ime set $previousIme")
            if (!wasEnabled) shell("ime disable $id")
            original.save(app)
            automation.serviceInfo = automation.serviceInfo.apply { this.flags = flags }
        }
    }
}
