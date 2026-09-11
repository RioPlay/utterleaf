package org.utterleaf.keyboard.next.settings

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.AtomicFile
import org.utterleaf.keyboard.next.core.AndroidMainThread
import org.utterleaf.keyboard.next.core.MainThreadCheck
import java.io.File
import java.io.FileNotFoundException
import java.util.concurrent.Executor
import java.util.concurrent.Executors

internal interface PrivacyStorage {
    fun read(): Boolean
    fun write(incognito: Boolean)
}

/** Only an explicit Boolean preference is stored; no editor or touch data. */
internal class LocalPrivacyStorage(directory: File) : PrivacyStorage {
    private val path = File(directory, "privacy.v1")
    private val file = AtomicFile(path)

    override fun read(): Boolean = try {
        file.openRead().use { input ->
            val value = input.read()
            check((value == '0'.code || value == '1'.code) && input.read() == 10 && input.read() == -1)
            value == '1'.code
        }
    } catch (missing: FileNotFoundException) {
        if (path.exists() || File(path.path + ".bak").exists()) throw missing
        false // First install: calibration is still unavailable/off in every mode.
    }

    override fun write(incognito: Boolean) {
        val stream = file.startWrite()
        try {
            stream.write(byteArrayOf(if (incognito) '1'.code.toByte() else '0'.code.toByte(), 10))
            file.finishWrite(stream)
            check(read() == incognito)
        } catch (failure: Exception) {
            file.failWrite(stream)
            throw failure
        }
    }
}

/** Main-owned observable policy; disk work is serialized away from keyboard input. */
class PrivacyPreferences internal constructor(
    private val storage: PrivacyStorage,
    private val worker: Executor,
    private val post: (() -> Unit) -> Unit,
    private val owner: MainThreadCheck = AndroidMainThread,
) {
    data class State(val incognito: Boolean, val ready: Boolean, val saving: Boolean, val failed: Boolean)

    var state = State(incognito = true, ready = false, saving = false, failed = false)
        private set
    private val observers = linkedSetOf<(State) -> Unit>()
    private var retryValue = true

    init {
        worker.execute {
            val result = runCatching { storage.read() }
            post { publish(State(result.getOrDefault(true), true, false, result.isFailure)) }
        }
    }

    fun observe(listener: (State) -> Unit) {
        owner.check()
        observers += listener
        listener(state)
    }

    fun removeObserver(listener: (State) -> Unit) {
        owner.check()
        observers -= listener
    }

    fun setIncognito(enabled: Boolean) {
        owner.check()
        if (!state.ready || state.saving) return
        retryValue = enabled
        // Enter immediately, and do not leave until the off preference is acknowledged.
        publish(State(incognito = true, ready = true, saving = true, failed = false))
        worker.execute {
            val saved = runCatching { storage.write(enabled) }.isSuccess
            post { publish(State(if (saved) enabled else true, true, false, !saved)) }
        }
    }

    fun retry() = setIncognito(retryValue)

    /** No other N1 preferences exist. Incognito and all user data are preserved. */
    fun resetPreferences() { owner.check() }

    private fun publish(next: State) {
        owner.check()
        state = next
        observers.toList().forEach { it(next) }
    }

    companion object {
        private var instance: PrivacyPreferences? = null
        fun get(context: Context): PrivacyPreferences {
            AndroidMainThread.check()
            return instance ?: PrivacyPreferences(
                LocalPrivacyStorage(context.applicationContext.noBackupFilesDir),
                Executors.newSingleThreadExecutor { task -> Thread(task, "utterleaf-privacy") },
                Handler(Looper.getMainLooper()).let { handler -> { task -> handler.post(task); Unit } },
            ).also { instance = it }
        }
    }
}
