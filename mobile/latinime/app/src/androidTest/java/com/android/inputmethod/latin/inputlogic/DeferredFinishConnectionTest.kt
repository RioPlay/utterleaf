package com.android.inputmethod.latin.inputlogic

import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.LatinIME
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.lang.reflect.Proxy

/** Exercises the real InputMethodService super callbacks with controlled editor connections. */
@RunWith(AndroidJUnit4::class)
class DeferredFinishConnectionTest {
    private class Host {
        var finishes = 0
        val connection = Proxy.newProxyInstance(InputConnection::class.java.classLoader,
            arrayOf(InputConnection::class.java)) { _, method, _ ->
            check(method.name == "finishComposingText") { "Unexpected editor call: ${method.name}" }
            finishes++
            true
        } as InputConnection
    }

    private class TestIme : LatinIME() {
        var host: InputConnection? = null
        override fun getCurrentInputConnection() = host
        val logic get() = LatinIME::class.java.getDeclaredField("mInputLogic")
            .apply { isAccessible = true }.get(this) as InputLogic
    }

    private fun fixture(block: (TestIme, Host, Host) -> Unit) {
        var result: Result<Unit>? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            result = runCatching {
                val ime = TestIme()
                try {
                    val old = Host()
                    ime.host = old.connection
                    ime.mEditorSession.start()
                    ime.logic.mWordComposer.setBatchInputWord("synthetic-old-composition")
                    // The real UIHandler tests this timing marker before recording deferred finishes.
                    val marker = ime.mHandler.javaClass.getDeclaredField("MSG_PENDING_IMS_CALLBACK")
                        .apply { isAccessible = true }.getInt(null)
                    ime.mHandler.sendEmptyMessageDelayed(marker, 60_000)
                    block(ime, old, Host())
                } finally {
                    ime.mEditorSession.finish()
                    ime.logic.destroy()
                    ime.mHandler.removeAllMessages()
                }
            }
        }
        result!!.getOrThrow()
    }

    private fun drainAgainstReplacement(ime: TestIme, replacement: Host) {
        ime.host = replacement.connection
        ime.mEditorSession.start()
        ime.logic.mWordComposer.setBatchInputWord("synthetic-new-composition")
        // Drain exactly the inherited deferred dispatch, without unrelated keyboard setup.
        ime.mHandler.javaClass.getDeclaredMethod("executePendingImsCallback", LatinIME::class.java,
            EditorInfo::class.java, Boolean::class.javaPrimitiveType).apply { isAccessible = true }
            .invoke(ime.mHandler, ime, EditorInfo(), false)
        assertEquals(0, replacement.finishes)
        assertEquals("synthetic-new-composition", ime.logic.mWordComposer.typedWord)
        assertNotNull(ime.mEditorSession.capture())
    }

    @Test fun deferredHideFinishesOriginalConnectionImmediatelyAndNeverReplacement() = fixture { ime, old, next ->
        ime.onFinishInputView(false)
        assertEquals(1, old.finishes)
        assertTrue(ime.logic.isInputStateRetired)
        assertEquals("", ime.logic.mWordComposer.typedWord)
        drainAgainstReplacement(ime, next)
        assertEquals(1, old.finishes)
    }

    @Test fun deferredViewAndInputFinishCallOriginalConnectionExactlyOnce() = fixture { ime, old, next ->
        ime.onFinishInputView(true)
        assertEquals(0, old.finishes)
        assertTrue(ime.logic.isInputStateRetired)
        ime.onFinishInput()
        assertEquals(1, old.finishes)
        drainAgainstReplacement(ime, next)
        assertEquals(1, old.finishes)
    }

    @Test fun deferredNoViewFinishFinishesOriginalConnectionImmediately() = fixture { ime, old, next ->
        ime.onFinishInput()
        assertEquals(1, old.finishes)
        assertTrue(ime.logic.isInputStateRetired)
        assertEquals("", ime.logic.mWordComposer.typedWord)
        drainAgainstReplacement(ime, next)
        assertEquals(1, old.finishes)
    }
}
