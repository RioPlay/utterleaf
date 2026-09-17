package org.utterleaf.voice

import android.content.Context
import android.os.Handler
import android.os.Looper
import java.util.concurrent.Executors

/**
 * Loads the public-domain completion word list from the packaged resource.
 * The list is frequency-ordered plain English derived from Project Gutenberg
 * texts by mobile/android/tools/build_wordlist.py; provenance is recorded in
 * assets/NOTICE.txt.
 */
object SuggestionRepository {
    @Volatile private var loaded: SuggestionEngine? = null
    @Volatile private var loading = false
    @Volatile private var failed = false
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "utterleaf-suggestions").apply { isDaemon = true }
    }
    private var ready: (() -> Unit)? = null

    /** Returns the already-built dictionary without doing any I/O. */
    fun current(): SuggestionEngine? = loaded

    /**
     * Starts the one-time resource load away from the IME main thread. Only the
     * latest listener is retained because there can be one visible typing panel.
     */
    fun preload(context: Context, onReady: () -> Unit = {}) {
        loaded?.let { main.post(onReady); return }
        if (failed) return
        synchronized(this) {
            loaded?.let { main.post(onReady); return }
            if (failed) return
            ready = onReady
            if (loading) return
            loading = true
        }
        val appContext = context.applicationContext
        worker.execute {
            val engine = runCatching { readEngine(appContext) }.getOrNull()
            val callback: (() -> Unit)?
            synchronized(this) {
                if (engine != null) loaded = engine else failed = true
                loading = false
                // onReady means the dictionary is ready. A failed immutable
                // packaged resource must not recursively retry from a refresh.
                callback = if (engine != null) ready else null
                ready = null
            }
            callback?.let { main.post(it) }
        }
    }

    fun load(context: Context): SuggestionEngine {
        loaded?.let { return it }
        synchronized(this) {
            loaded?.let { return it }
            return readEngine(context).also { loaded = it }
        }
    }

    private fun readEngine(context: Context): SuggestionEngine {
        val words = context.resources.openRawResource(R.raw.wordlist_en).use { stream ->
            stream.bufferedReader().use { reader -> reader.readLines().filter { it.isNotBlank() } }
        }
        return SuggestionEngine(words)
    }
}
