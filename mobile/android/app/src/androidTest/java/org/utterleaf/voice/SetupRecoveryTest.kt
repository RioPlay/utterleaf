package org.utterleaf.voice

import android.app.Activity
import android.content.Intent
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.ByteArrayInputStream
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SetupRecoveryTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val app = instrumentation.targetContext

    private fun <T> main(block: () -> T): T {
        if (android.os.Looper.myLooper() == android.os.Looper.getMainLooper()) return block()
        val result = AtomicReference<T>()
        instrumentation.runOnMainSync { result.set(block()) }
        return result.get()
    }

    private fun await(message: String, condition: () -> Boolean) {
        val deadline = SystemClock.elapsedRealtime() + 10_000
        while (SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return
            SystemClock.sleep(20)
        }
        throw AssertionError(message)
    }

    private fun descendants(root: View): List<View> = listOf(root) + if (root is ViewGroup) {
        (0 until root.childCount).flatMap { descendants(root.getChildAt(it)) }
    } else emptyList()

    private fun hasText(activity: Activity, prefix: String) = main {
        descendants(activity.window.decorView).filterIsInstance<TextView>().any {
            it.isShown && it.text.toString().startsWith(prefix)
        }
    }

    private fun button(activity: Activity, label: String): Button = main {
        descendants(activity.window.decorView).filterIsInstance<Button>().single { it.text.toString() == label }
    }

    private fun awaitLease() = await("Import did not release its work lease") {
        if (WorkLease.acquire()) { WorkLease.release(); true } else false
    }

    private fun ownedDirectory(): File = File(app.cacheDir, "setup-recovery-${UUID.randomUUID()}").apply {
        check(mkdir())
    }

    private fun removeOwned(directory: File) {
        check(directory.canonicalFile.parentFile == app.cacheDir.canonicalFile &&
            directory.name.startsWith("setup-recovery-"))
        check(!directory.exists() || directory.deleteRecursively())
    }

    @Test fun importProgressAndFailureSurviveActivityRecreation() {
        awaitLease()
        val work = ModelImports.forDirectory(app.noBackupFilesDir)
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val closed = CountDownLatch(1)
        val stream = object : InputStream() {
            override fun read(): Int {
                entered.countDown()
                if (!release.await(10, TimeUnit.SECONDS)) throw IOException("Synthetic import timed out")
                throw IOException("Synthetic failed import")
            }
            override fun close() { closed.countDown() }
        }
        var activity: Activity? = null
        var monitor: android.app.Instrumentation.ActivityMonitor? = null
        var failure: Throwable? = null
        try {
            assertTrue(work.start { stream })
            assertTrue("Controlled import did not start", entered.await(5, TimeUnit.SECONDS))
            val original = instrumentation.startActivitySync(Intent(app, SetupActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            activity = original
            main { button(original, "Set up offline voice").performClick() }
            await("Original activity did not show import progress") { hasText(original, "Verifying the model") }
            assertFalse(main { button(original, "Import a model").isEnabled })
            main { button(original, "Show technical model details").performClick() }
            assertTrue(hasText(original, "Technical identifier:"))

            monitor = instrumentation.addMonitor(SetupActivity::class.java.name, null, false)
            main { original.recreate() }
            val recreated = checkNotNull(instrumentation.waitForMonitorWithTimeout(monitor, 10_000))
            activity = recreated
            assertNotSame(original, recreated)
            await("Recreated activity lost active import progress") { hasText(recreated, "Verifying the model") }
            assertTrue("Expanded setup state was not restored", main { button(recreated, "Import a model").isShown })
            assertFalse(main { button(recreated, "Import a model").isEnabled })
            assertTrue("Technical-details state was not restored", hasText(recreated, "Technical identifier:"))
            main { button(recreated, "Hide technical model details").performClick() }
            assertFalse(hasText(recreated, "Technical identifier:"))
            release.countDown()
            await("Recreated activity did not receive import failure and recovery") {
                hasText(recreated, "The model could not be imported.")
            }
            assertTrue(main { button(recreated, "Import a model").isEnabled })
            assertTrue("Import source remained open", closed.await(5, TimeUnit.SECONDS))
            awaitLease()
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            ImeTestReadiness.cleanupPreserving(failure,
                { release.countDown(); awaitLease() },
                { monitor?.let { instrumentation.removeMonitor(it) } },
                { main { activity?.finish() }; instrumentation.waitForIdleSync() })
        }
    }

    @Test fun failedImportPreservesVerifiedActiveBytesAndClosedObserversStayDetached() {
        awaitLease()
        val directory = ownedDirectory()
        val work = ModelImportWork(directory)
        val callbacks = AtomicInteger()
        var observer: AutoCloseable? = null
        var failure: Throwable? = null
        fun digest(file: File): List<Byte> {
            val hash = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { input ->
                val buffer = ByteArray(65_536)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    hash.update(buffer, 0, count)
                }
            }
            return hash.digest().toList()
        }
        try {
            val spec = instrumentation.context.assets.open("ggml-tiny.en.bin").use {
                ModelStore.install(it, directory)
            }
            val verified = checkNotNull(ModelStore.verifiedFile(directory))
            val before = digest(verified)
            observer = work.observe { callbacks.incrementAndGet() }
            instrumentation.waitForIdleSync()
            val delivered = callbacks.get()
            observer.close()
            observer = null
            assertTrue(work.start { ByteArrayInputStream(byteArrayOf(1, 2, 3)) })
            await("Invalid import did not fail") { work.state.phase == ModelImportWork.Phase.FAILED }
            awaitLease()
            instrumentation.waitForIdleSync()
            assertEquals("Disposed observer received later state", delivered, callbacks.get())
            assertEquals(spec, ModelStore.installed(directory))
            assertEquals(verified, ModelStore.verifiedFile(directory))
            assertEquals("Failed import changed active model bytes", before, digest(verified))
            assertFalse(File(directory, "model-import.tmp").exists())
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            ImeTestReadiness.cleanupPreserving(failure,
                { observer?.close() }, { awaitLease() }, { removeOwned(directory) })
        }
    }

    @Test fun successfulImportUsesTheSamePlainEnglishModelName() {
        awaitLease()
        val directory = ownedDirectory()
        val work = ModelImportWork(directory)
        var failure: Throwable? = null
        try {
            assertTrue(work.start { instrumentation.context.assets.open("ggml-tiny.en.bin") })
            await("Verified import did not complete") { work.state.phase == ModelImportWork.Phase.INSTALLED }
            awaitLease()
            assertTrue(work.state.message.startsWith("Compact English verified and installed."))
            assertFalse(work.state.message.contains("tiny.en"))
            assertEquals("tiny.en", ModelStore.installed(directory)?.id)
            assertNotNull(ModelStore.verifiedFile(directory))
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            ImeTestReadiness.cleanupPreserving(failure, { awaitLease() }, { removeOwned(directory) })
        }
    }

    @Test fun importMemoryFailureAndThrowingObserversLeaveRecoveryUsable() {
        awaitLease()
        val directory = ownedDirectory()
        val work = ModelImportWork(directory)
        val initialThrows = AtomicInteger()
        val laterThrows = AtomicInteger()
        val failures = AtomicInteger()
        val terminalLeaseWasAvailable = AtomicReference<Boolean>()
        val observers = mutableListOf<AutoCloseable>()
        var failure: Throwable? = null
        try {
            val marker = File(directory, "existing-model-marker").apply { writeText("keep installed data") }
            observers += work.observe {
                initialThrows.incrementAndGet()
                throw IllegalStateException("Synthetic initial observer failure")
            }
            observers += work.observe {
                if (it.phase == ModelImportWork.Phase.FAILED) {
                    laterThrows.incrementAndGet()
                    throw IllegalStateException("Synthetic later observer failure")
                }
            }
            observers += work.observe {
                if (it.phase == ModelImportWork.Phase.FAILED) {
                    val acquired = WorkLease.acquire()
                    terminalLeaseWasAvailable.set(acquired)
                    if (acquired) WorkLease.release()
                    failures.incrementAndGet()
                }
            }
            instrumentation.waitForIdleSync()
            assertTrue(work.start { throw OutOfMemoryError("Synthetic provider memory failure") })
            await("Memory failure did not reach a healthy observer") { failures.get() == 1 }
            assertEquals(ModelImportWork.Phase.FAILED, work.state.phase)
            assertTrue(work.state.message.contains("Close other apps and try again"))
            assertEquals(true, terminalLeaseWasAvailable.get())
            assertEquals("keep installed data", marker.readText())
            assertTrue(work.start { ByteArrayInputStream(byteArrayOf(1, 2, 3)) })
            await("Import could not be retried after memory failure") { failures.get() == 2 }
            assertEquals("Throwing initial observer was retained", 1, initialThrows.get())
            assertEquals("Throwing later observer was retained", 1, laterThrows.get())
            assertFalse(File(directory, "model-import.tmp").exists())
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            ImeTestReadiness.cleanupPreserving(failure,
                { observers.forEach { it.close() } }, { awaitLease() }, { removeOwned(directory) })
        }
    }

    @Test fun interruptedImportCleanupOnlyRemovesTheUnpublishedStagingFile() {
        awaitLease()
        val directory = ownedDirectory()
        var failure: Throwable? = null
        var observer: AutoCloseable? = null
        val terminalLeaseWasAvailable = AtomicReference<Boolean>()
        try {
            val pending = File(directory, "model-import.tmp").apply { writeText("incomplete synthetic model") }
            val marker = File(directory, "existing-model-marker").apply { writeText("keep installed data") }
            val work = ModelImportWork(directory)
            observer = work.observe { state ->
                if (state.phase == ModelImportWork.Phase.INTERRUPTED) {
                    val acquired = WorkLease.acquire()
                    terminalLeaseWasAvailable.set(acquired)
                    if (acquired) WorkLease.release()
                }
            }
            work.recoverInterrupted()
            await("Stale import was not reported as interrupted") {
                work.state.phase == ModelImportWork.Phase.INTERRUPTED
            }
            awaitLease()
            await("No terminal import callback") { terminalLeaseWasAvailable.get() != null }
            assertEquals("Import completed before releasing its lease", true, terminalLeaseWasAvailable.get())
            assertFalse(pending.exists())
            assertEquals("keep installed data", marker.readText())
            assertTrue(work.state.message.contains("Choose the model file again"))
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            ImeTestReadiness.cleanupPreserving(failure,
                { observer?.close() }, { awaitLease() }, { removeOwned(directory) })
        }
    }
}
