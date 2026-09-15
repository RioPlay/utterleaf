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
            val target = key("Accents and alternate characters")
            send(target, MotionEvent.ACTION_DOWN)
            send(target, MotionEvent.ACTION_MOVE, dx = -target.width * 2f)
            send(target, MotionEvent.ACTION_UP, dx = -target.width * 2f)
            instrumentation.waitForIdleSync()
        }
        fun capture(state: String) {
            val directoryName = InstrumentationRegistry.getArguments().getString("r2Screenshots") ?: return
            require(directoryName.matches(Regex("[a-zA-Z0-9_-]{1,32}")))
            val anchors = when (state) {
                "tools-hub" -> listOf("Close tools and settings", "Keyboard settings", "Latin compose")
                "extra-keys" -> listOf("Escape", "Left arrow", "Space")
                "extra-functions" -> listOf("Hide function keys", "F1", "Space")
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

    @Test fun hubAndPanelLayersStayUsableAcrossSupportedGeometry() {
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
                    assertTrue(key("Emoji").performLongClick())
                    assertTrue("Hub grew ${width}dp light=$light large=$large $alignment", layout() <= normalHeight)
                    checkActions()
                    for (label in listOf("Close tools and settings", "Keyboard settings", "Switch keyboard", "Latin compose",
                        "Full width layout", "Left hand layout", "Right hand layout", "QWERTY letter layout",
                        "QWERTZ letter layout", "AZERTY letter layout", "Number row on", "Extra keys on")) {
                        val button = key(label)
                        assertTrue("Missing $label in the hub", button.isFocusable)
                        val rect = bounds(label)
                        assertTrue("$label clipped at ${width}dp light=$light large=$large $alignment: $rect",
                            rect.left >= 0 && rect.right <= panel.view.width && rect.top >= 0 && rect.bottom <= panel.view.height)
                    }
                    key("Close tools and settings").performClick()
                    assertEquals(normalHeight, layout())
                    key("Extra keys").performClick()
                    val panelHeight = layout()
                    assertTrue("The fold-out panel must add its rows", panelHeight > normalHeight)
                    for (label in listOf("Function keys", "Escape", "Tab", "Control off", "Alt off",
                        "Home", "End", "Insert", "Forward delete", "Page up", "Page down",
                        "Left arrow", "Down arrow", "Up arrow", "Right arrow", "q", "Space")) {
                        val rect = bounds(label)
                        assertTrue("$label clipped at ${width}dp light=$light large=$large $alignment: $rect",
                            rect.left >= 0 && rect.right <= panel.view.width && rect.top >= 0 && rect.bottom <= panel.view.height)
                    }
                    key("Function keys").performClick()
                    val functionsHeight = layout()
                    assertTrue("F-keys must add their rows", functionsHeight > panelHeight)
                    for (label in listOf("Hide function keys", "F1", "F12", "q")) {
                        val rect = bounds(label)
                        assertTrue("$label clipped at ${width}dp: $rect",
                            rect.left >= 0 && rect.right <= panel.view.width && rect.top >= 0 && rect.bottom <= panel.view.height)
                    }
                    key("Hide function keys").performClick()
                    assertEquals(panelHeight, layout())
                    key("Extra keys").performClick()
                    assertEquals(normalHeight, layout())
                    panel.dispose()
                }
        }
    }

    @Test fun emojiTapHoldAndSwipeCancellationRemainDistinct() {
        val captureWidth = InstrumentationRegistry.getArguments().getString("r2WidthDp")?.toIntOrNull() ?: 360
        val captureLight = InstrumentationRegistry.getArguments().getString("r2Light") == "true"
        val captureLarge = InstrumentationRegistry.getArguments().getString("r2Large") == "true"
        val captureAlignment = InstrumentationRegistry.getArguments().getString("r2Alignment")
            ?.let { stored -> KeyboardAlignment.entries.singleOrNull { it.stored == stored } } ?: KeyboardAlignment.FULL
        withPanel(KeyboardOptions(holdDelayMs = 120, light = captureLight, large = captureLarge,
            alignment = captureAlignment), widthDp = captureWidth) { fixture ->
            val normalHeight = fixture.height()
            fixture.capture("normal")
            // A tap opens the emoji picker, never the tools hub.
            fixture.tap(fixture.key("Emoji"))
            assertFalse(fixture.has("Close tools and settings"))
            assertTrue(fixture.calls.inserted.isEmpty())
            assertEquals(0, fixture.calls.settings)
            fixture.tap(fixture.key("Return from emoji to letters"))
            assertEquals(normalHeight, fixture.height())

            // The long press is the tools hub; it never inserts text.
            val emojiKey = fixture.key("Emoji")
            assertTrue(main { emojiKey.performAccessibilityAction(AccessibilityNodeInfo.ACTION_LONG_CLICK, null) })
            assertTrue(fixture.has("Close tools and settings"))
            assertTrue(fixture.calls.inserted.isEmpty())
            fixture.capture("tools-hub")
            fixture.cancelMenuTouch()
            assertTrue(fixture.has("Close tools and settings"))
            assertTrue("Swipe release activated a hub tool",
                fixture.calls.actions.isEmpty() && fixture.calls.settings == 0)
            fixture.tap(fixture.reveal("Latin compose"))
            assertTrue(fixture.has("Cancel compose"))
            fixture.tap(fixture.key("Cancel compose"))
            assertEquals(normalHeight, fixture.height())

            // Panel open and close keep the everyday keyboard intact.
            fixture.tap(fixture.key("Extra keys"))
            assertTrue(fixture.has("Escape"))
            assertTrue(fixture.height() > normalHeight)
            fixture.capture("extra-keys")
            fixture.tap(fixture.key("Function keys"))
            assertTrue(fixture.has("F1"))
            fixture.capture("extra-functions")
            fixture.tap(fixture.key("Hide function keys"))
            assertFalse(fixture.has("F1"))
            fixture.tap(fixture.key("Extra keys"))
            assertFalse(fixture.has("Escape"))
            assertEquals(normalHeight, fixture.height())

            assertTrue(main { fixture.key("Emoji").performAccessibilityAction(AccessibilityNodeInfo.ACTION_LONG_CLICK, null) })
            fixture.tap(fixture.key("Keyboard settings"))
            assertEquals(1, fixture.calls.settings)
        }
    }

    @Test fun privateHubStaysRestrictedAndPanelExitsStayClean() {
        val captureWidth = InstrumentationRegistry.getArguments().getString("r2WidthDp")?.toIntOrNull() ?: 360
        val captureLight = InstrumentationRegistry.getArguments().getString("r2Light") == "true"
        val captureLarge = InstrumentationRegistry.getArguments().getString("r2Large") == "true"
        val captureAlignment = InstrumentationRegistry.getArguments().getString("r2Alignment")
            ?.let { stored -> KeyboardAlignment.entries.singleOrNull { it.stored == stored } } ?: KeyboardAlignment.FULL
        withPanel(KeyboardOptions(holdDelayMs = 120), privateEditing = true) { fixture ->
            fixture.tap(fixture.key("Keyboard tools"))
            assertTrue(fixture.has("Close tools and settings"))
            assertTrue(fixture.has("Latin compose"))
            assertFalse(fixture.has("Keyboard settings"))
            assertFalse(fixture.has("Switch keyboard"))
            assertFalse(fixture.has("Private draft"))
            assertEquals(0, fixture.calls.settings)
            assertTrue(fixture.calls.inserted.isEmpty())
            fixture.tap(fixture.key("Close tools and settings"))
        }

        withPanel(KeyboardOptions(numberRow = true, light = captureLight,
            large = captureLarge, alignment = captureAlignment), widthDp = captureWidth) { fixture ->
            val normalHeight = fixture.height()
            fixture.tap(fixture.key("Extra keys"))
            assertTrue(fixture.has("Escape"))
            assertTrue(fixture.has("Left arrow"))
            fixture.tap(fixture.key("Control off"))
            fixture.tap(fixture.key("Function keys"))
            assertTrue(fixture.has("F1"))
            assertTrue(fixture.has("Hide function keys"))
            assertTrue(fixture.height() > normalHeight)
            fixture.capture("extra-functions")
            fixture.tap(fixture.key("Hide function keys"))
            assertTrue(fixture.has("Control on"))
            assertFalse(fixture.has("F1"))
            assertTrue("The panel keeps letters visible", fixture.has("q"))
            assertTrue(fixture.has("Left arrow"))
            fixture.capture("extra-keys")
            fixture.tap(fixture.key("Extra keys"))
            assertTrue(fixture.has("q"))
            assertFalse(fixture.has("Left arrow"))
        }
    }

    @Test fun selectAllTapAndWordHoldStayDistinct() {
        withPanel { fixture ->
            assertTrue(main { fixture.key("Emoji").performLongClick() })
            val selectAll = fixture.key("Select all text")
            assertFalse(selectAll.isSelected)
            fixture.tap(selectAll)
            assertEquals(listOf(EditorAction.SELECT_ALL), fixture.calls.actions)
            assertFalse("Select all is a one-shot action, not a mode", selectAll.isSelected)
            assertTrue(main { selectAll.performLongClick() })
            assertEquals(listOf(listOf(KeyEvent.KEYCODE_DPAD_LEFT, true, false, true)), fixture.calls.special)
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


