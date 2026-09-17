package org.utterleaf.voice

import android.content.Context

/**
 * Loads the public-domain completion word list from the packaged resource.
 * The list is frequency-ordered plain English derived from Project Gutenberg
 * texts by mobile/android/tools/build_wordlist.py; provenance is recorded in
 * assets/NOTICE.txt.
 */
object SuggestionRepository {
    @Volatile private var loaded: SuggestionEngine? = null

    fun load(context: Context): SuggestionEngine {
        loaded?.let { return it }
        synchronized(this) {
            loaded?.let { return it }
            val words = context.resources.openRawResource(R.raw.wordlist_en)
                .bufferedReader().readLines().filter { it.isNotBlank() }
            return SuggestionEngine(words).also { loaded = it }
        }
    }
}
