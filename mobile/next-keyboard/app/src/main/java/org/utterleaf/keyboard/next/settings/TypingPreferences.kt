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

data class TypingOptions(val numberRow: Boolean = false, val accentLongPress: Boolean = true)

internal interface TypingStorage {
    fun read(): TypingOptions
    fun write(options: TypingOptions)
}

/** Version byte plus two explicit preference bits. No text, touches, or user assets. */
internal class LocalTypingStorage(directory: File) : TypingStorage {
    private val path = File(directory, "typing.v1")
    private val file = AtomicFile(path)
    override fun read(): TypingOptions = try {
        file.openRead().use { input ->
            check(input.read() == 1)
            val flags = input.read()
            check(flags in 0..3 && input.read() == -1)
            TypingOptions(flags and 1 != 0, flags and 2 != 0)
        }
    } catch (missing: FileNotFoundException) {
        if (path.exists() || File(path.path + ".bak").exists()) throw missing
        TypingOptions()
    }

    override fun write(options: TypingOptions) {
        val stream = file.startWrite()
        try {
            val flags = (if (options.numberRow) 1 else 0) or (if (options.accentLongPress) 2 else 0)
            stream.write(byteArrayOf(1, flags.toByte()))
            file.finishWrite(stream)
            check(read() == options)
        } catch (failure: Exception) {
            file.failWrite(stream)
            throw failure
        }
    }
}

/** Drafts never affect the IME. Saved settings publish only after the disk acknowledgement. */
class TypingPreferences internal constructor(
    private val storage: TypingStorage,
    private val worker: Executor,
    private val post: (() -> Unit) -> Unit,
    private val owner: MainThreadCheck = AndroidMainThread,
) {
    data class State(
        val saved: TypingOptions = TypingOptions(),
        val draft: TypingOptions = saved,
        val ready: Boolean = false,
        val saving: Boolean = false,
        val failed: Boolean = false,
    )
    var state = State()
        private set
    private val observers = linkedSetOf<(State) -> Unit>()

    init {
        worker.execute {
            val result = runCatching { storage.read() }
            post { publish(State(saved = result.getOrDefault(TypingOptions()), ready = true, failed = result.isFailure)) }
        }
    }

    fun observe(listener: (State) -> Unit) { owner.check(); observers += listener; listener(state) }
    fun removeObserver(listener: (State) -> Unit) { owner.check(); observers -= listener }
    fun edit(options: TypingOptions) {
        owner.check()
        if (state.ready && !state.saving) publish(state.copy(draft = options))
    }
    fun discard() {
        owner.check()
        if (!state.saving) publish(state.copy(draft = state.saved))
    }
    fun apply() {
        owner.check()
        if (!state.ready || state.saving) return
        val requested = state.draft
        publish(state.copy(saving = true))
        worker.execute {
            val success = runCatching { storage.write(requested) }.isSuccess
            post {
                publish(state.copy(saved = if (success) requested else state.saved,
                    saving = false, failed = !success))
            }
        }
    }
    /** Resets only typing preferences; Incognito and all user assets are separate. */
    fun reset() { owner.check(); if (state.ready && !state.saving) { edit(TypingOptions()); apply() } }
    private fun publish(next: State) { owner.check(); state = next; observers.toList().forEach { it(next) } }

    companion object {
        private var instance: TypingPreferences? = null
        fun get(context: Context): TypingPreferences {
            AndroidMainThread.check()
            return instance ?: TypingPreferences(
                LocalTypingStorage(context.applicationContext.noBackupFilesDir),
                Executors.newSingleThreadExecutor { task -> Thread(task, "utterleaf-typing-preferences") },
                Handler(Looper.getMainLooper()).let { handler -> { task -> handler.post(task); Unit } },
            ).also { instance = it }
        }
    }
}
