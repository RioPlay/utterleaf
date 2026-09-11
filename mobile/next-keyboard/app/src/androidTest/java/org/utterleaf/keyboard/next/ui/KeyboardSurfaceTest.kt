package org.utterleaf.keyboard.next.ui

import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityNodeInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.utterleaf.keyboard.next.R
import kotlin.math.ceil

@RunWith(AndroidJUnit4::class)
class KeyboardSurfaceTest {
    @Test fun surfaceExposesStableKeyBounds() = onMain { context ->
        val surface = surface(context)
        assertNotNull(surface.keyBounds("q"))
        assertNotNull(surface.keyBounds("space"))
        assertNotNull(surface.keyBounds("⌫"))
    }

    @Test fun outsideReleaseDoesNotCommitAndVirtualNodesExist() = onMain { context ->
        val emitted = mutableListOf<KeyAction>()
        val surface = surface(context, emitted)
        val q = surface.keyBounds("q")!!
        touch(surface, MotionEvent.ACTION_DOWN, q.left + 2f, q.top + 2f)
        touch(surface, MotionEvent.ACTION_UP, surface.width - 1f, surface.height - 1f)
        assertTrue(emitted.isEmpty())
        assertNotNull(surface.accessibilityNodeProvider)
    }

    @Test fun accentBasePickerKeepsPopupAfterBaseRelease() = onMain { context ->
        val surface = surface(context, longPressEnabled = false)
        assertTrue(surface.beginAccentSelection())
        tap(surface, surface.keyBounds("e")!!)
        assertTrue(surface.hasAlternatePopup)
        assertNotNull(surface.alternateBounds("é"))
    }

    @Test fun shiftedAlternateIsExclusivelyAccessibleAndCommitsOnce() = onMain { context ->
        val emitted = mutableListOf<KeyAction>()
        val surface = surface(context, emitted, shift = true, longPressEnabled = false)
        assertTrue(surface.beginAccentSelection())
        tap(surface, surface.keyBounds("e")!!)
        val choice = surface.alternateBounds("É")
        assertNotNull(choice)

        val popupVirtualId = surface.alternateVirtualId("É")!!
        val node = requireNotNull(surface.accessibilityNodeProvider!!.createAccessibilityNodeInfo(popupVirtualId)) {
            "current popup choice must expose a virtual node"
        }
        assertEquals("É", node.text.toString())
        val inactiveBase = requireNotNull(surface.accessibilityNodeProvider!!.createAccessibilityNodeInfo(1)) {
            "inactive base node must remain structurally available to ExploreByTouchHelper"
        }
        assertFalse(inactiveBase.isEnabled)
        assertFalse(inactiveBase.isVisibleToUser)
        assertFalse(surface.accessibilityNodeProvider!!.performAction(1, AccessibilityNodeInfo.ACTION_CLICK, null))
        tap(surface, choice!!)
        assertEquals(listOf(KeyAction(KeyAction.Kind.TEXT, "É")), emitted)
        assertFalse(surface.hasAlternatePopup)
    }

