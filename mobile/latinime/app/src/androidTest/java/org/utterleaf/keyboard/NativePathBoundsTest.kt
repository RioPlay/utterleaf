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
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID

/** Disposable native dictionary paths and genuine file slices; no fabricated native pointers. */
@RunWith(AndroidJUnit4::class)
class NativePathBoundsTest {
    private val attributes = mapOf("dictionary" to "synthetic-path", "locale" to "en_US", "version" to "1")
    private fun native(name: String, vararg args: Any?): Any? = BinaryDictionary::class.java.declaredMethods
        .single { it.name == name }.apply { isAccessible = true }.invoke(null, *args)
    private fun directory(test: (File) -> Unit) {
        val directory = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir,
            "synthetic-path-${UUID.randomUUID()}")
        check(directory.mkdir())
        try { test(directory) } finally { check(directory.deleteRecursively()) }
    }
    private fun dictionary(path: File) = BinaryDictionary(path.absolutePath, false, Locale.US,
        Dictionary.TYPE_MAIN, FormatSpec.VERSION4.toLong(), attributes)
    private fun invalidPath(block: () -> Any?) {
        try { block(); fail("Malformed path was accepted") }
        catch (error: InvocationTargetException) { assertTrue(error.targetException is IllegalArgumentException) }
    }
    private fun snapshot(root: File) = root.walkTopDown().filter { it.isFile }.associate {
        it.relativeTo(root).invariantSeparatorsPath to MessageDigest.getInstance("SHA-256")
            .digest(it.readBytes()).joinToString("") { byte -> "%02x".format(byte) }
    }

    @Test fun standardUtf8PathsMatchJavaFileForBmpAndSupplementaryNames() = directory { root ->
        for (name in listOf("café-日本語.dict", "leaf-\uD83D\uDE42.dict")) {
            val path = File(root, name)
            val dictionary = dictionary(path)
            try {
                assertTrue(dictionary.addUnigramEntry("pathcanary", 200, false, false, false, 0))
                assertTrue(dictionary.flush())
                assertTrue("Native output must have the exact Java filename", path.isDirectory)
                assertTrue(File(path, "$name.header").isFile)
                assertEquals(200, dictionary.getFrequency("pathcanary"))
                assertTrue(dictionary.flushWithGC())
                assertEquals(200, dictionary.getFrequency("pathcanary"))
            } finally { dictionary.close() }
            val reopened = BinaryDictionary(path.absolutePath, 0, path.length(), false,
                Locale.US, Dictionary.TYPE_MAIN, true)
            try { assertTrue(reopened.isValidDictionary); assertEquals(200, reopened.getFrequency("pathcanary")) }
            finally { reopened.close() }
        }
        val emptyPath = File(root, "empty-\uD83D\uDE42.dict")
        assertTrue(BinaryDictionaryUtils.createEmptyDictFile(emptyPath.absolutePath,
            FormatSpec.VERSION4.toLong(), Locale.US, attributes))
        assertTrue(emptyPath.isDirectory)
    }

    @Test fun malformedPathsRejectBeforeMutationAndMissingValidPathRemainsUnavailable() = directory { root ->
        val dictionary = dictionary(File(root, "existing.dict"))
        try {
            assertTrue(dictionary.addUnigramEntry("preservedcanary", 200, false, false, false, 0))
            assertTrue(dictionary.flush())
            val before = snapshot(root)
            assertTrue(dictionary.runWithNativeOperationForTesting {
                val handle = BinaryDictionary::class.java.getDeclaredField("mNativeDict")
                    .apply { isAccessible = true }.getLong(dictionary)
                val create = BinaryDictionaryUtils::class.java.declaredMethods
                    .single { it.name == "createEmptyDictFileNative" }.apply { isAccessible = true }
                for (path in listOf(null, "", "bad\u0000path", "\uD800", "\uDC00",
                    "a".repeat(4096), "é".repeat(2048), "\uD83D\uDE42".repeat(1024))) {
                    invalidPath { native("openNative", path, 0L, 0L, false) }
                    invalidPath { native("flushNative", handle, path) }
                    invalidPath { native("flushWithGCNative", handle, path) }
                    invalidPath { native("migrateNative", handle, path, FormatSpec.VERSION4.toLong()) }
                    invalidPath { create.invoke(null, path, FormatSpec.VERSION4.toLong(), "en_US",
                        attributes.keys.toTypedArray(), attributes.values.toTypedArray()) }
                }
                assertEquals(0L, native("openNative", File(root, "missing.dict").absolutePath, 0L, 13L, false))
            })
            assertEquals(200, dictionary.getFrequency("preservedcanary"))
            assertEquals(before, snapshot(root))
        } finally { dictionary.close() }
    }

    @Test fun realFileSlicesValidateLongRangesAndSupportUnalignedOffsets() = directory { root ->
        // AOSP V202: big-endian 12-byte header, then a static root array with zero nodes.
        val emptyDictionary = ByteBuffer.allocate(13).order(ByteOrder.BIG_ENDIAN)
            .putInt(0x9BC13AFEL.toInt()).putShort(202.toShort()).putShort(0.toShort())
            .putInt(12).put(0.toByte()).array()
        val path = File(root, "synthetic-v202.bin")
        path.writeBytes(ByteArray(7) + emptyDictionary)
        val dictionary = BinaryDictionary(path.absolutePath, 7, emptyDictionary.size.toLong(),
            false, Locale.US, Dictionary.TYPE_MAIN, false)
        try {
            assertTrue(dictionary.isValidDictionary)
            assertEquals(Dictionary.NOT_A_PROBABILITY, dictionary.getFrequency("synthetic"))
        } finally { dictionary.close() }
        for ((offset, size) in listOf(
            -1L to 13L, 7L to -1L, (Int.MAX_VALUE.toLong() + 1) to 13L,
            7L to (Int.MAX_VALUE.toLong() + 1), Long.MAX_VALUE to Long.MAX_VALUE,
            7L to 0L, 7L to 14L, path.length() to 1L,
            Int.MAX_VALUE.toLong() to Int.MAX_VALUE.toLong()
        )) assertEquals(0L, native("openNative", path.absolutePath, offset, size, false))
        assertArrayEquals(ByteArray(7) + emptyDictionary, path.readBytes())
    }
}
