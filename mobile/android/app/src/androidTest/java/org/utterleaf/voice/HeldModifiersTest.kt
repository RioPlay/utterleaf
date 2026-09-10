package org.utterleaf.voice

import android.content.Intent
import android.app.Activity
import android.os.SystemClock
import android.text.InputType
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.BaseInputConnection
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class HeldModifiersTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private fun buttons(view: View): List<Button> = when (view) {
        is Button -> listOf(view)
        is android.view.ViewGroup -> (0 until view.childCount).flatMap { buttons(view.getChildAt(it)) }
        else -> emptyList()
    }

    private data class Fixture(val activity: Activity, val panel: TypingPanel, val editor: EditText)

    private fun fixture(repeatDelete: Boolean = true): Fixture {
        val activity = instrumentation.startActivitySync(Intent(instrumentation.targetContext, KeyboardSettingsActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        lateinit var panel: TypingPanel; lateinit var editor: EditText
        val laidOut = CountDownLatch(1)
        instrumentation.runOnMainSync {
            editor = EditText(activity).apply { inputType = InputType.TYPE_CLASS_TEXT; isFocusableInTouchMode = true }
            val connection = {
                object : BaseInputConnection(editor, true) {
                    override fun sendKeyEvent(event: android.view.KeyEvent): Boolean = when (event.action) {
                        android.view.KeyEvent.ACTION_DOWN -> editor.onKeyDown(event.keyCode, event)
                        android.view.KeyEvent.ACTION_UP -> editor.onKeyUp(event.keyCode, event)
                        else -> false
                    }
                    override fun commitText(text: CharSequence?, newCursorPosition: Int): Boolean {
                        editor.text.replace(editor.selectionStart.coerceAtLeast(0), editor.selectionEnd.coerceAtLeast(0), text ?: "")
                        return true
                    }
                    override fun deleteSurroundingText(beforeLength: Int, afterLength: Int): Boolean {
                        val start = (editor.selectionStart - beforeLength).coerceAtLeast(0)
                        editor.text.delete(start, editor.selectionStart); return true
                    }
                }
            }
            panel = TypingPanel(activity, KeyboardOptions(terminal = true, deleteRepeat = repeatDelete),
                { text -> TerminalInput.printable(connection(), text, forceKeyEvents = true) },
                { connection()?.deleteSurroundingText(1, 0) }, {}, {}, {}, {}, {},
                { code, ctrl, alt, shift -> TerminalInput.send(connection(), code, ctrl, alt, shift) })
            panel.reset(false, false, "Enter")
            panel.view.addOnLayoutChangeListener { _, left, top, right, bottom, _, _, _, _ ->
                if (right > left && bottom > top) laidOut.countDown()
            }
            activity.setContentView(FrameLayout(activity).apply {
                addView(editor, FrameLayout.LayoutParams(-1, 120))
                addView(panel.view, FrameLayout.LayoutParams(-1, -2))
            })
            editor.requestFocus(); editor.setText("one two"); editor.setSelection(editor.length())
        }
        assertTrue("Attached panel did not lay out", laidOut.await(5, TimeUnit.SECONDS))
        instrumentation.waitForIdleSync()
        return Fixture(activity, panel, editor)
    }

    private fun center(panel: TypingPanel, label: String): Pair<Float, Float> {
        val button = buttons(panel.view).single { it.contentDescription == label }
        val root = IntArray(2); val position = IntArray(2)
        panel.view.getLocationOnScreen(root); button.getLocationOnScreen(position)
        return Pair(position[0] - root[0] + button.width / 2f, position[1] - root[1] + button.height / 2f)
    }

    private fun dispatch(panel: TypingPanel, downTime: Long, action: Int, points: List<Pair<Float, Float>>) {
        val properties = Array(points.size) { index -> MotionEvent.PointerProperties().apply { id = index; toolType = MotionEvent.TOOL_TYPE_FINGER } }
        val coordinates = Array(points.size) { index -> MotionEvent.PointerCoords().apply {
            x = points[index].first; y = points[index].second; pressure = 1f; size = 1f
        } }
        val now = SystemClock.uptimeMillis()
        val event = MotionEvent.obtain(downTime, now, action, points.size, properties, coordinates,
            0, 0, 1f, 1f, 0, 0, android.view.InputDevice.SOURCE_TOUCHSCREEN, 0)
        try { panel.view.dispatchTouchEvent(event) } finally { event.recycle() }
    }

    @Test fun heldCtrlBackspaceDeletesWordsThenPlainBackspaceAfterRelease() {
        val f = fixture()
        try {
            instrumentation.runOnMainSync {
                val ctrl = center(f.panel, "Control off"); val del = center(f.panel, "Delete")
                val down = SystemClock.uptimeMillis(); dispatch(f.panel, down, MotionEvent.ACTION_DOWN, listOf(ctrl))
                dispatch(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(ctrl, del))
                assertEquals("one ", f.editor.text.toString())
                dispatch(f.panel, down, MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(ctrl, del))
                f.editor.setText("three four"); f.editor.setSelection(f.editor.length())
                dispatch(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(ctrl, del))
                assertEquals("three ", f.editor.text.toString())
                dispatch(f.panel, down, MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(ctrl, del))
                dispatch(f.panel, down, MotionEvent.ACTION_UP, listOf(ctrl))
                dispatch(f.panel, SystemClock.uptimeMillis(), MotionEvent.ACTION_DOWN, listOf(del))
                dispatch(f.panel, SystemClock.uptimeMillis(), MotionEvent.ACTION_UP, listOf(del))
            }
            assertEquals("three", f.editor.text.toString())
        } finally { instrumentation.runOnMainSync { f.activity.finish() } }
    }

    @Test fun heldModifiedDeleteRepeatsOnlyWhenEnabledAndStopsOnRelease() {
        for (enabled in listOf(true, false)) {
            val f = fixture(enabled)
            try {
                lateinit var ctrl: Pair<Float, Float>; lateinit var del: Pair<Float, Float>
                val down = SystemClock.uptimeMillis()
                instrumentation.runOnMainSync {
                    f.editor.setText("one two three four"); f.editor.setSelection(f.editor.length())
                    ctrl = center(f.panel, "Control off"); del = center(f.panel, "Delete")
                    dispatch(f.panel, down, MotionEvent.ACTION_DOWN, listOf(ctrl))
                    dispatch(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(ctrl, del))
                    assertEquals("one two three ", f.editor.text.toString())
                }
                if (enabled) UiAwait.until("Modified delete did not repeat") { f.editor.length() < "one two three ".length }
                else UiAwait.remains("Disabled repeat changed text") { f.editor.text.toString() == "one two three " }
                var releasedText = ""
                instrumentation.runOnMainSync {
                    if (enabled) assertTrue(f.editor.length() < "one two three ".length)
                    else assertEquals("one two three ", f.editor.text.toString())
                    dispatch(f.panel, down, MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(ctrl, del))
                    dispatch(f.panel, down, MotionEvent.ACTION_UP, listOf(ctrl))
                    releasedText = f.editor.text.toString()
                }
                UiAwait.remains("Modified delete continued after release") { f.editor.text.toString() == releasedText }
            } finally { instrumentation.runOnMainSync { f.activity.finish() } }
        }
    }
    @Test fun cancelMoveOutsideAndResetClearHeldModifierState() {
        val f = fixture()
        try {
            instrumentation.runOnMainSync {
                val ctrl = center(f.panel, "Control off"); val del = center(f.panel, "Delete")
                val down = SystemClock.uptimeMillis(); dispatch(f.panel, down, MotionEvent.ACTION_DOWN, listOf(ctrl))
                dispatch(f.panel, down, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(ctrl, del))
                dispatch(f.panel, down, MotionEvent.ACTION_MOVE, listOf(ctrl, Pair(del.first + 500f, del.second)))
                dispatch(f.panel, down, MotionEvent.ACTION_UP, listOf(ctrl))
                f.editor.setText("one two"); f.editor.setSelection(f.editor.length())
                val cancelledDown = SystemClock.uptimeMillis()
                dispatch(f.panel, cancelledDown, MotionEvent.ACTION_DOWN, listOf(ctrl))
                dispatch(f.panel, cancelledDown, MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), listOf(ctrl, del))
                dispatch(f.panel, cancelledDown, MotionEvent.ACTION_CANCEL, listOf(ctrl, del))
                f.panel.reset(false, false, "Enter")
                buttons(f.panel.view).single { it.contentDescription == "Delete" }.performClick()
            }
            UiAwait.remains("Cancelled modifier repeated or remained armed") { f.editor.text.toString() == "one" }
        } finally { instrumentation.runOnMainSync { f.activity.finish() } }
    }
}
