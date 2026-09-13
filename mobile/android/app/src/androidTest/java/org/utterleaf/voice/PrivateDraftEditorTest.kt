package org.utterleaf.voice

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Parcelable
import android.util.SparseArray
import android.view.ContentInfo
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityNodeInfo
import android.view.autofill.AutofillValue
import android.view.inputmethod.EditorInfo
import android.view.textclassifier.TextClassifier
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class PrivateDraftEditorTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()

    private fun <T> main(block: () -> T): T {
        val result = AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }

    @Test fun ownedKeysSelectionNavigationAndHistoryStayInBoundedModel() = main {
        val changes = mutableListOf<PrivateDraftSnapshot>()
        val editor = PrivateDraftEditor(instrumentation.targetContext, onChanged = { changes += it })

        assertTrue(editor.replace("A😀B\nxy\nz"))
        assertEquals("A😀B\nxy\nz", editor.view.text.toString())
        editor.view.setSelection(3, 1)
        assertEquals(PrivateDraftSnapshot("A😀B\nxy\nz", 3, 1), editor.current)

        assertTrue(editor.replace("Q"))
        assertEquals("AQB\nxy\nz", editor.current.text)
        assertTrue(editor.action(EditorAction.UNDO))
        assertEquals("A😀B\nxy\nz", editor.current.text)
        assertTrue(editor.action(EditorAction.REDO))
        assertEquals("AQB\nxy\nz", editor.current.text)

        assertTrue(editor.navigate(KeyEvent.KEYCODE_MOVE_HOME))
        assertEquals(0, editor.current.selectionEnd)
        assertTrue(editor.navigate(KeyEvent.KEYCODE_DPAD_DOWN))
        assertEquals(4, editor.current.selectionEnd)
        assertTrue(editor.navigate(KeyEvent.KEYCODE_DPAD_RIGHT, select = true))
        assertEquals(4, editor.current.selectionStart)
        assertEquals(5, editor.current.selectionEnd)
        assertTrue(editor.navigate(KeyEvent.KEYCODE_FORWARD_DEL))
        assertEquals("AQB\ny\nz", editor.current.text)
        assertTrue(editor.erase())
        assertEquals("AQBy\nz", editor.current.text)

        assertTrue(editor.action(EditorAction.SELECT_ALL))
        assertEquals(0, editor.view.selectionStart)
        assertEquals(editor.current.text.length, editor.view.selectionEnd)
        assertTrue(changes.isNotEmpty())
        assertEquals(editor.current, changes.last())
    }

    @Test fun clipboardMenusPhysicalTypingAndContentImportsAreRejected() {
        val context = instrumentation.targetContext
        val activity = instrumentation.startActivitySync(Intent(context, KeyboardTestActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            main {
                val clipboard = activity.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("marker", "clipboard-marker"))
                val editor = PrivateDraftEditor(activity)
                activity.setContentView(editor.view)
                assertTrue(editor.replace("private text"))
                assertTrue(editor.action(EditorAction.SELECT_ALL))
                val before = editor.current

                listOf(android.R.id.copy, android.R.id.cut, android.R.id.paste, android.R.id.selectAll,
                    android.R.id.shareText, android.R.id.textAssist).forEach {
                    assertFalse(editor.view.onTextContextMenuItem(it))
                }
                assertFalse(editor.action(EditorAction.COPY))
                assertFalse(editor.action(EditorAction.CUT))
                assertFalse(editor.action(EditorAction.PASTE))
                assertFalse(editor.view.showContextMenu())
                assertFalse(editor.view.showContextMenu(1f, 1f))

                val ctrlC = KeyEvent(0, 0, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_C, 0, KeyEvent.META_CTRL_ON)
                val ctrlX = KeyEvent(0, 0, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_X, 0, KeyEvent.META_CTRL_ON)
                val ctrlV = KeyEvent(0, 0, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_V, 0, KeyEvent.META_CTRL_ON)
                assertTrue(editor.view.onKeyShortcut(KeyEvent.KEYCODE_C, ctrlC))
                assertTrue(editor.view.onKeyDown(KeyEvent.KEYCODE_X, ctrlX))
                assertTrue(editor.view.onKeyUp(KeyEvent.KEYCODE_V,
                    KeyEvent.changeAction(ctrlV, KeyEvent.ACTION_UP)))
                assertTrue(editor.view.onKeyDown(KeyEvent.KEYCODE_A,
                    KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_A)))

                assertNull(editor.view.onCreateInputConnection(EditorInfo()))
                assertFalse(editor.view.onCheckIsTextEditor())
                editor.view.autofill(AutofillValue.forText("autofill import"))
                val arguments = Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, "accessibility import")
                }
                assertFalse(editor.view.performAccessibilityAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments))
                editor.view.setText("direct view mutation")
                if (Build.VERSION.SDK_INT >= 31) {
                    val payload = ContentInfo.Builder(ClipData.newPlainText("incoming", "content import"),
                        ContentInfo.SOURCE_CLIPBOARD).build()
                    assertSame(payload, editor.view.onReceiveContent(payload))
                }

                assertEquals(before, editor.current)
                assertEquals("private text", editor.view.text.toString())
                assertEquals("clipboard-marker", clipboard.primaryClip?.getItemAt(0)?.text?.toString())
            }
        } finally {
            main {
                (activity.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as ClipboardManager)
                    .setPrimaryClip(ClipData.newPlainText("", ""))
                activity.finish()
            }
            instrumentation.waitForIdleSync()
        }
    }

    @Test fun attachedNativeCaretSelectionUpdatesOnlyThePrivateModel() {
        val context = instrumentation.targetContext
        val activity = instrumentation.startActivitySync(Intent(context, KeyboardTestActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            val laidOut = CountDownLatch(1)
            val editor = main {
                PrivateDraftEditor(activity).also {
                    it.replace("alpha beta")
                    it.view.addOnLayoutChangeListener { _, left, top, right, bottom, _, _, _, _ ->
                        if (right > left && bottom > top) laidOut.countDown()
                    }
                    activity.setContentView(it.view)
                }
            }
            assertTrue(laidOut.await(5, TimeUnit.SECONDS))
            instrumentation.waitForIdleSync()
            main {
                val layout = editor.view.layout
                val offset = 6
                val x = editor.view.totalPaddingLeft + layout.getPrimaryHorizontal(offset)
                val line = layout.getLineForOffset(offset)
                val y = editor.view.totalPaddingTop + (layout.getLineTop(line) + layout.getLineBottom(line)) / 2f
                val now = android.os.SystemClock.uptimeMillis()
                val down = MotionEvent.obtain(now, now, MotionEvent.ACTION_DOWN, x, y, 0)
                val up = MotionEvent.obtain(now, now + 10, MotionEvent.ACTION_UP, x, y, 0)
                try {
                    assertTrue(editor.view.dispatchTouchEvent(down))
                    assertTrue(editor.view.dispatchTouchEvent(up))
                } finally {
                    down.recycle(); up.recycle()
                }
                assertEquals(editor.view.selectionStart, editor.current.selectionStart)
                assertEquals(editor.view.selectionEnd, editor.current.selectionEnd)
                assertTrue(editor.current.selectionStart in 5..7)
                assertEquals("alpha beta", editor.current.text)
            }
        } finally {
            main { activity.finish() }
            instrumentation.waitForIdleSync()
        }
    }

    @Test fun platformStateAndClassificationDoNotExportDraft() = main {
        val editor = PrivateDraftEditor(instrumentation.targetContext)
        assertTrue(editor.replace("never saved"))
        editor.view.id = 27182

        assertFalse(editor.view.isSaveEnabled)
        assertFalse(editor.view.isSaveFromParentEnabled)
        assertFalse(editor.view.showSoftInputOnFocus)
        assertEquals(View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS, editor.view.importantForAutofill)
        assertEquals(View.AUTOFILL_TYPE_NONE, editor.view.autofillType)
        assertNull(editor.view.autofillValue)
        assertSame(TextClassifier.NO_OP, editor.view.textClassifier)
        if (Build.VERSION.SDK_INT >= 30) {
            assertEquals(View.IMPORTANT_FOR_CONTENT_CAPTURE_NO_EXCLUDE_DESCENDANTS,
                editor.view.importantForContentCapture)
        }

        val state = SparseArray<Parcelable>()
        editor.view.saveHierarchyState(state)
        assertEquals(0, state.size())
    }

    @Test fun refusalsAreAtomicAndDisposeRemovesVisibleAccessibleAndModelText() = main {
        val changes = mutableListOf<PrivateDraftSnapshot>()
        val editor = PrivateDraftEditor(instrumentation.targetContext, onChanged = { changes += it })
        assertTrue(editor.replace("safe 😀"))
        val before = editor.current
        val changeCount = changes.size

        assertFalse(editor.replace("\uD800"))
        assertFalse(editor.replace("x".repeat(PrivateDraftBuffer.MAX_UTF16_UNITS)))
        assertEquals(before, editor.current)
        assertEquals(before.text, editor.view.text.toString())
        assertEquals(changeCount, changes.size)

        val staleView = editor.view
        editor.dispose()
        assertTrue(editor.isDisposed)
        assertEquals("", editor.current.text)
        assertEquals("", staleView.text.toString())
        assertFalse(editor.replace("late"))
        assertFalse(editor.erase())
        assertFalse(editor.navigate(KeyEvent.KEYCODE_DPAD_LEFT))
        assertFalse(editor.clearDraft())

        staleView.setSelection(0)
        val node = AccessibilityNodeInfo.obtain()
        try {
            staleView.onInitializeAccessibilityNodeInfo(node)
            assertFalse(node.text?.contains("safe") == true)
        } finally {
            node.recycle()
        }
        assertEquals("", editor.current.text)
    }
}
