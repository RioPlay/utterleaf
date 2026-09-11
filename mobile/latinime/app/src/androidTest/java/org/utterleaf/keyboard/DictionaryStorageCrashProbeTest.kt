package org.utterleaf.keyboard

import android.os.Process
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.BinaryDictionary
import com.android.inputmethod.latin.Dictionary
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Opt-in external SIGKILL probe; excluded from the normal instrumentation suite. */
@RunWith(AndroidJUnit4::class)
class DictionaryStorageCrashProbeTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val args = InstrumentationRegistry.getArguments()
    private val token = requireNotNull(args.getString("storageProbeToken")).also {
        require(it.matches(Regex("[0-9a-f]{32}")))
    }
    private val stage = requireNotNull(args.getString("storageProbeStage")).toInt().also { require(it in 4..6) }
    private val format = requireNotNull(args.getString("storageProbeFormat")).toInt().also { require(it == 402 || it == 403) }
    private val root = File(context.noBackupFilesDir, "storage-crash-probe/$token")
    private val path = File(root, "canary.dict")
    private fun handle(dictionary: BinaryDictionary) = BinaryDictionary::class.java
        .getDeclaredField("mNativeDict").apply { isAccessible = true }.getLong(dictionary)
    private fun record() = JSONObject().put("token", token).put("pid", Process.myPid())
        .put("uid", Process.myUid()).put("stage", stage).put("format", format)
    private fun write(name: String, value: JSONObject) {
        val pending = File(root, "$name.pending")
        pending.outputStream().use { stream -> stream.write(value.toString().toByteArray()); stream.fd.sync() }
        check(pending.renameTo(File(root, name)))
    }
    private fun hashes(directory: File): Map<String, String> = directory.walkTopDown().filter { it.isFile }.associate {
        it.relativeTo(directory).invariantSeparatorsPath to MessageDigest.getInstance("SHA-256")
            .digest(it.readBytes()).joinToString("") { byte -> "%02x".format(byte) }
    }
    @Test fun prepareAndPause() {
        check(!root.exists())
        check(root.mkdirs())
        val dictionary = BinaryDictionary(path.absolutePath, false, Locale.US, Dictionary.TYPE_MAIN,
            format.toLong(), mapOf("dictionary" to "synthetic-crash", "locale" to "en_US", "version" to "1"))
        val worker = Executors.newSingleThreadExecutor()
        var pausedHandle = 0L
        try {
            assertTrue(dictionary.addUnigramEntry("oldcanary", 200, false, false, false, 0))
            assertTrue(dictionary.flushWithGC())
            write("state.json", record().put("before", JSONObject(hashes(path))))
            assertTrue(dictionary.addUnigramEntry("newcanary", 210, false, false, false, 0))
            pausedHandle = handle(dictionary)
            assertTrue(dictionary.runWithNativeOperationForTesting {
                StorageFaults.configureNative(pausedHandle, stage, 2)
            })
            worker.submit { dictionary.flushWithGC() }
            val deadline = SystemClock.elapsedRealtime() + 10000
            while (StorageFaults.reachedNative(pausedHandle) != stage && SystemClock.elapsedRealtime() < deadline) {
                SystemClock.sleep(10)
            }
            assertEquals(stage, StorageFaults.reachedNative(pausedHandle))
            write("ready.json", record())
            check(CountDownLatch(1).await(120, TimeUnit.SECONDS)) { "External controller did not terminate the paused probe" }
        } finally {
            if (pausedHandle != 0L) StorageFaults.releaseNative(pausedHandle)
            worker.shutdown(); check(worker.awaitTermination(10, TimeUnit.SECONDS))
            dictionary.close()
        }
    }
    @Test fun verifyAfterDeath() {
        val state = JSONObject(File(root, "state.json").readText())
        assertEquals(token, state.getString("token"))
        assertEquals(stage, state.getInt("stage"))
        assertEquals(format, state.getInt("format"))
        assertNotEquals(state.getInt("pid"), Process.myPid())
        assertEquals(state.getInt("uid"), Process.myUid())
        val dictionary = BinaryDictionary(path.absolutePath, 0, path.length(), false,
            Locale.US, Dictionary.TYPE_MAIN, true)
        try {
            assertTrue(dictionary.isValidDictionary)
            assertEquals(200, dictionary.getFrequency("oldcanary"))
            assertEquals(if (stage == 4) Dictionary.NOT_A_PROBABILITY else 210,
                dictionary.getFrequency("newcanary"))
            val before = state.getJSONObject("before")
            val expected = before.keys().asSequence().associateWith { before.getString(it) }
            val oldPath = if (stage == 4) path else File(root, "canary.dict.utterleaf-stage/canary.dict")
            assertEquals(expected, hashes(oldPath))
            assertTrue(dictionary.addUnigramEntry("recoverycanary", 190, false, false, false, 0))
            assertTrue(dictionary.flush())
            assertEquals(190, dictionary.getFrequency("recoverycanary"))
            assertFalse(File(root, "canary.dict.utterleaf-stage").exists())
            write("verified.json", record().put("result", "pass"))
        } finally { dictionary.close() }
    }
}
