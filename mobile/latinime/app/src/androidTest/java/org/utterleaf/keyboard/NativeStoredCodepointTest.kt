package org.utterleaf.keyboard

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.BinaryDictionary
import com.android.inputmethod.latin.Dictionary
import com.android.inputmethod.latin.NgramContext
import com.android.inputmethod.latin.common.ComposedData
import com.android.inputmethod.latin.common.InputPointers
import com.android.inputmethod.latin.settings.SettingsValuesForSuggestion
import com.android.inputmethod.latin.makedict.FormatSpec
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.lang.reflect.InvocationTargetException
import java.util.Locale
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class NativeStoredCodepointTest {
    private fun native(name: String, vararg args: Any?): Any? = BinaryDictionary::class.java
        .declaredMethods.single { it.name == name }.apply { isAccessible = true }.invoke(null, *args)
    private fun fixture(test: (BinaryDictionary, Long) -> Unit) {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-stored-codepoints-${UUID.randomUUID()}")
        check(directory.mkdir())
        val dictionary = BinaryDictionary(File(directory, "fixture.dict").absolutePath, false,
            Locale.ENGLISH, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en", "version" to "1"))
        try {
            assertTrue(dictionary.runWithNativeOperationForTesting {
                val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                    .apply { isAccessible = true }.getLong(dictionary)
                assertNotEquals(0L, handle)
                test(dictionary, handle)
            })
        } finally { dictionary.close(); check(directory.deleteRecursively()) }
    }
    private fun add(handle: Long, word: IntArray, shortcut: IntArray? = null) =
        native("addUnigramEntryNative", handle, word, 180, shortcut, 0, false, false, false, 0)
    private val malformed = listOf(0x1F, -1, Int.MIN_VALUE, Int.MAX_VALUE, 0x110001, 0x110000)
        .map { intArrayOf('p'.code, it, 'z'.code) }

    @Test fun unrepresentableEditorContextReturnsNoSuggestionsAndNextRequestRemainsUsable() = fixture { dictionary, _ ->
        val data = ComposedData(InputPointers(1), false, "")
        fun predict(context: NgramContext) = dictionary.getSuggestions(data, context, 0,
            SettingsValuesForSuggestion(true), 0, 1f, null)
        for (text in listOf("p\u001Fz", "a".repeat(49))) {
            val results = predict(NgramContext(NgramContext.WordInfo(text)))
            assertNotNull(results)
            assertTrue(results!!.isEmpty())
        }
        assertNotNull(predict(NgramContext.EMPTY_PREV_WORDS_INFO))
    }

    @Test fun invalidStoredTargetsAndShortcutsCannotTruncateOrMutateWords() = fixture { _, handle ->
        val prefix = intArrayOf('p'.code)
        val target = intArrayOf('t'.code)
        assertEquals(true, add(handle, prefix))
        for (word in malformed) {
            assertEquals(false, add(handle, word))
            assertEquals(false, native("removeUnigramEntryNative", handle, word))
            assertEquals(Dictionary.NOT_A_PROBABILITY, native("getProbabilityNative", handle, word))
            assertEquals(false, add(handle, target, word))
            assertEquals(180, native("getProbabilityNative", handle, prefix))
            assertEquals(Dictionary.NOT_A_PROBABILITY, native("getProbabilityNative", handle, target))
        }
        assertEquals(false, add(handle, target, intArrayOf(0x110000, 'x'.code)))
        // These values are not the disk terminator; retain the upstream representation.
        for (value in listOf(0, 0xD800, 0xDFFF, 0x10FFFF)) {
            val word = intArrayOf('u'.code, value, 'z'.code)
            assertEquals(true, add(handle, word))
            assertEquals(180, native("getProbabilityNative", handle, word))
        }
    }

    @Test fun malformedContextsThrowBeforeMutationAndValidBosContextsRemainUsable() = fixture { _, handle ->
        val previous = intArrayOf('p'.code)
        val target = intArrayOf('t'.code)
        val flags = booleanArrayOf(false)
        assertEquals(true, add(handle, previous))
        assertEquals(true, add(handle, target))
        assertEquals(true, native("addNgramEntryNative", handle, arrayOf(previous), flags, target, 190, 0))
        for (word in malformed) {
            val context = arrayOf(word)
            val calls = listOf<() -> Any?>(
                { native("getNgramProbabilityNative", handle, context, flags, target) },
                { native("addNgramEntryNative", handle, context, flags, target, 220, 0) },
                { native("removeNgramEntryNative", handle, context, flags, target) },
                { native("updateEntriesForWordWithNgramContextNative", handle, context, flags, target, true, 1, 0) })
            for (call in calls) {
                try { call(); fail("Malformed context accepted") }
                catch (error: InvocationTargetException) {
                    assertTrue(error.targetException is IllegalArgumentException)
                }
                assertEquals(190, native("getNgramProbabilityNative", handle, arrayOf(previous), flags, target))
                assertEquals(180, native("getProbabilityNative", handle, target))
            }
        }
        val bos = intArrayOf(0x110000)
        assertEquals(true, native("addUnigramEntryNative", handle, bos, 180, null, 0, true, false, false, 0))
        assertEquals(true, native("addNgramEntryNative", handle, arrayOf(bos), booleanArrayOf(true), target, 200, 0))
        assertEquals(200, native("getNgramProbabilityNative", handle, arrayOf(bos), flags, target))
        assertEquals(200, native("getNgramProbabilityNative", handle, arrayOf(intArrayOf()), booleanArrayOf(true), target))
    }
}
