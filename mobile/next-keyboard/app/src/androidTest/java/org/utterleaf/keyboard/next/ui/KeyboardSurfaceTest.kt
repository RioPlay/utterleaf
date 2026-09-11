package org.utterleaf.keyboard.next.ui

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import android.view.MotionEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.ceil

@RunWith(AndroidJUnit4::class)
class KeyboardSurfaceTest {
    @Test fun surfaceExposesStableKeyBounds() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val surface = KeyboardSurface(context)
        val width = (320f * context.resources.displayMetrics.density).toInt()
        val height = ceil(236f * context.resources.displayMetrics.density).toInt()
        surface.measure(width, height)
        surface.layout(0, 0, width, height)
        assertNotNull(surface.keyBounds("q"))
        assertNotNull(surface.keyBounds("space"))
        assertNotNull(surface.keyBounds("⌫"))
    }
    @Test fun outsideReleaseDoesNotCommitAndVirtualNodesExist() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val emitted = mutableListOf<KeyAction>()
        val surface = KeyboardSurface(context) { emitted += it }
        val width = (320f * context.resources.displayMetrics.density).toInt()
        val height = ceil(236f * context.resources.displayMetrics.density).toInt()
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            surface.measure(width, height)
            surface.layout(0, 0, width, height)
            val q = surface.keyBounds("q")!!
            val down = MotionEvent.obtain(0, 0, MotionEvent.ACTION_DOWN, q.left + 2f, q.top + 2f, 0)
            val up = MotionEvent.obtain(0, 10, MotionEvent.ACTION_UP, width - 1f, height - 1f, 0)
            surface.dispatchTouchEvent(down); surface.dispatchTouchEvent(up)
            down.recycle(); up.recycle()
        }
        assertEquals(0, emitted.size)
        assertNotNull(surface.accessibilityNodeProvider)
    }
}
