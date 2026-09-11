package org.utterleaf.keyboard

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.BinaryDictionary
import com.android.inputmethod.latin.Dictionary
import com.android.inputmethod.latin.makedict.FormatSpec
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.lang.reflect.InvocationTargetException
import java.util.Locale
import java.util.UUID

/** Real native properties with malformed outputs; no fabricated native handles. */
@RunWith(AndroidJUnit4::class)
class NativePropertyOutputBoundsTest {
    private val word = "propertycanary".map { it.code }.toIntArray()
    private val shortcut = "syntheticshortcut".map { it.code }.toIntArray()
    private fun native(name: String, vararg args: Any?): Any? = BinaryDictionary::class.java.declaredMethods
        .single { it.name == name }.apply { isAccessible = true }.invoke(null, *args)

    private fun fixture(test: (BinaryDictionary, Long) -> Unit) {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-property-outputs-${UUID.randomUUID()}")
        check(directory.mkdir())
        val dictionary = BinaryDictionary(File(directory, "fixture.dict").absolutePath, false,
            Locale.US, Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(),
            mapOf("dictionary" to "synthetic-test", "locale" to "en_US", "version" to "1"))
        try {
            assertTrue(dictionary.runWithNativeOperationForTesting {
                val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                    .apply { isAccessible = true }.getLong(dictionary)
                assertNotEquals(0L, handle)
                assertEquals(true, native("addUnigramEntryNative", handle, word, 200,
                    shortcut, 10, false, false, false, 0))
                test(dictionary, handle)
            })
        } finally { dictionary.close(); check(directory.deleteRecursively()) }
    }

    private fun outputs(): Array<Any?> = arrayOf(IntArray(48) { 73 }, BooleanArray(5) { true },
        IntArray(4) { 73 }, ArrayList<Any>(), ArrayList<Any>(), ArrayList<Any>(),
        ArrayList<Any>(), ArrayList<Any>(), ArrayList<Any>())

    private fun property(handle: Long, outputs: Array<Any?>) =
        native("getWordPropertyNative", handle, word, false, *outputs)

    private fun unchanged(outputs: Array<Any?>) {
        for (output in outputs) when (output) {
            is IntArray -> assertTrue(output.all { it == 73 })
            is BooleanArray -> assertTrue(output.all { it })
            is List<*> -> assertTrue(output.isEmpty())
        }
    }

    @Test fun malformedShapesAndNullListsLeaveAllOutputsUntouched() = fixture { _, handle ->
        val malformed = listOf(
            0 to null, 0 to IntArray(47) { 73 }, 0 to IntArray(49) { 73 },
            1 to null, 1 to BooleanArray(4) { true }, 1 to BooleanArray(6) { true },
            2 to null, 2 to IntArray(3) { 73 }, 2 to IntArray(5) { 73 }
        ) + (3..8).map { it to null }
        for ((index, invalid) in malformed) {
            val output = outputs().apply { this[index] = invalid }
            property(handle, output)
            unchanged(output)
        }
        // Java declares ArrayList parameters: reflection rejects wrong types before JNI.
        val wrongType = outputs().apply { this[3] = java.util.LinkedList<Any>() }
        try { property(handle, wrongType); fail("Reflection accepted a non-ArrayList") }
        catch (_: IllegalArgumentException) { unchanged(wrongType) }
    }

    private class ThrowingList(val failure: RuntimeException) : ArrayList<Any>() {
        var calls = 0
        override fun add(element: Any): Boolean { calls++; throw failure }
    }
    private class CountingList : ArrayList<Any>() {
        var calls = 0
        override fun add(element: Any): Boolean { calls++; return super.add(element) }
    }

    @Test fun throwingListPreservesExceptionAndStopsLaterOutputCallbacks() = fixture { dictionary, handle ->
        val failure = IllegalStateException("synthetic-output-failure")
        val throwing = ThrowingList(failure)
        val later = CountingList()
        val output = outputs().apply { this[7] = throwing; this[8] = later }
        try { property(handle, output); fail("Expected output callback failure") }
        catch (error: InvocationTargetException) { assertSame(failure, error.targetException) }
        assertEquals(1, throwing.calls)
        assertEquals(0, later.calls)
        // Primitive outputs precede callbacks: exception handling does not imply atomic output.
        assertEquals(200, (output[2] as IntArray)[0])
        assertEquals(200, dictionary.getFrequency("propertycanary"))
        val normal = outputs()
        property(handle, normal)
        assertEquals(200, (normal[2] as IntArray)[0])
        assertArrayEquals(shortcut, (normal[7] as ArrayList<*>).single() as IntArray)
        assertEquals(10, (normal[8] as ArrayList<*>).single())
    }

    @Test fun publicPropertyAndNativeOutputsKeepNormalValues() = fixture { dictionary, handle ->
        val wordProperty = dictionary.getWordProperty("propertycanary", false)
        assertNotNull(wordProperty)
        assertEquals("propertycanary", wordProperty.mWord)
        assertEquals(200, wordProperty.mProbabilityInfo.mProbability)
        val normal = outputs()
        property(handle, normal)
        assertArrayEquals(word, (normal[0] as IntArray).copyOf(word.size))
        assertArrayEquals(booleanArrayOf(false, false, false, true, false), normal[1] as BooleanArray)
        assertEquals(200, (normal[2] as IntArray)[0])
        assertArrayEquals(shortcut, (normal[7] as ArrayList<*>).single() as IntArray)
        assertEquals(10, (normal[8] as ArrayList<*>).single())
    }

    @Test fun ngramOutputsStayAlignedAndFirstCallbackFailureStopsRemainingLists() = fixture { _, handle ->
        val target = "syntheticnext".map { it.code }.toIntArray()
        assertEquals(true, native("addUnigramEntryNative", handle, target, 180,
            null, 0, false, false, false, 0))
        assertEquals(true, native("addNgramEntryNative", handle, arrayOf(word),
            booleanArrayOf(false), target, 170, 0))
        val normal = outputs()
        property(handle, normal)
        for (index in 3..6) assertEquals(1, (normal[index] as ArrayList<*>).size)
        val context = (normal[3] as ArrayList<*>).single() as Array<*>
        assertArrayEquals(word, context.single() as IntArray)
        assertArrayEquals(booleanArrayOf(false), (normal[4] as ArrayList<*>).single() as BooleanArray)
        assertArrayEquals(target, (normal[5] as ArrayList<*>).single() as IntArray)
        assertEquals(170, ((normal[6] as ArrayList<*>).single() as IntArray)[0])

        val failure = IllegalStateException("synthetic-ngram-output-failure")
        val throwing = ThrowingList(failure)
        val later = List(5) { CountingList() }
        val output = outputs().apply {
            this[3] = throwing
            later.forEachIndexed { index, list -> this[index + 4] = list }
        }
        try { property(handle, output); fail("Expected ngram callback failure") }
        catch (error: InvocationTargetException) { assertSame(failure, error.targetException) }
        assertEquals(1, throwing.calls)
        later.forEach { assertEquals(0, it.calls) }
    }
}
