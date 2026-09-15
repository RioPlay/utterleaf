package org.utterleaf.voice

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Rect
import android.os.SystemClock
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.Button
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class CompactLayerTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun <T> main(block: () -> T): T {
        if (android.os.Looper.myLooper() == android.os.Looper.getMainLooper()) return block()
        val result = AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }

    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    private class Calls {
        val inserted = mutableListOf<String>()
        var settings = 0
        var switches = 0
        val actions = mutableListOf<EditorAction>()
        val special = mutableListOf<List<Any>>()
    }

    private inner class Fixture(val activity: KeyboardSettingsActivity, val host: FrameLayout,
        val panel: TypingPanel, val calls: Calls, val widthDp: Int) {
        private var downTime = 0L

        fun buttons() = main { descendants(panel.view).filterIsInstance<Button>() }
        fun key(description: String) = buttons().single { it.contentDescription == description }
        fun has(description: String) = buttons().any { it.contentDescription == description }
        fun height() = main { panel.view.height }
        fun bounds(button: View): Rect = main {
            Rect().also { button.getGlobalVisibleRect(it) }
        }
        fun fullyVisible(button: View): Boolean = main {
            val rect = Rect()
            button.isShown && button.getGlobalVisibleRect(rect) && rect.width() == button.width &&
                rect.height() >= button.height - 1
        }
        fun send(button: Button, action: Int, dx: Float = 0f, dy: Float = 0f) = main {
            val now = SystemClock.uptimeMillis()
            if (action == MotionEvent.ACTION_DOWN) downTime = now
            val event = MotionEvent.obtain(downTime, now, action, button.width / 2f + dx, button.height / 2f + dy, 0)
            try { button.dispatchTouchEvent(event) } finally { event.recycle() }
        }
        fun tap(button: Button) {
            send(button, MotionEvent.ACTION_DOWN)
            send(button, MotionEvent.ACTION_UP)
            instrumentation.waitForIdleSync()
        }
        fun multiTouch(button: Button) = main {
            val properties = Array(2) { index -> MotionEvent.PointerProperties().apply {
                id = index; toolType = MotionEvent.TOOL_TYPE_FINGER
            } }
            val coordinates = Array(2) { index -> MotionEvent.PointerCoords().apply {
                x = button.width / 2f + index * 2; y = button.height / 2f; pressure = 1f; size = 1f
            } }
            val event = MotionEvent.obtain(downTime, SystemClock.uptimeMillis(),
                MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                2, properties, coordinates, 0, 0, 1f, 1f, 0, 0,
                android.view.InputDevice.SOURCE_TOUCHSCREEN, 0)
            try { button.dispatchTouchEvent(event) } finally { event.recycle() }
        }
        fun reveal(description: String): Button = key(description).also {
            assertTrue("$description must be visible without scrolling", fullyVisible(it))
        }
        fun cancelMenuTouch() {
            val target = key("Keyboard layout")
            send(target, MotionEvent.ACTION_DOWN)
            send(target, MotionEvent.ACTION_MOVE, dx = -target.width * 2f)
            send(target, MotionEvent.ACTION_UP, dx = -target.width * 2f)
            instrumentation.waitForIdleSync()
        }
        fun capture(state: String) {
            val directoryName = InstrumentationRegistry.getArguments().getString("r2Screenshots") ?: return
            require(directoryName.matches(Regex("[a-zA-Z0-9_-]{1,32}")))
            val anchors = when (state) {
                "settings-layer" -> listOf("Close keyboard settings", "Full width layout")
                "edit-layer" -> listOf("Close edit actions", "Cut")
                "terminal-functions" -> listOf("Return to terminal letters", "F1", "Space")
                "terminal-navigation" -> listOf("Return to terminal letters", "Left arrow", "Space")
                "tools-start", "tools-slid" -> listOf("Return to typing", "Keyboard layout", "Edit actions")
                else -> listOf("q", "Space")
            }
            var previousScroll = -1
            var stableSamples = 0
            UiAwait.until("$state keyboard rows and tool strip did not settle before capture") {
                main {
                    val rowsVisible = anchors.all { label ->
                        val button = key(label); val rect = Rect()
                        button.getGlobalVisibleRect(rect) && rect.width() == button.width &&
                            rect.height() >= button.height - 1
                    }
                    val currentScroll = descendants(panel.view).filterIsInstance<HorizontalScrollView>()
                        .singleOrNull()?.scrollX ?: 0
                    stableSamples = if (currentScroll == previousScroll) stableSamples + 1 else 0
                    previousScroll = currentScroll
                    panel.view.width > 0 && panel.view.height > 0 && rowsVisible && stableSamples >= 15
                }
            }
            val directory = File(checkNotNull(app.getExternalFilesDir(null)), directoryName)
            check(directory.isDirectory || directory.mkdirs())
            val bitmap = main {
                Bitmap.createBitmap(panel.view.width, panel.view.height, Bitmap.Config.ARGB_8888).also {
                    panel.view.draw(Canvas(it))
                }
            }
            try {
                FileOutputStream(File(directory, "$state-keyboard.png")).use {
                    bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
                }
            } finally { bitmap.recycle() }
        }
    }

    private fun withPanel(options: KeyboardOptions = KeyboardOptions(), privateEditing: Boolean = false,
        widthDp: Int = 360, test: (Fixture) -> Unit) {
        val activity = instrumentation.startActivitySync(Intent(app, KeyboardSettingsActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as KeyboardSettingsActivity
        val laidOut = CountDownLatch(1)
        val fixture = main {
            val calls = Calls()
            val panel = TypingPanel(activity, options,
                { calls.inserted += it; true }, {}, {}, {}, {}, { calls.settings++ }, { calls.switches++ },
                terminalKey = { code, ctrl, alt, shift -> calls.special += listOf(code, ctrl, alt, shift); true },
                editorAction = { calls.actions += it; true }, privateEditing = privateEditing,
                actionAvailable = { true })
            panel.reset(allowVoice = false, numeric = false, action = "Done")
            panel.view.addOnLayoutChangeListener { _, left, top, right, bottom, _, _, _, _ ->
                if (right > left && bottom > top) laidOut.countDown()
            }
            val host = FrameLayout(activity)
            host.addView(panel.view, FrameLayout.LayoutParams(Ui.dp(activity, widthDp), -2))
            activity.setContentView(host)
            Fixture(activity, host, panel, calls, widthDp)
        }
        try {
            assertTrue("Compact keyboard did not lay out", laidOut.await(5, TimeUnit.SECONDS))
            instrumentation.waitForIdleSync()
            test(fixture)
        } finally {
            main { fixture.panel.dispose(); activity.finish() }
            instrumentation.waitForIdleSync()
        }
    }

    @Test fun toolsSettingsAndEditingReplaceRowsAcrossSupportedGeometry() {
        main {
            for (width in listOf(320, 360, 412)) for (light in listOf(false, true))
                for (large in listOf(false, true)) for (alignment in KeyboardAlignment.entries) {
                    val options = KeyboardOptions(light = light, large = large, alignment = alignment)
                    val panel = TypingPanel(app, options, { true }, {}, {}, {}, {}, {}, {},
                        editorAction = { true }, actionAvailable = { true })
                    panel.reset(false, false, "Done")
                    fun buttons() = descendants(panel.view).filterIsInstance<Button>()
                    fun key(label: String) = buttons().single { it.contentDescription == label }
                    fun bounds(label: String) = key(label).let { button ->
                        Rect(0, 0, button.width, button.height).also { panel.view.offsetDescendantRectToMyCoords(button, it) }
                    }
                    fun checkActions() {
                        buttons().forEach { button ->
                            val rect = bounds(button.contentDescription.toString())
                            assertTrue("Action clipped at $width $alignment: ${button.contentDescription}",
                                rect.left >= 0 && rect.right <= panel.view.width && rect.top >= 0 && rect.bottom <= panel.view.height)
                            assertTrue("Action too small: ${button.contentDescription}",
                                button.width >= Ui.dp(app, 48) && button.height >= Ui.dp(app, 48))
                        }
                    }
                    fun layout(): Int {
                        val widthPx = Ui.dp(app, width)
                        panel.view.measure(View.MeasureSpec.makeMeasureSpec(widthPx, View.MeasureSpec.EXACTLY),
                            View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
                        panel.view.layout(0, 0, widthPx, panel.view.measuredHeight)
                        return panel.view.height
                    }
                    val normalHeight = layout()
                    key("Keyboard tools").performClick()
                    assertTrue("Tools grew ${width}dp light=$light large=$large $alignment", layout() <= normalHeight)
                    checkActions()
                    for (label in listOf("Return to typing", "Edit actions", "Keyboard layout", "Keyboard settings", "Latin compose")) {
                        assertTrue("Missing $label in compact tools", key(label).isFocusable)
                    }
                    key("Return to typing").performClick()
                    assertTrue(key(",").performLongClick())
                    val settingsHeight = layout()
                    assertTrue("Settings layer grew the keyboard", settingsHeight <= normalHeight)
                    assertFalse(buttons().any { it.contentDescription == "q" })
                    for (label in listOf("Close keyboard settings", "Keyboard settings", "Switch keyboard",
                        "Full width layout", "Left hand layout", "Right hand layout", "QWERTY letter layout",
                        "QWERTZ letter layout", "AZERTY letter layout", "Number row off", "Terminal controls off")) {
                        val button = key(label)
                        val rect = Rect(0, 0, button.width, button.height)
                        panel.view.offsetDescendantRectToMyCoords(button, rect)
                        assertTrue("$label clipped at ${width}dp light=$light large=$large $alignment: $rect",
                            rect.left >= 0 && rect.right <= panel.view.width && rect.top >= 0 && rect.bottom <= panel.view.height)
                    }
                    key("Close keyboard settings").performClick()
                    assertEquals(normalHeight, layout())
                    key("Edit actions").performClick()
                    assertTrue("Edit layer grew the keyboard", layout() <= normalHeight)
                    checkActions()
                    assertEquals(bounds("Move cursor up").centerX(), bounds("Select text").centerX())
                    assertEquals(bounds("Move cursor down").centerX(), bounds("Select text").centerX())
                    assertTrue(bounds("Move cursor up").bottom <= bounds("Select text").top)
                    assertTrue(bounds("Move cursor down").top >= bounds("Select text").bottom)
                    assertTrue(bounds("Move cursor left").right <= bounds("Select text").left)
                    assertTrue(bounds("Move cursor right").left >= bounds("Select text").right)
                    assertTrue(key("Close edit actions").isFocusable)
                    assertTrue(key("Cut").isFocusable)
                    panel.dispose()
                }
        }
    }

    @Test fun allActionsAreVisibleAndCommaTapHoldCancellationRemainDistinct() {
        val captureWidth = InstrumentationRegistry.getArguments().getString("r2WidthDp")?.toIntOrNull() ?: 360
        val captureLight = InstrumentationRegistry.getArguments().getString("r2Light") == "true"
        val captureLarge = InstrumentationRegistry.getArguments().getString("r2Large") == "true"
        val captureAlignment = InstrumentationRegistry.getArguments().getString("r2Alignment")
            ?.let { stored -> KeyboardAlignment.entries.singleOrNull { it.stored == stored } } ?: KeyboardAlignment.FULL
        withPanel(KeyboardOptions(holdDelayMs = 120, light = captureLight, large = captureLarge,
            alignment = captureAlignment), widthDp = captureWidth) { fixture ->
            val normalHeight = fixture.height()
            fixture.capture("normal")
            fixture.tap(fixture.key("Keyboard tools"))
            assertTrue(fixture.height() <= normalHeight)
            assertTrue(fixture.fullyVisible(fixture.key("Return to typing")))
            assertTrue(fixture.fullyVisible(fixture.key("Edit actions")))
            fixture.capture("tools-start")
            fixture.cancelMenuTouch()
            assertTrue(fixture.has("Return to typing"))
            assertFalse(fixture.has("Close keyboard settings"))
            assertTrue("Swipe release activated an editor tool", fixture.calls.actions.isEmpty())
            assertEquals(0, fixture.calls.settings)
            val layout = fixture.reveal("Keyboard layout")
            fixture.capture("tools-slid")
            fixture.tap(layout)
            assertTrue(fixture.has("Close keyboard settings"))
            assertFalse(fixture.has("q"))
            assertTrue(fixture.height() <= normalHeight)
            fixture.capture("settings-layer")
            fixture.tap(fixture.key("Close keyboard settings"))

            fixture.tap(fixture.key("Edit actions"))
            assertTrue(fixture.has("Close edit actions"))
            assertTrue(fixture.height() <= normalHeight)
            fixture.capture("edit-layer")
            fixture.tap(fixture.key("Close edit actions"))

            var comma = fixture.key(",")
            fixture.send(comma, MotionEvent.ACTION_DOWN)
            fixture.send(comma, MotionEvent.ACTION_UP)
            assertEquals(listOf(","), fixture.calls.inserted)

            comma = fixture.key(",")
            fixture.send(comma, MotionEvent.ACTION_DOWN)
            UiAwait.until("Comma hold did not open compact settings") { fixture.has("Close keyboard settings") }
            fixture.send(comma, MotionEvent.ACTION_UP)
            assertEquals("Hold inserted a comma", listOf(","), fixture.calls.inserted)
            fixture.tap(fixture.key("Keyboard settings"))
            assertEquals(1, fixture.calls.settings)
            fixture.tap(fixture.key("Close keyboard settings"))

            comma = fixture.key(",")
            fixture.send(comma, MotionEvent.ACTION_DOWN)
            fixture.send(comma, MotionEvent.ACTION_CANCEL)
            UiAwait.remains("Cancelled comma hold launched settings or typed",
                durationMs = 300) { !fixture.has("Close keyboard settings") && fixture.calls.inserted == listOf(",") }

            comma = fixture.key(",")
            fixture.send(comma, MotionEvent.ACTION_DOWN)
            fixture.send(comma, MotionEvent.ACTION_MOVE, dx = -comma.width.toFloat() * 2)
            fixture.send(comma, MotionEvent.ACTION_UP, dx = -comma.width.toFloat() * 2)
            UiAwait.remains("Slide-off comma hold launched settings or typed",
                durationMs = 300) { !fixture.has("Close keyboard settings") && fixture.calls.inserted == listOf(",") }

            comma = fixture.key(",")
            fixture.send(comma, MotionEvent.ACTION_DOWN)
            fixture.multiTouch(comma)
            fixture.send(comma, MotionEvent.ACTION_UP)
            UiAwait.remains("Multitouch comma hold launched settings or typed",
                durationMs = 300) { !fixture.has("Close keyboard settings") && fixture.calls.inserted == listOf(",") }

            comma = fixture.key(",")
            fixture.send(comma, MotionEvent.ACTION_DOWN)
            main { fixture.panel.reset(false, false, "Done") }
            fixture.send(comma, MotionEvent.ACTION_UP)
            UiAwait.remains("Stale comma key launched settings or typed",
                durationMs = 300) { !fixture.has("Close keyboard settings") && fixture.calls.inserted == listOf(",") }

            comma = fixture.key(",")
            fixture.send(comma, MotionEvent.ACTION_DOWN)
            main { fixture.host.removeView(fixture.panel.view) }
            UiAwait.remains("Detached comma hold launched settings or typed",
                durationMs = 300) { !fixture.has("Close keyboard settings") && fixture.calls.inserted == listOf(",") }
            main {
                fixture.host.addView(fixture.panel.view,
                    FrameLayout.LayoutParams(Ui.dp(app, fixture.widthDp), FrameLayout.LayoutParams.WRAP_CONTENT))
                fixture.panel.reset(false, false, "Done")
            }
            UiAwait.until("Compact keyboard did not recover after comma detach") {
                fixture.has(",") && fixture.fullyVisible(fixture.key(","))
            }

            comma = fixture.key(",")
            assertTrue(main { comma.performAccessibilityAction(AccessibilityNodeInfo.ACTION_LONG_CLICK, null) })
            assertTrue(fixture.has("Close keyboard settings"))
            assertEquals(listOf(","), fixture.calls.inserted)
        }
    }

    @Test fun privateCommaHoldAndTerminalLayerExitsFailClosed() {
        val captureWidth = InstrumentationRegistry.getArguments().getString("r2WidthDp")?.toIntOrNull() ?: 360
        val captureLight = InstrumentationRegistry.getArguments().getString("r2Light") == "true"
        val captureLarge = InstrumentationRegistry.getArguments().getString("r2Large") == "true"
        val captureAlignment = InstrumentationRegistry.getArguments().getString("r2Alignment")
            ?.let { stored -> KeyboardAlignment.entries.singleOrNull { it.stored == stored } } ?: KeyboardAlignment.FULL
        withPanel(KeyboardOptions(holdDelayMs = 120), privateEditing = true) { fixture ->
            val comma = fixture.key(",")
            fixture.send(comma, MotionEvent.ACTION_DOWN)
            UiAwait.remains("Private comma hold escaped to settings",
                durationMs = 300) { !fixture.has("Close keyboard settings") && fixture.calls.settings == 0 && fixture.calls.inserted.isEmpty() }
            fixture.send(comma, MotionEvent.ACTION_UP)
            assertTrue(main { comma.performAccessibilityAction(AccessibilityNodeInfo.ACTION_LONG_CLICK, null) })
            assertFalse(fixture.has("Close keyboard settings"))
            assertEquals(0, fixture.calls.settings)
            assertTrue(fixture.calls.inserted.isEmpty())
        }

        withPanel(KeyboardOptions(terminal = true, numberRow = true, light = captureLight,
            large = captureLarge, alignment = captureAlignment), widthDp = captureWidth) { fixture ->
            val terminalHeight = fixture.height()
            fixture.capture("terminal-letters")
            assertTrue(fixture.has("Navigation keys"))
            assertTrue(fixture.has("Left arrow"))
            fixture.tap(fixture.key("Control off"))
            fixture.tap(fixture.key("Function keys"))
            assertTrue(fixture.has("F1"))
            assertTrue(fixture.has("Return to terminal letters"))
            assertTrue(fixture.height() <= terminalHeight)
            fixture.capture("terminal-functions")
            fixture.tap(fixture.key("Return to terminal letters"))
            assertTrue(fixture.has("Control off"))
            assertFalse(fixture.has("F1"))
            fixture.tap(fixture.key("Navigation keys"))
            assertTrue(fixture.has("Left arrow"))
            assertFalse(fixture.has("q"))
            assertTrue("Nav layer grew the keyboard", fixture.height() <= terminalHeight)
            fixture.capture("terminal-navigation")
            fixture.tap(fixture.key("Return to terminal letters"))
            assertTrue(fixture.has("q"))
            assertTrue(fixture.has("Left arrow"))
        }
    }

    @Test fun selectTapSelectsNeighboringWordAndHoldSelectsAll() {
        withPanel { fixture ->
            fixture.tap(fixture.key("Edit actions"))
            val select = fixture.key("Select text")
            assertFalse(select.isSelected)
            fixture.tap(select)
            assertEquals(listOf(listOf(KeyEvent.KEYCODE_DPAD_LEFT, true, false, true)), fixture.calls.special)
            assertFalse("Select is a one-shot word action, not a mode", select.isSelected)
            fixture.tap(fixture.key("Move cursor left"))
            assertEquals(listOf(
                listOf(KeyEvent.KEYCODE_DPAD_LEFT, true, false, true),
                listOf(KeyEvent.KEYCODE_DPAD_LEFT, false, false, false)), fixture.calls.special)
            assertTrue(main { select.performLongClick() })
            assertEquals(listOf(EditorAction.SELECT_ALL), fixture.calls.actions)
            assertFalse(select.isSelected)
        }
    }

    @Test fun symbolPagesExposeTheUsPunctuationSet() {
        withPanel { fixture ->
            fixture.tap(fixture.key("Switch letters and symbols"))
            val first = fixture.buttons().map { it.text.toString() }.toSet()
            for (mark in listOf("@", "#", "$", "%", "&", "-", "+", "(", ")", "/", "*", "\"", "'", ":", ";", "!", "?", "_")) {
                assertTrue("Missing $mark on the first symbol page", mark in first)
            }
            fixture.tap(fixture.key("More symbols"))
            val second = fixture.buttons().map { it.text.toString() }.toSet()
            for (mark in listOf("`", "~", "^", "=", "[", "]", "{", "}", "\\", "|", ",", ".", "<", ">", "±", "×", "÷", "§", "©", "®")) {
                assertTrue("Missing $mark on the more-symbols page", mark in second)
            }
        }
    }
}
