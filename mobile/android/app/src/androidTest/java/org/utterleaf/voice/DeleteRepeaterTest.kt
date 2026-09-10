package org.utterleaf.voice

import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import android.content.Intent
import android.app.Activity
import android.widget.Button
import android.widget.FrameLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DeleteRepeaterTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private fun event(action: Int, x: Float, y: Float, time: Long): MotionEvent =
        MotionEvent.obtain(time, time, action, x, y, 0)

    private fun pointerDown(time: Long): MotionEvent {
        val first = MotionEvent.PointerProperties().apply { id = 0; toolType = MotionEvent.TOOL_TYPE_FINGER }
        val second = MotionEvent.PointerProperties().apply { id = 1; toolType = MotionEvent.TOOL_TYPE_FINGER }
        val firstPoint = MotionEvent.PointerCoords().apply { x = 20f; y = 20f; pressure = 1f; size = 1f }
        val secondPoint = MotionEvent.PointerCoords().apply { x = 30f; y = 20f; pressure = 1f; size = 1f }
        return MotionEvent.obtain(time, time, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT),
            2, arrayOf(first, second), arrayOf(firstPoint, secondPoint), 0, 0, 1f, 1f, 0, 0, 0, 0)
    }

    private fun send(view: View, event: MotionEvent) {
        try { view.dispatchTouchEvent(event) } finally { event.recycle() }
    }

    private data class Fixture(val activity: Activity, val host: FrameLayout, val button: Button)

    private fun fixture(): Fixture {
        val activity = instrumentation.startActivitySync(Intent(instrumentation.targetContext, KeyboardSettingsActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        lateinit var host: FrameLayout; lateinit var button: Button
        val laidOut = java.util.concurrent.CountDownLatch(1)
        instrumentation.runOnMainSync {
            host = FrameLayout(activity)
            button = Button(activity)
            button.addOnLayoutChangeListener { _, l, t, r, b, _, _, _, _ -> if (r > l && b > t) laidOut.countDown() }
            host.addView(button, FrameLayout.LayoutParams(120, 80))
            activity.setContentView(host)
        }
        instrumentation.waitForIdleSync()
        assertTrue(laidOut.await(5, java.util.concurrent.TimeUnit.SECONDS))
        return Fixture(activity, host, button)
    }

    @Test fun enabledTapPerformsOneClickAndDisabledKeepsNativeClick() {
        val fixture = fixture(); try { instrumentation.runOnMainSync {
            val repeater = DeleteRepeater(); val counts = mutableListOf<String>()
            val enabled = fixture.button.apply { setOnClickListener { counts += "enabled" } }
            repeater.attach(enabled, true) { counts += "erase" }
            val now = SystemClock.uptimeMillis()
            send(enabled, event(MotionEvent.ACTION_DOWN, 20f, 20f, now))
            send(enabled, event(MotionEvent.ACTION_UP, 20f, 20f, now + 20))
            val disabled = Button(fixture.activity).apply { setOnClickListener { counts += "disabled" } }
            fixture.host.addView(disabled, FrameLayout.LayoutParams(120, 80))
            repeater.attach(disabled, false) { counts += "should-not-repeat" }
            disabled.performClick() // Accessible tap path remains available with repeat disabled.
            assertEquals(listOf("enabled", "disabled"), counts)
        } } finally { instrumentation.runOnMainSync { fixture.activity.finish() } }
    }

    @Test fun holdRepeatsAtSteadyIntervalAndReleaseDoesNotClick() {
        val fixture = fixture(); try {
        val erases = mutableListOf<Long>(); val repeater = DeleteRepeater(); val target = fixture.button
        var downTime = 0L
        instrumentation.runOnMainSync {
            target.setOnClickListener { erases += -1L }
            repeater.attach(target, true) { erases += SystemClock.uptimeMillis() }
            downTime = SystemClock.uptimeMillis(); send(target, event(MotionEvent.ACTION_DOWN, 20f, 20f, downTime))
        }
        UiAwait.until("hold must erase at least twice") { erases.size >= 2 }
        instrumentation.runOnMainSync {
            val now = SystemClock.uptimeMillis(); send(target, event(MotionEvent.ACTION_UP, 20f, 20f, now))
        }
        assertTrue("hold must erase at least twice", erases.size >= 2)
        assertTrue("release must not perform a click", erases.none { it == -1L })
        assertTrue("hold must respect the system delay",
            erases.first() - downTime >= android.view.ViewConfiguration.getLongPressTimeout())
        assertTrue("repeat must not run faster than its 80 ms cadence", erases.zipWithNext().all { (a, b) -> b - a >= 80 })
        val releasedCount = erases.size
        UiAwait.remains("release must stop repeating") { erases.size == releasedCount }
        } finally { instrumentation.runOnMainSync { fixture.activity.finish() } }
    }

    @Test fun moveOutsideCancelMultitouchAndExplicitCancelStopTimers() {
        val fixture = fixture(); try {
        val erased = mutableListOf<Int>(); val repeater = DeleteRepeater(); val target = fixture.button
        instrumentation.runOnMainSync {
            repeater.attach(target, true) { erased += 1 }
            val now = SystemClock.uptimeMillis(); send(target, event(MotionEvent.ACTION_DOWN, 20f, 20f, now))
            send(target, event(MotionEvent.ACTION_MOVE, 200f, 20f, now + 20))
            send(target, event(MotionEvent.ACTION_UP, 200f, 20f, now + 40))
        }
        UiAwait.remains("Cancelled delete must not fire") { erased.isEmpty() }
        instrumentation.runOnMainSync {
            val now = SystemClock.uptimeMillis(); send(target, event(MotionEvent.ACTION_DOWN, 20f, 20f, now))
            send(target, pointerDown(now + 20))
            send(target, event(MotionEvent.ACTION_UP, 20f, 20f, now + 40))
        }
        UiAwait.remains("Cancelled delete must not fire") { erased.isEmpty() }
        instrumentation.runOnMainSync { repeater.cancel() }
        UiAwait.remains("Explicit cancellation must stop callbacks") { erased.isEmpty() }
        } finally { instrumentation.runOnMainSync { fixture.activity.finish() } }
    }

    @Test fun staleCancelPreventsLateCallbacksAfterReplacement() {
        val fixture = fixture(); try {
        val erased = mutableListOf<Int>(); val repeater = DeleteRepeater(); val old = fixture.button
        instrumentation.runOnMainSync {
            repeater.attach(old, true) { erased += 1 }
            send(old, event(MotionEvent.ACTION_DOWN, 20f, 20f, SystemClock.uptimeMillis()))
            repeater.cancel()
        }
        UiAwait.remains("Cancelled delete must not fire") { erased.isEmpty() }
        instrumentation.runOnMainSync {
            send(old, event(MotionEvent.ACTION_DOWN, 20f, 20f, SystemClock.uptimeMillis()))
        }
        UiAwait.remains("cancelled button must remain invalid") { erased.isEmpty() }
        } finally { instrumentation.runOnMainSync { fixture.activity.finish() } }
    }
}
