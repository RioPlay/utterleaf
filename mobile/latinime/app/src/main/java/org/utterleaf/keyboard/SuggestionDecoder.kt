package org.utterleaf.keyboard

import com.android.inputmethod.latin.Suggest

/** A queued decode whose editor inputs have already been captured by their owner. */
fun interface SuggestionDecoder {
    fun decode(callback: Suggest.OnGetSuggestedWordsCallback)
}
