package org.utterleaf.keyboard

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.BinaryDictionary
import com.android.inputmethod.latin.Dictionary
import com.android.inputmethod.latin.DicTraverseSession
import com.android.inputmethod.latin.makedict.FormatSpec
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.Locale
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class NativeTraverseInitTest {
    @Test fun malformedSessionInitializationIsBoundedAndValidSessionRemainsReusable() {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-traverse-init-${UUID.randomUUID()}")
        check(directory.mkdir())
        val dictionary = BinaryDictionary(File(directory, "fixture.dict").absolutePath, false,
            Locale.ENGLISH, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en", "version" to "1"))
        try {
            assertTrue(dictionary.addUnigramEntry("p", 180, false, false, false, 0))
            assertTrue(dictionary.runWithNativeOperationForTesting {
                val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                    .apply { isAccessible = true }.getLong(dictionary)
                val session = DicTraverseSession(Locale.ENGLISH, handle, 0)
                try {
                    for ((word, length) in listOf(
                        null to -1, null to 1, intArrayOf(112) to -1,
                        intArrayOf(112) to Int.MAX_VALUE, IntArray(49) to 49,
                        intArrayOf(112) to 2, intArrayOf(-1) to 1,
                        intArrayOf(112, 0x1F) to 2, intArrayOf(0x110001) to 1)) {
                        session.initSession(handle, word, length)
                        session.initSession(handle, intArrayOf(112), 1)
                    }
                    session.initSession(0, null, 0)
                    session.initSession(handle, null, 0)
                    session.initSession(handle, IntArray(48) { 112 }, 48)
                    // Explicit prefix length is the existing public contract; unused tail ignored.
                    session.initSession(handle, intArrayOf(112, -1), 1)
                    assertNotEquals(0L, session.session)
                    assertEquals(180, dictionary.getFrequency("p"))
                } finally { session.close() }
            })
        } finally { dictionary.close(); check(directory.deleteRecursively()) }
    }
}
