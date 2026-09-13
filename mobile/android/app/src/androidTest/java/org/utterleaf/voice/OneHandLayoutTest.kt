package org.utterleaf.voice

import android.app.Activity
import android.content.Intent
import android.graphics.Rect
import android.os.SystemClock
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class OneHandLayoutTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private fun buttons(view: View): List<Button> = when (view) {
        is Button -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
        else -> emptyList()
    }

    private fun panel(options: KeyboardOptions, typed: MutableList<String> = mutableListOf(),
        erased: MutableList<Unit> = mutableListOf(),
        terminal: MutableList<List<Boolean>> = mutableListOf()): TypingPanel =
        TypingPanel(instrumentation.targetContext, options,
            { typed.add(it); true }, { erased.add(Unit) }, {}, {}, {}, {}, {},
            terminalKey = { _, ctrl, alt, shift -> terminal.add(listOf(ctrl, alt, shift)); true })

    private fun layout(panel: TypingPanel, widthDp: Int) {
        val width = Ui.dp(panel.view.context, widthDp)
        panel.view.measure(
            View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED),
        )
        panel.view.layout(0, 0, width, panel.view.measuredHeight)
    }

    private fun assertColumn(panel: TypingPanel, widthDp: Int, alignment: KeyboardAlignment) {
        layout(panel, widthDp)
        val root = panel.view
        val content = root.getChildAt(0)
        val available = Ui.dp(root.context, widthDp)
        val minimum = Ui.dp(root.context, 320)
        val maximum = Ui.dp(root.context, 360)
        val expected = if (alignment == KeyboardAlignment.FULL || available <= minimum) available
            else ((available.toLong() * 82L) / 100L).toInt().coerceIn(minimum, minOf(maximum, available))
        assertEquals(expected, content.width)
        assertEquals(if (alignment == KeyboardAlignment.RIGHT && available > minimum) available - expected else 0,
            content.left)
        buttons(root).filter { it.visibility == View.VISIBLE }.forEach { key ->
            val bounds = Rect(0, 0, key.width, key.height)
            root.offsetDescendantRectToMyCoords(key, bounds)
            assertTrue("${key.contentDescription} starts outside the aligned column", bounds.left >= content.left)
            assertTrue("${key.contentDescription} ends outside the aligned column", bounds.right <= content.right)
            assertTrue("${key.contentDescription} has no usable bounds", bounds.width() > 0 && bounds.height() > 0)
        }
    }

    @Test fun widthsClampAndNarrowDisplaysFallBackToFull() {
        instrumentation.runOnMainSync {
            for (alignment in KeyboardAlignment.entries) {
                for (width in listOf(300, 400, 600)) {
                    val panel = panel(KeyboardOptions(alignment = alignment))
                    panel.reset(false, false, "Enter")
                    assertColumn(panel, width, alignment)
                }
            }
        }
    }

    @Test fun everyLayerAndVisualOptionStaysInsideTheSameColumn() {
        instrumentation.runOnMainSync {
            for (large in listOf(false, true)) for (light in listOf(false, true)) {
                val panel = panel(KeyboardOptions(alignment = KeyboardAlignment.RIGHT,
                    numberRow = true, terminal = true, large = large, light = light))
                panel.reset(true, false, "Send")
                assertColumn(panel, 600, KeyboardAlignment.RIGHT)

                fun key(description: String) = buttons(panel.view).single { it.contentDescription == description }
                key("Switch letters and symbols").performClick()
                assertColumn(panel, 600, KeyboardAlignment.RIGHT)
                key("Switch letters and symbols").performClick()
                key("Function keys").performClick()
                assertColumn(panel, 600, KeyboardAlignment.RIGHT)
                key("Return to letters").performClick()
                key("Keyboard tools").performClick()
                assertColumn(panel, 600, KeyboardAlignment.RIGHT)
                assertTrue(key("Right hand layout").isSelected)
                key("Edit actions").performClick()
                assertColumn(panel, 600, KeyboardAlignment.RIGHT)
                assertTrue(buttons(panel.view).any { it.contentDescription == "Return to typing" })
            }
        }
    }

    private data class Fixture(val activity: Activity, val panel: TypingPanel,
        val typed: MutableList<String>, val erased: MutableList<Unit>,
        val terminal: MutableList<List<Boolean>>, val host: FrameLayout)

    private fun attachedFixture(): Fixture {
        val activity = instrumentation.startActivitySync(Intent(instrumentation.targetContext,
            KeyboardSettingsActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        lateinit var result: Fixture
        val laidOut = CountDownLatch(1)
        instrumentation.runOnMainSync {
            val typed = mutableListOf<String>(); val erased = mutableListOf<Unit>()
            val terminal = mutableListOf<List<Boolean>>()
            val panel = panel(KeyboardOptions(terminal = true, holdDelayMs = 250), typed, erased, terminal)
            panel.reset(false, false, "Enter")
            panel.view.addOnLayoutChangeListener { _, left, top, right, bottom, _, _, _, _ ->
                if (right > left && bottom > top) laidOut.countDown()
            }
            val host = FrameLayout(activity).apply {
                addView(panel.view, FrameLayout.LayoutParams(-1, -2))
            }
            activity.setContentView(FrameLayout(activity).apply {
                addView(host, FrameLayout.LayoutParams(Ui.dp(activity, 360), -2))
            })
            result = Fixture(activity, panel, typed, erased, terminal, host)
        }
        assertTrue("Keyboard did not lay out", laidOut.await(5, TimeUnit.SECONDS))
        instrumentation.waitForIdleSync()
        return result
    }

    private fun send(button: Button, action: Int, downTime: Long) {
        val event = MotionEvent.obtain(downTime, SystemClock.uptimeMillis(), action,
            button.width / 2f, button.height / 2f, 0)
        try { button.dispatchTouchEvent(event) } finally { event.recycle() }
    }

    private data class Point(val id: Int, val x: Float, val y: Float)

    private fun point(panel: TypingPanel, description: String, id: Int): Point {
        val key = buttons(panel.view).single { it.contentDescription == description }
        assertTrue("$description was not laid out", key.width > 0 && key.height > 0)
        val root = IntArray(2); val position = IntArray(2)
        panel.view.getLocationOnScreen(root); key.getLocationOnScreen(position)
        return Point(id, position[0] - root[0] + key.width / 2f,
            position[1] - root[1] + key.height / 2f)
    }

    private fun sendRoot(panel: TypingPanel, down: Long, action: Int, points: List<Point>) {
        val properties = Array(points.size) { index -> MotionEvent.PointerProperties().apply {
            id = points[index].id; toolType = MotionEvent.TOOL_TYPE_FINGER
        } }
        val coordinates = Array(points.size) { index -> MotionEvent.PointerCoords().apply {
            x = points[index].x; y = points[index].y; pressure = 1f; size = 1f
        } }
        val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, points.size,
            properties, coordinates, 0, 0, 1f, 1f, 0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0)
        try { panel.view.dispatchTouchEvent(event) } finally { event.recycle() }
    }

    private fun resize(f: Fixture, widthDp: Int) {
        val width = Ui.dp(f.activity, widthDp)
        val params = f.host.layoutParams as FrameLayout.LayoutParams
        params.width = width
        f.host.layoutParams = params
        f.host.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
        f.host.layout(0, 0, width, f.host.measuredHeight)
    }

    @Test fun alignmentChangeInvalidatesTouchHoldRepeatAndModifiers() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        val f = attachedFixture()
        try {
            instrumentation.runOnMainSync {
                fun key(description: String) = buttons(f.panel.view).single { it.contentDescription == description }
                key("Keyboard tools").performClick()
            }
            instrumentation.waitForIdleSync()

            instrumentation.runOnMainSync {
                fun key(description: String) = buttons(f.panel.view).single { it.contentDescription == description }
                val q = key("q"); val qDown = SystemClock.uptimeMillis()
                assertTrue(q.width > 0 && q.height > 0)
                send(q, MotionEvent.ACTION_DOWN, qDown)
                key("Right hand layout").performClick()
                send(q, MotionEvent.ACTION_UP, qDown)
            }
            instrumentation.waitForIdleSync()

            instrumentation.runOnMainSync {
                fun key(description: String) = buttons(f.panel.view).single { it.contentDescription == description }
                val e = key("e"); val eDown = SystemClock.uptimeMillis()
                assertTrue(e.width > 0 && e.height > 0)
                send(e, MotionEvent.ACTION_DOWN, eDown)
                key("Left hand layout").performClick()
                send(e, MotionEvent.ACTION_UP, eDown)
            }
            instrumentation.waitForIdleSync()

            instrumentation.runOnMainSync {
                val qPoint = point(f.panel, "q", 2); val wPoint = point(f.panel, "w", 3)
                assertTrue(qPoint.x != wPoint.x || qPoint.y != wPoint.y)
                val rolloverDown = SystemClock.uptimeMillis()
                sendRoot(f.panel, rolloverDown, MotionEvent.ACTION_DOWN, listOf(qPoint))
                sendRoot(f.panel, rolloverDown,
                    MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                    listOf(qPoint, wPoint))
                sendRoot(f.panel, rolloverDown,
                    MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                    listOf(qPoint, wPoint))
                assertTrue("The first physical release was not withheld by rollover", f.typed.isEmpty())
                resize(f, 340)
                sendRoot(f.panel, rolloverDown, MotionEvent.ACTION_UP, listOf(qPoint))
            }
            instrumentation.waitForIdleSync()

            instrumentation.runOnMainSync {
                fun key(description: String) = buttons(f.panel.view).single { it.contentDescription == description }
                val delete = key("Delete"); val deleteDown = SystemClock.uptimeMillis()
                assertTrue(delete.width > 0 && delete.height > 0)
                send(delete, MotionEvent.ACTION_DOWN, deleteDown)
            }
            Thread.sleep(android.view.ViewConfiguration.getLongPressTimeout().toLong() + 120)
            instrumentation.waitForIdleSync()
            val afterFirstRepeat = f.erased.size
            assertTrue("Held delete did not begin repeating", afterFirstRepeat > 0)
            instrumentation.runOnMainSync { resize(f, 350) }
            val afterResize = f.erased.size
            Thread.sleep(250)
            instrumentation.waitForIdleSync()
            assertEquals("Delete repeated after geometry changed", afterResize, f.erased.size)

            instrumentation.runOnMainSync {
                fun key(description: String) = buttons(f.panel.view).single { it.contentDescription == description }
                key("Control off").performClick()
                assertTrue(key("Control on").isSelected)
                key("Right hand layout").performClick()
                key("Tab").performClick()
            }
            assertTrue(f.typed.isEmpty())
            assertFalse((0 until f.panel.view.childCount).any { f.panel.view.getChildAt(it) is AlternateStrip })
            assertEquals(listOf(listOf(false, false, false)), f.terminal)
        } finally {
            instrumentation.runOnMainSync { f.activity.finish() }
            original.save(context)
            instrumentation.waitForIdleSync()
        }
    }
}
