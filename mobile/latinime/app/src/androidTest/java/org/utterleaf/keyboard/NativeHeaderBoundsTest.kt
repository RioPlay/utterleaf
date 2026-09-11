package org.utterleaf.keyboard

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.BinaryDictionary
import com.android.inputmethod.latin.Dictionary
import com.android.inputmethod.latin.makedict.FormatSpec
import com.android.inputmethod.latin.utils.BinaryDictionaryUtils
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.lang.reflect.InvocationTargetException
import java.util.Locale
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class NativeHeaderBoundsTest {
    private val base = mapOf("dictionary" to "synthetic-header", "locale" to "de", "version" to "1")
    private fun native(name: String, vararg args: Any?): Any? = BinaryDictionary::class.java.declaredMethods
        .single { it.name == name }.apply { isAccessible = true }.invoke(null, *args)
    private fun fixture(extra: Map<String, String> = emptyMap(), test: (BinaryDictionary, File) -> Unit) {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-header-${UUID.randomUUID()}")
        check(directory.mkdir())
        val dictionary = BinaryDictionary(File(directory, "fixture.dict").absolutePath, false,
            Locale.GERMAN, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(), base + extra)
        try { assertTrue(dictionary.isValidDictionary); test(dictionary, directory) }
        finally { dictionary.close(); check(directory.deleteRecursively()) }
    }
    private fun invalid(block: () -> Any?) {
        try {
            val result = block()
            if (result is Long && result != 0L) native("closeNative", result)
            fail("Malformed metadata was accepted")
        } catch (error: InvocationTargetException) {
            assertTrue(error.targetException is IllegalArgumentException)
        }
    }

    @Test fun unicodeMetadataAndInclusiveCodepointLimitsSurviveFlushAndReopen() {
        val largeKey = "\uD83D\uDE42".repeat(256)
        val values = mapOf(largeKey to "key-boundary", "bmp" to "é".repeat(2048),
            "supplementary" to "\uD83D\uDE42".repeat(2048), "description" to "Français 日本語",
            "zzafter" to "synthetic-tail", "empty-value" to "")
        fixture(values) { dictionary, _ ->
            val before = dictionary.header.mDictionaryOptions.mAttributes
            values.forEach { (key, value) -> assertEquals(value, before[key]) }
            assertTrue(dictionary.addUnigramEntry("headercanary", 200, false, false, false, 0))
            assertTrue(dictionary.flush())
            val after = dictionary.header.mDictionaryOptions.mAttributes
            values.filterValues { it.isNotEmpty() }.forEach { (key, value) -> assertEquals(value, after[key]) }
            // Existing disk writer omits empty attributes; accepting them does not promise persistence.
            assertNull(after["empty-value"])
            assertEquals(200, dictionary.getFrequency("headercanary"))
        }
    }

    @Test fun malformedMetadataRejectsBeforeDictionaryOrFileCreation() {
        val malformed = listOf(
            arrayOf("bad\u001Fkey") to arrayOf("value"),
            arrayOf("key") to arrayOf("bad\u001Fvalue"),
            null to arrayOf("v"), arrayOf("k") to null,
            arrayOf("k") to emptyArray<String>(), arrayOfNulls<String>(1) to arrayOf("v"),
            arrayOf("k") to arrayOfNulls<String>(1), arrayOf("k".repeat(257)) to arrayOf("v"),
            arrayOf("k") to arrayOf("v".repeat(2049)), arrayOf("k") to arrayOf("\uD83D\uDE42".repeat(2049)),
            arrayOf("k") to arrayOf("bad\u0000value"), arrayOf("k") to arrayOf("\uD800"),
            arrayOf("k") to arrayOf("\uDC00"), Array(257) { "key$it" } to Array(257) { "value" }
        )
        fixture { _, directory ->
            val file = File(directory, "must-not-exist.dict")
            val createFile = BinaryDictionaryUtils::class.java.declaredMethods
                .single { it.name == "createEmptyDictFileNative" }.apply { isAccessible = true }
            for ((keys, values) in malformed) {
                invalid { native("createOnMemoryNative", FormatSpec.VERSION4.toLong(), "de", keys, values) }
                invalid { createFile.invoke(null, file.absolutePath, FormatSpec.VERSION4.toLong(), "de", keys, values) }
                assertFalse(file.exists())
            }
            for (locale in listOf(null, "a".repeat(2049), "\uD800", "bad\u0000locale", "bad\u001Flocale")) {
                invalid { native("createOnMemoryNative", FormatSpec.VERSION4.toLong(), locale,
                    emptyArray<String>(), emptyArray<String>()) }
            }
            val emptyLocaleHandle = native("createOnMemoryNative", FormatSpec.VERSION4.toLong(), "",
                emptyArray<String>(), emptyArray<String>()) as Long
            assertNotEquals(0L, emptyLocaleHandle)
            native("closeNative", emptyLocaleHandle)
        }
    }

    @Test fun maximumAttributeCountIsAcceptedWithoutTruncation() {
        val extras = (0 until 253).associate { "custom$it" to "value$it" }
        fixture(extras) { dictionary, _ ->
            val attributes = dictionary.header.mDictionaryOptions.mAttributes
            (base + extras).forEach { (key, value) -> assertEquals(value, attributes[key]) }
        }
    }

    private class ThrowingList(val failure: RuntimeException) : ArrayList<Any>() {
        var calls = 0
        override fun add(element: Any): Boolean { calls++; throw failure }
    }
    private class CountingList : ArrayList<Any>() {
        var calls = 0
        override fun add(element: Any): Boolean { calls++; return super.add(element) }
    }
    private class ReopeningList(private val dictionary: BinaryDictionary) : ArrayList<IntArray>() {
        var reopened = false
        override fun add(element: IntArray): Boolean {
            if (!reopened) {
                reopened = true
                assertTrue(dictionary.addUnigramEntry("reentrantcanary", 200, false, false, false, 0))
                assertTrue(dictionary.flush())
            }
            return super.add(element)
        }
    }

    @Test fun headerOutputOwnsSnapshotAcrossReentrantFlushAndReopen() = fixture { dictionary, directory ->
        val expected = HashMap(dictionary.header.mDictionaryOptions.mAttributes)
        val keys = ReopeningList(dictionary)
        val values = ArrayList<IntArray>()
        assertTrue(dictionary.runWithNativeOperationForTesting {
            val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                .apply { isAccessible = true }.getLong(dictionary)
            native("getHeaderInfoNative", handle, IntArray(1), IntArray(1), keys, values)
        })
        assertTrue(keys.reopened)
        assertEquals(keys.size, values.size)
        val result = keys.indices.associate { index ->
            String(keys[index], 0, keys[index].size) to String(values[index], 0, values[index].size)
        }
        assertEquals(expected, result)
        assertTrue(File(directory, "fixture.dict").exists())
        assertEquals(200, dictionary.getFrequency("reentrantcanary"))
    }

    @Test fun malformedHeaderOutputsAreUntouchedAndThrowingListsStopLaterCallbacks() = fixture { dictionary, _ ->
        assertTrue(dictionary.runWithNativeOperationForTesting {
            val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                .apply { isAccessible = true }.getLong(dictionary)
            for (index in 0..3) {
                val outputs: Array<Any?> = arrayOf(intArrayOf(73), intArrayOf(73), ArrayList<Any>(), ArrayList<Any>())
                outputs[index] = null
                native("getHeaderInfoNative", handle, *outputs)
                outputs.filterIsInstance<IntArray>().forEach { assertArrayEquals(intArrayOf(73), it) }
                outputs.filterIsInstance<ArrayList<*>>().forEach { assertTrue(it.isEmpty()) }
            }
            for (index in 0..1) for (size in listOf(0, 2)) {
                val outputs: Array<Any?> = arrayOf(intArrayOf(73), intArrayOf(73), ArrayList<Any>(), ArrayList<Any>())
                outputs[index] = IntArray(size) { 73 }
                native("getHeaderInfoNative", handle, *outputs)
                outputs.filterIsInstance<IntArray>().forEach { assertTrue(it.all { value -> value == 73 }) }
                outputs.filterIsInstance<ArrayList<*>>().forEach { assertTrue(it.isEmpty()) }
            }
            val failure = IllegalStateException("synthetic-header-callback")
            val first = ThrowingList(failure)
            val second = CountingList()
            try { native("getHeaderInfoNative", handle, IntArray(1), IntArray(1), first, second); fail("Expected callback failure") }
            catch (error: InvocationTargetException) { assertSame(failure, error.targetException) }
            assertEquals(1, first.calls)
            assertEquals(0, second.calls)
        })
        assertEquals("synthetic-header", dictionary.header.mDictionaryOptions.mAttributes["dictionary"])
    }

    @Test fun numericMetadataPreservesIntBoundsAndRejectsOverflowOrNonAsciiDigits() {
        for ((text, enabled) in listOf("2147483647" to true, "-2147483648" to true,
            "2147483648" to false, "-2147483649" to false, "9".repeat(2048) to false,
            "١" to false, "\uD83D\uDE42" to false, "0" to false)) {
            fixture(mapOf("REQUIRES_GERMAN_UMLAUT_PROCESSING" to text)) { dictionary, _ ->
                assertTrue(dictionary.addUnigramEntry("ö", 190, false, false, false, 0))
                assertEquals("numeric metadata $text", if (enabled) 190 else Dictionary.NOT_A_PROBABILITY,
                    dictionary.getMaxFrequencyOfExactMatches("oe"))
            }
        }
    }
}
