package org.utterleaf.voice

import android.os.Handler
import android.os.Looper
import java.io.File
import java.io.InputStream
import java.nio.file.Files
import java.util.concurrent.atomic.AtomicBoolean

/** App-owned import state. Never retains a picker URI, Activity, or imported bytes. */
internal class ModelImportWork(private val directory: File) {
    enum class Phase { IDLE, VERIFYING, RECOVERING, INSTALLED, FAILED, INTERRUPTED }
    data class State(val phase: Phase, val message: String = "", val revision: Long = 0) {
        val busy get() = phase == Phase.VERIFYING || phase == Phase.RECOVERING
    }

    private class Observer(val callback: (State) -> Unit) {
        val active = AtomicBoolean(true)
        var lastRevision = -1L // Read only on the main thread.
    }

    private val lock = Any()
    private val main = Handler(Looper.getMainLooper())
    private val observers = mutableSetOf<Observer>()
    private var current = State(Phase.IDLE)
    val state: State get() = synchronized(lock) { current }

    fun observe(callback: (State) -> Unit): AutoCloseable {
        val observer = Observer(callback)
        val initial = synchronized(lock) { observers.add(observer); current }
        deliver(observer, initial)
        return AutoCloseable {
            observer.active.set(false)
            synchronized(lock) { observers.remove(observer) }
        }
    }

    private fun deliver(observer: Observer, value: State) {
        main.post {
            if (observer.active.get() && value.revision > observer.lastRevision) {
                observer.lastRevision = value.revision
                try { observer.callback(value) } catch (_: RuntimeException) {
                    observer.active.set(false)
                    synchronized(lock) { observers.remove(observer) }
                }
            }
        }
    }

    private fun publish(phase: Phase, message: String = "") {
        val (value, recipients) = synchronized(lock) {
            current = State(phase, message, current.revision + 1)
            current to observers.toList()
        }
        recipients.forEach { deliver(it, value) }
    }

    /** WorkLease bounds the process to one capture/import/mutation; no work is queued. */
    fun start(openInput: () -> InputStream): Boolean {
        synchronized(lock) {
            if (current.busy || !WorkLease.acquire()) return false
            publish(Phase.VERIFYING, "Verifying the model on this device… Your existing model and typing are unchanged.")
        }
        return launch {
            try {
                val installed = openInput().use { ModelStore.install(it, directory) }
                State(Phase.INSTALLED,
                    "${ModelPresentation.forSpec(installed).name} verified and installed. You can now remove the downloaded copy from Downloads.")
            } catch (_: Exception) {
                State(Phase.FAILED,
                    "The model could not be imported. Your existing model is kept and typing still works. Choose the original supported file again and check free storage.")
            }
        }
    }

    /** Only removes the exact unpublished temporary file left by a terminated import. */
    fun recoverInterrupted() {
        if (state.phase != Phase.IDLE) return
        val pending = File(directory, "model-import.tmp")
        if (!pending.exists()) return
        synchronized(lock) {
            if (current.phase != Phase.IDLE || !WorkLease.acquire()) return
            publish(Phase.RECOVERING, "Checking an interrupted model import… Typing still works.")
        }
        launch {
            try {
                val root = directory.canonicalFile
                check(pending.canonicalFile.parentFile == root &&
                    pending.name == "model-import.tmp" && !Files.isSymbolicLink(pending.toPath()) &&
                    !pending.isDirectory) { "Unowned import staging path" }
                check(!pending.exists() || pending.delete()) { "Could not remove interrupted staging file" }
                State(Phase.INTERRUPTED,
                    "The previous import was interrupted. Your installed model is kept and typing still works. Choose the model file again.")
            } catch (_: Exception) {
                State(Phase.FAILED,
                    "The interrupted import could not be cleared. Your installed model is kept and typing still works. Check free storage and reopen Utterleaf before trying again.")
            }
        }
    }

    private fun launch(work: () -> State): Boolean {
        return try {
            Thread({
                val result = try { work() } catch (_: OutOfMemoryError) {
                    memoryFailure()
                } finally { WorkLease.release() }
                // busy remains true until after release, preventing another
                // import from starting before this terminal state is published.
                publish(result.phase, result.message)
            }, "utterleaf-model-import").start()
            true
        } catch (_: Exception) {
            WorkLease.release()
            publish(Phase.FAILED,
                "The import could not start. Your installed model is kept and typing still works. Try again.")
            false
        } catch (_: OutOfMemoryError) {
            WorkLease.release()
            val failure = memoryFailure()
            publish(failure.phase, failure.message)
            false
        }
    }

    private fun memoryFailure() = State(Phase.FAILED,
        "There was not enough memory to import the model. Your installed model is kept and typing still works. Close other apps and try again.")
}

/** One ordinary application directory; tests can create isolated ModelImportWork instances. */
internal object ModelImports {
    private var owner: File? = null
    private var work: ModelImportWork? = null

    @Synchronized fun forDirectory(directory: File): ModelImportWork {
        val resolved = directory.canonicalFile
        check(owner == null || owner == resolved) { "Model import owner changed within this process" }
        return work ?: ModelImportWork(resolved).also { owner = resolved; work = it }
    }
}
