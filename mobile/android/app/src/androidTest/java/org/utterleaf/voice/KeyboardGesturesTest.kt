package org.utterleaf.voice

import android.content.Intent
import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class KeyboardGesturesTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private fun <T> main(block: () -> T): T {
        if (android.os.Looper.myLooper() == android.os.Looper.getMainLooper()) return block()
        val result = AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }
    private fun buttons(view: View): List<Button> = when (view) {
        is Button -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
        else -> emptyList()
    }
    private inner class Fixture(val panel: TypingPanel, val inserted: MutableList<String>,
                                val moves: MutableList<Boolean>, val host: FrameLayout) {
        private var downTime = 0L
        fun key(label: String) = main { buttons(panel.view).single { it.contentDescription == label } }
        fun strip() = main { (0 until panel.view.childCount).map { panel.view.getChildAt(it) }.filterIsInstance<AlternateStrip>().single() }
        fun hasStrip() = main { (0 until panel.view.childCount).any { panel.view.getChildAt(it) is AlternateStrip } }
        fun dp(value: Int) = Ui.dp(host.context, value).toFloat()
        fun send(button: Button, action: Int, dx: Float = 0f, dy: Float = 0f) {
            main {
                val origin = IntArray(2); button.getLocationOnScreen(origin)
                dispatch(button, action, origin[0] + button.width / 2f + dx, origin[1] + button.height / 2f + dy)
            }
        }
        private fun dispatch(button: Button, action: Int, rawX: Float, rawY: Float) {
            val now = SystemClock.uptimeMillis()
            if (action == MotionEvent.ACTION_DOWN) downTime = now
            val origin = IntArray(2); button.getLocationOnScreen(origin)
            val event = MotionEvent.obtain(downTime, now, action, rawX, rawY, 0)
            event.offsetLocation(-origin[0].toFloat(), -origin[1].toFloat())
            try { button.dispatchTouchEvent(event) } finally { event.recycle() }
        }
        fun atCell(button: Button, index: Int, action: Int) {
            val overlay = strip()
            main {
                val origin = IntArray(2); panel.view.getLocationOnScreen(origin)
                val cell = overlay.cells[index]
                dispatch(button, action, origin[0] + cell.centerX(), origin[1] + cell.centerY())
            }
        }
        fun hold(button: Button) {
            send(button, MotionEvent.ACTION_DOWN)
            Thread.sleep(ViewConfiguration.getLongPressTimeout().toLong() + 100)
            instrumentation.waitForIdleSync()
            assertTrue("Attached button did not open hold choices", hasStrip())
        }
        fun multiTouch(button: Button) = main {
            val properties = Array(2) { index -> MotionEvent.PointerProperties().apply { id = index; toolType = MotionEvent.TOOL_TYPE_FINGER } }
            val coordinates = Array(2) { index -> MotionEvent.PointerCoords().apply { x = button.width / 2f + index * 2; y = button.height / 2f; pressure = 1f; size = 1f } }
            val event = MotionEvent.obtain(downTime, SystemClock.uptimeMillis(),
                MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                2, properties, coordinates, 0, 0, 1f, 1f, 0, 0, android.view.InputDevice.SOURCE_TOUCHSCREEN, 0)
            try { button.dispatchTouchEvent(event) } finally { event.recycle() }
        }
        fun chord(action: Int, shift: Button, space: Button? = null, dx: Float = 0f) = main {
            val keys = if (space == null) listOf(shift) else listOf(shift, space)
            val origin = IntArray(2); panel.view.getLocationOnScreen(origin)
            val properties = Array(keys.size) { index -> MotionEvent.PointerProperties().apply {
                id = index; toolType = MotionEvent.TOOL_TYPE_FINGER
            } }
            val coordinates = Array(keys.size) { index -> MotionEvent.PointerCoords().apply {
                val position = IntArray(2); keys[index].getLocationOnScreen(position)
                x = position[0] - origin[0] + keys[index].width / 2f + if (index == 1) dx else 0f
                y = position[1] - origin[1] + keys[index].height / 2f
                pressure = 1f; size = 1f
            } }
            val now = SystemClock.uptimeMillis()
            if (action == MotionEvent.ACTION_DOWN) downTime = now
            val event = MotionEvent.obtain(downTime, now, action, keys.size, properties, coordinates,
                0, 0, 1f, 1f, 0, 0, android.view.InputDevice.SOURCE_TOUCHSCREEN, 0)
            try { panel.view.dispatchTouchEvent(event) } finally { event.recycle() }
        }
    }
    private fun withPanel(options: KeyboardOptions = KeyboardOptions(), accept: Boolean = true, test: (Fixture) -> Unit) {
        val activity = instrumentation.startActivitySync(Intent(instrumentation.targetContext, KeyboardSettingsActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            val laidOut = java.util.concurrent.CountDownLatch(1)
            val fixture = main {
                val inserted = mutableListOf<String>(); val moves = mutableListOf<Boolean>()
                val panel = TypingPanel(activity, options, { inserted.add(it); accept }, {}, {}, { moves.add(it) }, {}, {}, {},
                    terminalKey = { code, ctrl, alt, shift ->
                        assertTrue(shift); assertFalse(ctrl); assertFalse(alt)
                        moves.add(code == android.view.KeyEvent.KEYCODE_DPAD_LEFT); true
                    })
                panel.reset(false, false, "Enter")
                panel.view.addOnLayoutChangeListener { _, left, top, right, bottom, _, _, _, _ ->
                    if (right > left && bottom > top) laidOut.countDown()
                }
                val host = FrameLayout(activity)
                host.addView(panel.view, FrameLayout.LayoutParams(Ui.dp(activity, 320), -2))
                activity.setContentView(host)
                Fixture(panel, inserted, moves, host)
            }
            assertTrue("Keyboard did not lay out", laidOut.await(5, java.util.concurrent.TimeUnit.SECONDS))
            instrumentation.waitForIdleSync()
            assertTrue(main { fixture.panel.view.isAttachedToWindow && fixture.panel.view.width > 0 })
            test(fixture)
        } finally {
            main { activity.finish() }
            instrumentation.waitForIdleSync()
        }
    }

    @Test fun spaceTapAndDistanceBasedDragReversal() = withPanel { f ->
        val key = f.key("Space")
        f.send(key, MotionEvent.ACTION_DOWN); f.send(key, MotionEvent.ACTION_UP)
        f.send(key, MotionEvent.ACTION_DOWN)
        f.send(key, MotionEvent.ACTION_MOVE, f.dp(48))
        f.send(key, MotionEvent.ACTION_MOVE, f.dp(48)) // Stationary events do not move the cursor.
        f.send(key, MotionEvent.ACTION_MOVE, f.dp(16)) // Reverse without crossing the starting point.
        f.send(key, MotionEvent.ACTION_UP, f.dp(16))
        assertEquals(listOf(" "), f.inserted)
        assertEquals(listOf(false, false, false, true, true), f.moves)
    }

    @Test fun spaceCancellationMultitouchAndStaleButtonsNeverInsert() = withPanel { f ->
        val key = f.key("Space")
        f.send(key, MotionEvent.ACTION_DOWN)
        f.send(key, MotionEvent.ACTION_MOVE, dy = f.dp(40))
        f.send(key, MotionEvent.ACTION_MOVE, dx = f.dp(48))
        f.send(key, MotionEvent.ACTION_UP)
        f.send(key, MotionEvent.ACTION_DOWN); f.multiTouch(key)
        f.send(key, MotionEvent.ACTION_MOVE, f.dp(48)); f.send(key, MotionEvent.ACTION_UP)
        f.send(key, MotionEvent.ACTION_DOWN); f.send(key, MotionEvent.ACTION_CANCEL); f.send(key, MotionEvent.ACTION_UP)
        main { f.panel.reset(false, false, "Enter") }
        f.send(key, MotionEvent.ACTION_DOWN); f.send(key, MotionEvent.ACTION_UP)
        assertTrue(f.inserted.isEmpty()); assertTrue(f.moves.isEmpty())
    }

    @Test fun letterDriftWithinKeyAndHoldReleaseChooseExactlyOnce() = withPanel { f ->
        val key = f.key("a")
        val drift = ViewConfiguration.get(key.context).scaledTouchSlop + 1f
        f.send(key, MotionEvent.ACTION_DOWN)
        f.send(key, MotionEvent.ACTION_MOVE, drift)
        f.send(key, MotionEvent.ACTION_UP, drift)
        val height = main { f.panel.view.height }
        f.hold(key)
        val expected = AlternateCharacters.choices('a', false)[main { f.strip().selectedIndex }]
        assertEquals(height, main { f.panel.view.height })
        f.send(key, MotionEvent.ACTION_UP)
        assertEquals(listOf("a", expected), f.inserted)
        assertFalse(f.hasStrip())
    }

    @Test fun uppercaseSlideReleaseAndEdgeGeometry() = withPanel { f ->
        main { f.key("Shift off").performClick() }
        val upper = f.key("E")
        f.hold(upper); f.atCell(upper, 0, MotionEvent.ACTION_MOVE); f.atCell(upper, 0, MotionEvent.ACTION_UP)
        assertEquals(listOf("É"), f.inserted)
        for (letter in listOf("a", "p", "l", "z")) {
            val key = f.key(letter); f.hold(key)
            val overlay = f.strip()
            main { overlay.cells.forEach { assertTrue(it.left >= 0 && it.right <= f.panel.view.width && it.top >= 0 && it.bottom <= f.panel.view.height) } }
            f.atCell(key, 0, MotionEvent.ACTION_MOVE); f.atCell(key, 0, MotionEvent.ACTION_UP)
            assertFalse(f.hasStrip())
        }
        assertEquals(5, f.inserted.size)
    }

    @Test fun holdSlideAwayMultitouchResetAndDetachCancel() = withPanel { f ->
        var key = f.key("a"); f.hold(key)
        f.send(key, MotionEvent.ACTION_MOVE, f.dp(-500), f.dp(-500)); f.send(key, MotionEvent.ACTION_UP, f.dp(-500), f.dp(-500))
        f.hold(key); f.multiTouch(key); f.send(key, MotionEvent.ACTION_UP)
        f.hold(key); main { f.panel.reset(false, false, "Enter") }; f.send(key, MotionEvent.ACTION_UP)
        key = f.key("a"); f.send(key, MotionEvent.ACTION_DOWN)
        main { f.panel.reset(false, false, "Enter") }
        Thread.sleep(ViewConfiguration.getLongPressTimeout().toLong() + 100)
        assertFalse(f.hasStrip())
        key = f.key("a"); f.hold(key); main { f.host.removeView(f.panel.view) }; f.send(key, MotionEvent.ACTION_UP)
        assertTrue(f.inserted.isEmpty()); assertFalse(f.hasStrip())
    }

    @Test fun rejectedAlternateRemovesOverlayWithoutFallback() = withPanel(accept = false) { f ->
        val key = f.key("e"); f.hold(key)
        f.atCell(key, 0, MotionEvent.ACTION_UP)
        assertEquals(listOf("é"), f.inserted)
        assertFalse(f.hasStrip())
    }

    @Test fun periodTapAndPunctuationHoldReleaseStayDistinct() = withPanel { f ->
        val period = f.key(".")
        f.send(period, MotionEvent.ACTION_DOWN); f.send(period, MotionEvent.ACTION_UP)
        f.hold(period); f.atCell(period, 1, MotionEvent.ACTION_MOVE); f.atCell(period, 1, MotionEvent.ACTION_UP)
        assertEquals(listOf(".", "?"), f.inserted)
        f.hold(period)
        f.send(period, MotionEvent.ACTION_UP, f.dp(-500), f.dp(-500))
        assertEquals(listOf(".", "?"), f.inserted)
    }

    @Test fun shiftSpaceChordSelectsAndReversesWithoutTypingOrLatchingShift() = withPanel { f ->
        val shift = f.key("Shift off"); val space = f.key("Space")
        f.chord(MotionEvent.ACTION_DOWN, shift)
        f.chord(MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), shift, space)
        f.chord(MotionEvent.ACTION_MOVE, shift, space, f.dp(-48))
        f.chord(MotionEvent.ACTION_MOVE, shift, space, f.dp(-16))
        f.chord(MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), shift, space, f.dp(-16))
        f.chord(MotionEvent.ACTION_UP, shift)
        assertEquals(listOf(true, true, true, false, false), f.moves)
        assertTrue(f.inserted.isEmpty()); assertEquals("Shift off", shift.contentDescription)
        main { f.key("a").performClick() }; assertEquals(listOf("a"), f.inserted)
    }

    @Test fun chordResetAndFingerReleaseStopFurtherSelection() = withPanel { f ->
        val shift = f.key("Shift off"); val space = f.key("Space")
        f.chord(MotionEvent.ACTION_DOWN, shift)
        f.chord(MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), shift, space)
        f.chord(MotionEvent.ACTION_POINTER_UP, shift, space) // Shift lifted first.
        f.chord(MotionEvent.ACTION_MOVE, shift, space, f.dp(-48))
        f.chord(MotionEvent.ACTION_CANCEL, shift)
        f.chord(MotionEvent.ACTION_DOWN, shift)
        f.chord(MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), shift, space)
        main { f.panel.reset(false, false, "Enter") }
        f.chord(MotionEvent.ACTION_MOVE, shift, space, f.dp(-48))
        f.chord(MotionEvent.ACTION_UP, shift)
        assertTrue(f.moves.isEmpty()); assertTrue(f.inserted.isEmpty())
    }
}
