package org.utterleaf.voice

import android.app.Activity
import android.content.Intent
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
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Dispatches through the root surface so Android's child-event splitting is never assumed. */
@RunWith(AndroidJUnit4::class)
class TypingRolloverTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private data class Point(val id: Int, val x: Float, val y: Float)
    private data class Fixture(val activity: Activity, val panel: TypingPanel, val typed: MutableList<String>)

    private fun buttons(view: View): List<Button> = when (view) {
        is Button -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
        else -> emptyList()
    }
    private fun fixture(): Fixture {
        val activity = instrumentation.startActivitySync(Intent(instrumentation.targetContext, KeyboardSettingsActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        lateinit var panel: TypingPanel
        val typed = mutableListOf<String>(); val laidOut = CountDownLatch(1)
        instrumentation.runOnMainSync {
            panel = TypingPanel(activity, KeyboardOptions(), { typed.add(it); true }, {}, {}, {}, {}, {}, {})
            panel.reset(false, false, "Enter")
            panel.view.addOnLayoutChangeListener { _, left, top, right, bottom, _, _, _, _ ->
                if (right > left && bottom > top) laidOut.countDown()
            }
            activity.setContentView(FrameLayout(activity).apply { addView(panel.view, FrameLayout.LayoutParams(Ui.dp(activity, 360), -2)) })
        }
        assertTrue("Keyboard did not lay out", laidOut.await(5, TimeUnit.SECONDS))
        instrumentation.waitForIdleSync()
        return Fixture(activity, panel, typed)
    }
    private fun point(panel: TypingPanel, label: String, id: Int): Point {
        val key = buttons(panel.view).single { it.contentDescription == label }
        val root = IntArray(2); val position = IntArray(2)
        panel.view.getLocationOnScreen(root); key.getLocationOnScreen(position)
        return Point(id, position[0] - root[0] + key.width / 2f, position[1] - root[1] + key.height / 2f)
    }
    private fun key(panel: TypingPanel, label: String) = buttons(panel.view).single { it.contentDescription == label }
    private fun send(panel: TypingPanel, down: Long, action: Int, points: List<Point>) {
        val properties = Array(points.size) { index -> MotionEvent.PointerProperties().apply { id = points[index].id; toolType = MotionEvent.TOOL_TYPE_FINGER } }
        val coordinates = Array(points.size) { index -> MotionEvent.PointerCoords().apply {
            x = points[index].x; y = points[index].y; pressure = 1f; size = 1f
        } }
        val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, points.size, properties, coordinates,
            0, 0, 1f, 1f, 0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0)
        try { panel.view.dispatchTouchEvent(event) } finally { event.recycle() }
    }
    private fun overlap(panel: TypingPanel, first: Point, second: Point, reverse: Boolean = true) {
        val down = SystemClock.uptimeMillis()
        send(panel, down, MotionEvent.ACTION_DOWN, listOf(first))
        send(panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(first, second))
        if (reverse) {
            send(panel, down, MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(first, second))
            send(panel, down, MotionEvent.ACTION_UP, listOf(first))
        } else {
            send(panel, down, MotionEvent.ACTION_POINTER_UP, listOf(first, second))
            send(panel, down, MotionEvent.ACTION_UP, listOf(second))
        }
    }

    @Test fun rootRolloverPreservesPressOrderAcrossRowsAndReverseRelease() {
        val f = fixture()
        try {
            instrumentation.runOnMainSync {
                overlap(f.panel, point(f.panel, "q", 7), point(f.panel, "a", 11))
                overlap(f.panel, point(f.panel, "w", 13), point(f.panel, "e", 17), reverse = false)
                overlap(f.panel, point(f.panel, "a", 19), point(f.panel, "a", 23))
            }
            assertEquals(listOf("q", "a", "w", "e", "a", "a"), f.typed)
        } finally { instrumentation.runOnMainSync { f.activity.finish() } }
    }

    @Test fun rootRolloverCancelsSlideOffAndInvalidatedStreams() {
        val f = fixture()
        try {
            instrumentation.runOnMainSync {
                val q = point(f.panel, "q", 1); val w = point(f.panel, "w", 2); val down = SystemClock.uptimeMillis()
                send(f.panel, down, MotionEvent.ACTION_DOWN, listOf(q))
                send(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(q, w))
                send(f.panel, down, MotionEvent.ACTION_MOVE, listOf(q.copy(x = -100f), w))
                send(f.panel, down, MotionEvent.ACTION_MOVE, listOf(q, w)) // Re-entry stays cancelled.
                send(f.panel, down, MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(q, w))
                send(f.panel, down, MotionEvent.ACTION_UP, listOf(q))
                assertEquals(listOf("w"), f.typed)

                val a = point(f.panel, "a", 3); val s = point(f.panel, "s", 4); val resetDown = SystemClock.uptimeMillis()
                send(f.panel, resetDown, MotionEvent.ACTION_DOWN, listOf(a))
                send(f.panel, resetDown, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(a, s))
                f.panel.reset(false, true, "Enter") // Mode rebuild cancels the captured stream.
                send(f.panel, resetDown, MotionEvent.ACTION_UP, listOf(a))
                assertEquals(listOf("w"), f.typed)

                f.panel.reset(false, false, "Enter")
                val z = point(f.panel, "z", 5); val x = point(f.panel, "x", 6); val detachedDown = SystemClock.uptimeMillis()
                send(f.panel, detachedDown, MotionEvent.ACTION_DOWN, listOf(z))
                send(f.panel, detachedDown, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(z, x))
                (f.panel.view.parent as ViewGroup).removeView(f.panel.view)
                send(f.panel, detachedDown, MotionEvent.ACTION_UP, listOf(z))
                assertEquals(listOf("w"), f.typed)
            }
        } finally { instrumentation.runOnMainSync { f.activity.finish() } }
    }

    @Test fun continuousTwoThumbRolloverPreservesThousandCharacters() {
        val f = fixture()
        try {
            instrumentation.runOnMainSync {
                val q = point(f.panel, "q", 0); val w = point(f.panel, "w", 1); val down = SystemClock.uptimeMillis()
                send(f.panel, down, MotionEvent.ACTION_DOWN, listOf(q))
                send(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(q, w))
                repeat(499) {
                    send(f.panel, down, MotionEvent.ACTION_POINTER_UP, listOf(q, w))
                    send(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(w, q))
                    send(f.panel, down, MotionEvent.ACTION_POINTER_UP, listOf(w, q))
                    send(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(q, w))
                }
                send(f.panel, down, MotionEvent.ACTION_POINTER_UP, listOf(q, w))
                send(f.panel, down, MotionEvent.ACTION_UP, listOf(w))
            }
            assertEquals("qw".repeat(500), f.typed.joinToString(""))
        } finally { instrumentation.runOnMainSync { f.activity.finish() } }
    }

    @Test fun holdGeometryCancelAndUnsupportedThirdFingerNeverFallBackToBaseTaps() {
        val f = fixture()
        try {
            instrumentation.runOnMainSync {
                val e = point(f.panel, "e", 0); val down = SystemClock.uptimeMillis()
                send(f.panel, down, MotionEvent.ACTION_DOWN, listOf(e))
            }
            Thread.sleep(android.view.ViewConfiguration.getLongPressTimeout().toLong() + 100)
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync {
                val e = point(f.panel, "e", 0); val q = point(f.panel, "q", 1); val down = SystemClock.uptimeMillis()
                send(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(e, q))
                send(f.panel, down, MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(e, q))
                send(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(e, q))
                send(f.panel, down, MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(e, q))
                send(f.panel, down, MotionEvent.ACTION_UP, listOf(e))
                assertEquals(emptyList<String>(), f.typed)

                val a = point(f.panel, "a", 0); val s = point(f.panel, "s", 1); val space = point(f.panel, "Space", 2); val stream = SystemClock.uptimeMillis()
                send(f.panel, stream, MotionEvent.ACTION_DOWN, listOf(a))
                send(f.panel, stream, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(a, s))
                send(f.panel, stream, MotionEvent.ACTION_POINTER_DOWN or (2 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(a, s, space))
                send(f.panel, stream, MotionEvent.ACTION_CANCEL, listOf(a, s, space))
                assertEquals(emptyList<String>(), f.typed)

                val geometryQ = point(f.panel, "q", 0); val w = point(f.panel, "w", 1); val geometry = SystemClock.uptimeMillis()
                send(f.panel, geometry, MotionEvent.ACTION_DOWN, listOf(geometryQ))
                send(f.panel, geometry, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(geometryQ, w))
                key(f.panel, "q").layout(1, 1, key(f.panel, "q").width + 1, key(f.panel, "q").height + 1)
                send(f.panel, geometry, MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(geometryQ, w))
                send(f.panel, geometry, MotionEvent.ACTION_UP, listOf(geometryQ))
                assertEquals(listOf("w"), f.typed)

                assertEquals(listOf("w"), f.typed)
            }
        } finally { instrumentation.runOnMainSync { f.activity.finish() } }
    }

    @Test fun numberAndPunctuationRolloverUsesTheSameRootRoute() {
        val f = fixture()
        try {
            instrumentation.runOnMainSync { f.panel.reset(false, true, "Enter") }
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync { overlap(f.panel, point(f.panel, "1", 0), point(f.panel, ".", 1)) }
            assertEquals(listOf("1", "."), f.typed)
        } finally { instrumentation.runOnMainSync { f.activity.finish() } }
    }

    @Test fun heldPrefixQueueIsBoundedAndFailsClosed() {
        val f = fixture()
        try {
            instrumentation.runOnMainSync {
                val a = point(f.panel, "a", 0); val s = point(f.panel, "s", 1); val down = SystemClock.uptimeMillis()
                send(f.panel, down, MotionEvent.ACTION_DOWN, listOf(a))
                send(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(a, s))
                send(f.panel, down, MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(a, s))
                repeat(31) {
                    send(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(a, s))
                    send(f.panel, down, MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(a, s))
                }
                send(f.panel, down, MotionEvent.ACTION_UP, listOf(a))
            }
            assertEquals(emptyList<String>(), f.typed)
        } finally { instrumentation.runOnMainSync { f.activity.finish() } }
    }
}
