package org.utterleaf.keyboard

import android.view.View
import android.view.inputmethod.BaseInputConnection
import android.view.inputmethod.ExtractedText
import android.view.inputmethod.ExtractedTextRequest
import android.view.inputmethod.SurroundingText
import android.view.inputmethod.TextSnapshot
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SensitiveInputConnectionTest {
    @Test fun sensitiveQueriesNeverReachHostButExplicitTypingStillWorks() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.runOnMainSync {
            var reads = 0
            val host = object : BaseInputConnection(View(instrumentation.targetContext), true) {
                override fun getTextBeforeCursor(n: Int, flags: Int): CharSequence { reads++; return "canary" }
                override fun getTextAfterCursor(n: Int, flags: Int): CharSequence { reads++; return "canary" }
                override fun getSelectedText(flags: Int): CharSequence { reads++; return "canary" }
                override fun getExtractedText(request: ExtractedTextRequest?, flags: Int): ExtractedText? { reads++; return null }
                override fun getSurroundingText(beforeLength: Int, afterLength: Int, flags: Int): SurroundingText? { reads++; return null }
                override fun getCursorCapsMode(reqModes: Int): Int { reads++; return 0 }
                override fun takeSnapshot(): TextSnapshot? { reads++; return null }
                override fun requestCursorUpdates(cursorUpdateMode: Int): Boolean { reads++; return true }
                override fun requestCursorUpdates(cursorUpdateMode: Int, cursorUpdateFilter: Int): Boolean { reads++; return true }
            }
            val guarded = SensitiveInputConnection(host)
            assertEquals("", guarded.getTextBeforeCursor(1024, 0))
            assertEquals("", guarded.getTextAfterCursor(1024, 0))
            assertNull(guarded.getSelectedText(0))
            assertNull(guarded.getExtractedText(ExtractedTextRequest(), 0))
            assertNull(guarded.getSurroundingText(1024, 1024, 0))
            assertEquals(0, guarded.getCursorCapsMode(0))
            assertNull(guarded.takeSnapshot())
            assertFalse(guarded.requestCursorUpdates(1))
            assertFalse(guarded.requestCursorUpdates(1, 0))
            assertEquals(0, reads)
            assertTrue(guarded.commitText("ab", 1))
            assertTrue(guarded.deleteSurroundingText(1, 0))
            assertEquals("a", host.editable.toString())
        }
    }
}
