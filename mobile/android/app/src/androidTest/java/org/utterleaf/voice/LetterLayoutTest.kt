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
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class LetterLayoutTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private fun buttons(view: View): List<Button> = when (view) {
        is Button -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
        else -> emptyList()
    }

    private fun panel(options: KeyboardOptions, typed: MutableList<String> = mutableListOf(),
        erased: MutableList<Unit> = mutableListOf(), modified: MutableList<Triple<String, Boolean, Boolean>> = mutableListOf(),
        moved: MutableList<Boolean> = mutableListOf()): TypingPanel =
        TypingPanel(instrumentation.targetContext, options,
            { typed.add(it); true }, { erased.add(Unit) }, {}, { moved.add(it) }, {}, {}, {},
            terminalKey = { _, _, _, _ -> true },
            modifiedCommit = { value, ctrl, alt -> modified.add(Triple(value, ctrl, alt)); true })

    private fun layout(panel: TypingPanel, widthDp: Int) {
        val width = Ui.dp(panel.view.context, widthDp)
        panel.view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED))
        panel.view.layout(0, 0, width, panel.view.measuredHeight)
    }

    private fun key(panel: TypingPanel, description: String) =
        buttons(panel.view).single { it.contentDescription == description }

    @Test fun everyLayoutFitsFullAndOneHandColumnsAtNarrowAndWideWidths() {
        instrumentation.runOnMainSync {
            for (letterLayout in LetterLayout.entries) for (alignment in KeyboardAlignment.entries) {
                for (width in listOf(300, 600)) {
                    val panel = panel(KeyboardOptions(letterLayout = letterLayout, alignment = alignment))
                    panel.reset(false, false, "Enter")
                    layout(panel, width)
                    val root = panel.view
                    val content = root.getChildAt(0)
                    val visible = buttons(root).filter { it.visibility == View.VISIBLE }
                    val letters = visible.mapNotNull { it.contentDescription?.toString() }
                        .filter { it.length == 1 && it[0] in 'a'..'z' }.map { it.single() }
                    assertEquals("$letterLayout $alignment $width", letterLayout.rows.joinToString("").toSet(), letters.toSet())
                    assertEquals(26, letters.size)
                    val bounds = visible.map { button ->
                        Rect(0, 0, button.width, button.height).also { root.offsetDescendantRectToMyCoords(button, it) }
                    }
                    bounds.forEach { rect ->
                        assertTrue("empty key in $letterLayout/$alignment/$width", rect.width() > 0 && rect.height() > 0)
                        assertTrue(rect.left >= content.left && rect.right <= content.right)
                    }
                    bounds.indices.forEach { first ->
                        for (second in first + 1 until bounds.size) {
                            assertFalse("overlap in $letterLayout/$alignment/$width", Rect.intersects(bounds[first], bounds[second]))
                        }
                    }
                }
            }
        }
    }

    @Test fun visibleLettersDrivePlainCaseAndShortcutDispatch() {
        val typed = mutableListOf<String>()
        val modified = mutableListOf<Triple<String, Boolean, Boolean>>()
        instrumentation.runOnMainSync {
            val panel = panel(KeyboardOptions(terminal = true, letterLayout = LetterLayout.QWERTZ), typed,
                modified = modified)
            panel.reset(false, false, "Enter")
            key(panel, "z").performClick()
            key(panel, "Shift off").performClick(); key(panel, "Y").performClick()
            key(panel, "Keyboard tools").performClick(); key(panel, "Caps lock off").performClick()
            key(panel, "Z").performClick()
            key(panel, "Control off").performClick(); key(panel, "Y").performClick()
            assertEquals(listOf("z", "Y", "Z"), typed)
            assertEquals(listOf(Triple("Y", true, false)), modified)
        }
    }

    @Test fun hintsAndBothAlternateRoutesUseTheSelectedPosition() {
        val typed = mutableListOf<String>()
        lateinit var activity: Activity
        lateinit var panel: TypingPanel
        val ready = CountDownLatch(1)
        activity = instrumentation.startActivitySync(Intent(instrumentation.targetContext,
            KeyboardSettingsActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            instrumentation.runOnMainSync {
                panel = panel(KeyboardOptions(letterLayout = LetterLayout.AZERTY, holdDelayMs = 250), typed)
                panel.reset(false, false, "Enter")
                panel.view.addOnLayoutChangeListener { _, l, t, r, b, _, _, _, _ ->
                    if (r > l && b > t) ready.countDown()
                }
                activity.setContentView(FrameLayout(activity).apply { addView(panel.view) })
            }
            assertTrue(ready.await(5, TimeUnit.SECONDS)); instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                val expected = mapOf('a' to "1", 'q' to "@", 'w' to "*", 'z' to "2", 'm' to "/")
                expected.forEach { (letter, hint) ->
                    val button = buttons(panel.view).single { it.tag == letter } as HintedKey
                    assertEquals(hint, button.secondaryHint)
                }
                key(panel, "Keyboard tools").performClick()
                key(panel, "Accents and alternate characters").performClick()
                key(panel, "q").performClick()
                val alternateButtons = buttons(panel.view)
                assertEquals(1, alternateButtons.count { it.text.toString() == "@" })
                assertFalse(alternateButtons.any { it.text.toString() == "1" })
                key(panel, "Cancel alternate characters").performClick()
            }
            instrumentation.waitForIdleSync()

            var holdDown = 0L
            instrumentation.runOnMainSync {
                val heldKey = key(panel, "a")
                holdDown = SystemClock.uptimeMillis()
                val origin = IntArray(2); heldKey.getLocationOnScreen(origin)
                val event = MotionEvent.obtain(holdDown, holdDown, MotionEvent.ACTION_DOWN,
                    origin[0] + heldKey.width / 2f, origin[1] + heldKey.height / 2f, 0)
                event.offsetLocation(-origin[0].toFloat(), -origin[1].toFloat())
                try { assertTrue(heldKey.dispatchTouchEvent(event)) } finally { event.recycle() }
            }
            Thread.sleep(350); instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                fun strip(view: View): AlternateStrip? {
                    if (view is AlternateStrip) return view
                    if (view is ViewGroup) for (index in 0 until view.childCount) strip(view.getChildAt(index))?.let { return it }
                    return null
                }
                val heldKey = key(panel, "a")
                val alternate = strip(panel.view)
                assertNotNull(alternate)
                assertEquals("1", AlternateCharacters.choices('a', false, LetterLayout.AZERTY)[alternate!!.selectedIndex])
                val keyPosition = IntArray(2); heldKey.getLocationOnScreen(keyPosition)
                val event = MotionEvent.obtain(holdDown, SystemClock.uptimeMillis(), MotionEvent.ACTION_UP,
                    keyPosition[0] + heldKey.width / 2f, keyPosition[1] + heldKey.height / 2f, 0)
                event.offsetLocation(-keyPosition[0].toFloat(), -keyPosition[1].toFloat())
                try { heldKey.dispatchTouchEvent(event) } finally { event.recycle() }
                assertEquals(listOf("1"), typed)
            }
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            instrumentation.waitForIdleSync()
        }
    }

    private data class Point(val id: Int, val x: Float, val y: Float)

    private fun point(panel: TypingPanel, description: String, id: Int): Point {
        val button = key(panel, description)
        val root = IntArray(2); val position = IntArray(2)
        panel.view.getLocationOnScreen(root); button.getLocationOnScreen(position)
        return Point(id, position[0] - root[0] + button.width / 2f,
            position[1] - root[1] + button.height / 2f)
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

    @Test fun switchingLayoutCancelsPendingTouchRepeatSelectionAlternateAndModifiers() {
        val context = instrumentation.targetContext
        val original = KeyboardOptions.load(context)
        val typed = mutableListOf<String>(); val erased = mutableListOf<Unit>()
        val modified = mutableListOf<Triple<String, Boolean, Boolean>>(); val moved = mutableListOf<Boolean>()
        var activity: Activity? = null; lateinit var panel: TypingPanel
        try {
            activity = instrumentation.startActivitySync(Intent(context, KeyboardSettingsActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            instrumentation.runOnMainSync {
                panel = panel(KeyboardOptions(terminal = true, holdDelayMs = 250), typed, erased, modified, moved)
                panel.reset(false, false, "Enter")
                activity!!.setContentView(FrameLayout(activity!!).apply { addView(panel.view) })
            }
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                key(panel, "Keyboard tools").performClick()
            }
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                val q = point(panel, "q", 2); val w = point(panel, "w", 3)
                val down = SystemClock.uptimeMillis()
                sendRoot(panel, down, MotionEvent.ACTION_DOWN, listOf(q))
                sendRoot(panel, down, MotionEvent.ACTION_POINTER_DOWN or
                    (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(q, w))
                sendRoot(panel, down, MotionEvent.ACTION_POINTER_UP or
                    (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(q, w))
                key(panel, "QWERTZ letter layout").performClick()
                sendRoot(panel, down, MotionEvent.ACTION_UP, listOf(q))
                assertTrue(key(panel, "Keyboard tools").isSelected)
                assertTrue(key(panel, "QWERTZ letter layout").isSelected)
                assertTrue(typed.isEmpty())
            }
            instrumentation.waitForIdleSync()

            lateinit var held: Button
            var heldDown = 0L
            instrumentation.runOnMainSync {
                held = key(panel, "e"); heldDown = SystemClock.uptimeMillis()
                val event = MotionEvent.obtain(heldDown, heldDown, MotionEvent.ACTION_DOWN,
                    held.width / 2f, held.height / 2f, 0)
                try { held.dispatchTouchEvent(event) } finally { event.recycle() }
            }
            Thread.sleep(350); instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                assertTrue((0 until panel.view.childCount).any { panel.view.getChildAt(it) is AlternateStrip })
                key(panel, "AZERTY letter layout").performClick()
                val event = MotionEvent.obtain(heldDown, SystemClock.uptimeMillis(), MotionEvent.ACTION_UP,
                    held.width / 2f, held.height / 2f, 0)
                try { held.dispatchTouchEvent(event) } finally { event.recycle() }
                assertFalse((0 until panel.view.childCount).any { panel.view.getChildAt(it) is AlternateStrip })

                key(panel, "Select text").performClick()
                key(panel, "QWERTZ letter layout").performClick()
                key(panel, "Move cursor left").performClick()
                assertEquals(listOf(true), moved)

                key(panel, "Control off").performClick()
                key(panel, "AZERTY letter layout").performClick()
                key(panel, "q").performClick()
                assertEquals(listOf("q"), typed)
                assertTrue(modified.isEmpty())
            }

            instrumentation.runOnMainSync {
                val delete = key(panel, "Delete")
                val down = SystemClock.uptimeMillis()
                val event = MotionEvent.obtain(down, down, MotionEvent.ACTION_DOWN,
                    delete.width / 2f, delete.height / 2f, 0)
                try { delete.dispatchTouchEvent(event) } finally { event.recycle() }
            }
            Thread.sleep(android.view.ViewConfiguration.getLongPressTimeout().toLong() + 140)
            instrumentation.waitForIdleSync()
            assertTrue(erased.isNotEmpty())
            instrumentation.runOnMainSync { key(panel, "QWERTY letter layout").performClick() }
            val stopped = erased.size
            Thread.sleep(240); instrumentation.waitForIdleSync()
            assertEquals(stopped, erased.size)
            assertFalse((0 until panel.view.childCount).any { panel.view.getChildAt(it) is AlternateStrip })
            instrumentation.runOnMainSync { key(panel, "z").performClick() }
            assertEquals("z", typed.last())
        } finally {
            instrumentation.runOnMainSync { activity?.finish() }
            original.save(context)
            instrumentation.waitForIdleSync()
        }
    }
}
