package org.utterleaf.voice

import org.junit.Assert.*
import org.junit.Test
import java.nio.file.Files

class PrivacyCoreTest {
    @Test fun delayedResultsCannotCrossFields() {
        val gate = TakeGate()
        val first = gate.next()
        assertTrue(gate.accepts(first))
        gate.invalidate()
        assertFalse(gate.accepts(first))
        val second = gate.next()
        assertFalse(gate.accepts(first))
        assertTrue(gate.accepts(second))
        gate.invalidate()
        assertFalse(gate.accepts(second))
    }
    @Test fun failedImportPreservesInstalledModelAndRemovesTemporaryBytes() {
        val directory = Files.createTempDirectory("utterleaf-model-test").toFile()
        try {
            val existing = ModelStore.file(directory)
            existing.writeText("previous model")
            try { ModelStore.install("not a model".byteInputStream(), directory); fail("Unverified model accepted") }
            catch (_: IllegalArgumentException) { }
            assertEquals("previous model", existing.readText())
            assertFalse(java.io.File(directory, "model-import.tmp").exists())
            assertFalse(ModelStore.ready(directory))
        } finally { directory.deleteRecursively() }
    }
    @Test fun captureAndImportCannotOverlap() {
        assertTrue(WorkLease.acquire())
        try { assertFalse(WorkLease.acquire()) } finally { WorkLease.release() }
        assertTrue(WorkLease.acquire()); WorkLease.release()
    }
    @Test fun fullSizeUntrustedModelFailsHashValidation() {
        val directory = Files.createTempDirectory("utterleaf-hash-test").toFile()
        val zeros = object : java.io.InputStream() {
            var left = ModelStore.SIZE
            override fun read(): Int = if (left-- > 0) 0 else -1
            override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
                if (left <= 0) return -1
                val n = minOf(left, length.toLong()).toInt()
                buffer.fill(0, offset, offset + n); left -= n; return n
            }
        }
        try {
            try { ModelStore.install(zeros, directory); fail("Same-size untrusted model accepted") }
            catch (_: IllegalArgumentException) { }
            assertFalse(ModelStore.file(directory).exists())
            assertFalse(java.io.File(directory, "model-import.tmp").exists())
        } finally { directory.deleteRecursively() }
    }
}
