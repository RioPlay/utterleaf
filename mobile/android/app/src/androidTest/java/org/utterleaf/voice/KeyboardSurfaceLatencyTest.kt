package org.utterleaf.voice

import android.content.Intent
import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/** Ordinary key dispatch must not run the modifier state update path. */
@RunWith(AndroidJUnit4::class)
class KeyboardSurfaceLatencyTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    @Test fun ordinaryTouchDoesNotInvokeModifierResetCallback() {
        val activity = instrumentation.startActivitySync(
            Intent(instrumentation.targetContext, KeyboardTestActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
        var modifierUpdates = 0
        var clicks = 0
        try {
            instrumentation.runOnMainSync {
                val surface = KeyboardSurface(activity)
                surface.modifiers.bind(null, null) { _, _ -> modifierUpdates++ }
                surface.addView(Button(activity).apply {
                    contentDescription = "letter a"
                    setOnClickListener { clicks++ }
                }, FrameLayout.LayoutParams(200, 100))
                activity.setContentView(surface)
                surface.measure(
                    View.MeasureSpec.makeMeasureSpec(200, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(100, View.MeasureSpec.EXACTLY),
                )
                surface.layout(0, 0, 200, 100)
                val now = SystemClock.uptimeMillis()
                val down = MotionEvent.obtain(now, now, MotionEvent.ACTION_DOWN, 100f, 50f, 0)
                val up = MotionEvent.obtain(now, now + 10, MotionEvent.ACTION_UP, 100f, 50f, 0)
                try {
                    surface.dispatchTouchEvent(down)
                    surface.dispatchTouchEvent(up)
                } finally {
                    down.recycle()
                    up.recycle()
                }
            }
            instrumentation.waitForIdleSync()
            assertEquals(0, modifierUpdates)
            assertEquals(1, clicks)
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
            instrumentation.waitForIdleSync()
        }
    }
}
