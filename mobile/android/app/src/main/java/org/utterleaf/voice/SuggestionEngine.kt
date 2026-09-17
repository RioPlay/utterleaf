package org.utterleaf.voice

/**
 * Completion engine for the suggestion strip. Prefix-only: it never replaces
 * typed text on its own, so no candidate can silently change a person's
 * meaning. Candidates respect the composing word's initial case.
 */
class SuggestionEngine(words: List<String>) {
    private data class Entry(val word: String, val rank: Int)

    private val sorted: List<Entry> = words.asSequence()
        .filter { it.length >= 2 && it.all { char -> char in 'a'..'z' } }
        .distinct()
        .mapIndexed { index, word -> Entry(word, index) }
        .sortedBy { it.word }
        .toList()

    /**
     * Up to [max] dictionary words starting with [composing], ordered by
     * frequency rank. The composing word itself is excluded when it is an
     * exact dictionary entry; a completion would otherwise add nothing.
     */
    fun completions(composing: String, max: Int = 3): List<String> {
        if (composing.isEmpty() || composing.length > MAX_COMPOSING) return emptyList()
        val lower = composing.lowercase()
        if (lower.any { char -> char !in 'a'..'z' }) return emptyList()
        var low = 0
        var high = sorted.size
        while (low < high) {
            val mid = (low + high) / 2
            if (sorted[mid].word < lower) low = mid + 1 else high = mid
        }
        val matches = mutableListOf<Entry>()
        var index = low
        while (index < sorted.size && sorted[index].word.startsWith(lower) && matches.size < SCAN_LIMIT) {
            matches.add(sorted[index])
            index++
        }
        return matches.asSequence()
            .filter { it.word != lower }
            .sortedBy { it.rank }
            .take(max)
            .map { entry -> adaptCase(entry.word, composing) }
            .toList()
    }

    private fun adaptCase(word: String, composing: String): String = when {
        composing.length > 1 && composing.all { it.isUpperCase() } -> word.uppercase()
        composing[0].isUpperCase() -> word.replaceFirstChar(Char::uppercaseChar)
        else -> word
    }

    data class SuggestionState(val composing: String, val candidates: List<String>) {
        companion object {
            val EMPTY = SuggestionState("", emptyList())
        }
    }

    companion object {
        /** Bounded composing context only; never a full-document read. */
        const val MAX_COMPOSING = 32
        private const val SCAN_LIMIT = 200
    }
}