    @Test fun secondPointerCancelsPopupAndCannotCommitAfterwards() = onMain { context ->
        val emitted = mutableListOf<KeyAction>()
        val surface = surface(context, emitted)
        assertTrue(surface.openAlternatesFor("e"))
        val choice = surface.alternateBounds("é")!!
        touch(surface, MotionEvent.ACTION_DOWN, choice.centerX(), choice.centerY())
        multiTouch(surface, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), choice.centerX(), choice.centerY(), choice.centerX() + 1f, choice.centerY() + 1f)
        multiTouch(surface, MotionEvent.ACTION_UP, choice.centerX(), choice.centerY(), choice.centerX() + 1f, choice.centerY() + 1f)
        assertFalse(surface.hasAlternatePopup)
        assertTrue(emitted.isEmpty())
    }

    @Test fun leavingPopupThenReturningDoesNotCommit() = onMain { context ->
        val emitted = mutableListOf<KeyAction>()
        val surface = surface(context, emitted)
        assertTrue(surface.openAlternatesFor("e"))
        val choice = surface.alternateBounds("é")!!
        touch(surface, MotionEvent.ACTION_DOWN, choice.centerX(), choice.centerY())
        touch(surface, MotionEvent.ACTION_MOVE, -5f, -5f)
        touch(surface, MotionEvent.ACTION_UP, choice.centerX(), choice.centerY())
        assertFalse(surface.hasAlternatePopup)
        assertTrue(emitted.isEmpty())
    }

    @Test fun resizeCancelsPopupWithoutCommit() = onMain { context ->
        val emitted = mutableListOf<KeyAction>()
        val surface = surface(context, emitted)
        assertTrue(surface.openAlternatesFor("e"))
        surface.layout(0, 0, surface.width - 1, surface.height)
        assertFalse(surface.hasAlternatePopup)
        assertTrue(emitted.isEmpty())
    }

    @Test fun narrowPopupKeepsEveryChoiceAndCancelInsideSurface() = onMain { context ->
        val density = context.resources.displayMetrics.density
        val width = ceil(240f * density).toInt()
        val height = ceil(236f * density).toInt()
        val surface = surface(context, width = width, height = height)
        assertTrue(surface.openAlternatesFor("a"))
        val labels = AlternateCharacters.forBase("a") + context.getString(R.string.next_key_cancel)
        labels.forEach { label ->
            val bounds = surface.alternateBounds(label)
            assertNotNull("missing alternate $label", bounds)
            bounds!!
            assertTrue(bounds.left >= 0f && bounds.top >= 0f)
            assertTrue(bounds.right <= surface.width.toFloat() && bounds.bottom <= surface.height.toFloat())
        }
    }

    @Test fun disabledLongPressStillAllowsExplicitTapPickerAndCancel() = onMain { context ->
        val emitted = mutableListOf<KeyAction>()
        val surface = surface(context, emitted, longPressEnabled = false)
        assertTrue(surface.beginAccentSelection())
        tap(surface, surface.keyBounds("e")!!)
        assertTrue(surface.hasAlternatePopup)
        tap(surface, surface.alternateBounds(context.getString(R.string.next_key_cancel))!!)
        assertFalse(surface.hasAlternatePopup)
        assertTrue(emitted.isEmpty())
    }

    @Test fun stalePopupVirtualIdCannotChooseFromANewerPopup() = onMain { context ->
        val emitted = mutableListOf<KeyAction>()
        val surface = surface(context, emitted)
        assertTrue(surface.openAlternatesFor("e"))
        val stale = surface.alternateVirtualId("é")!!
        surface.cancelPointers()
        assertTrue(surface.openAlternatesFor("a"))
        val current = surface.alternateVirtualId("á")!!
        assertTrue(stale != current)
        assertFalse(surface.accessibilityNodeProvider!!.performAction(stale, AccessibilityNodeInfo.ACTION_CLICK, null))
        assertTrue(surface.hasAlternatePopup)
        assertTrue(emitted.isEmpty())
    }

    private fun onMain(block: (android.content.Context) -> Unit) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.runOnMainSync { block(instrumentation.targetContext) }
    }

    private fun surface(
        context: android.content.Context,
        emitted: MutableList<KeyAction> = mutableListOf(),
        width: Int = (320f * context.resources.displayMetrics.density).toInt(),
        height: Int = ceil(236f * context.resources.displayMetrics.density).toInt(),
        shift: Boolean = false,
        longPressEnabled: Boolean = true,
    ): KeyboardSurface = KeyboardSurface(context) { emitted += it }.also {
        it.bindState(shift, false, "↵", longPressEnabled = longPressEnabled)
        it.measure(
            View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY),
        )
        it.layout(0, 0, width, height)
    }

    private fun tap(surface: KeyboardSurface, bounds: KeyBounds) {
        touch(surface, MotionEvent.ACTION_DOWN, bounds.centerX(), bounds.centerY())
        touch(surface, MotionEvent.ACTION_UP, bounds.centerX(), bounds.centerY())
    }

    private fun touch(surface: KeyboardSurface, action: Int, x: Float, y: Float) {
        MotionEvent.obtain(0, 1, action, x, y, 0).also {
            surface.dispatchTouchEvent(it)
            it.recycle()
        }
    }

    private fun multiTouch(surface: KeyboardSurface, action: Int, firstX: Float, firstY: Float, secondX: Float, secondY: Float) {
        val properties = arrayOf(MotionEvent.PointerProperties(), MotionEvent.PointerProperties())
        properties[0].id = 0; properties[0].toolType = MotionEvent.TOOL_TYPE_FINGER
        properties[1].id = 1; properties[1].toolType = MotionEvent.TOOL_TYPE_FINGER
        val coordinates = arrayOf(MotionEvent.PointerCoords(), MotionEvent.PointerCoords())
        coordinates[0].x = firstX; coordinates[0].y = firstY; coordinates[0].pressure = 1f; coordinates[0].size = 1f
        coordinates[1].x = secondX; coordinates[1].y = secondY; coordinates[1].pressure = 1f; coordinates[1].size = 1f
        MotionEvent.obtain(0, 2, action, 2, properties, coordinates, 0, 0, 1f, 1f, 0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0).also {
            surface.dispatchTouchEvent(it)
            it.recycle()
        }
    }

    private fun KeyBounds.centerX() = (left + right) / 2f
    private fun KeyBounds.centerY() = (top + bottom) / 2f
}
