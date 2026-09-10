package org.utterleaf.voice

import java.util.Locale

/**
 * The secondary characters shown for a letter key's alternate-character menu.
 *
 * This is deliberately a small, stable catalog: the first entries are common
 * Latin alternates and the final entry is the visible key hint. Symbols are
 * returned as strings because uppercase ß expands to SS.
 */
object AlternateCharacters {
    private val accents = mapOf(
        'a' to listOf("á", "à", "ä", "â", "å", "ā", "æ", "ã"),
        'e' to listOf("é", "è", "ë", "ê", "ē", "ė"),
        'i' to listOf("í", "ì", "ï", "î", "ī"),
        'o' to listOf("ó", "ò", "ö", "ô", "õ", "ø", "ō", "œ"),
        'u' to listOf("ú", "ù", "ü", "û", "ū"),
        'c' to listOf("ç", "ć", "č"),
        'n' to listOf("ñ", "ń", "ň"),
        's' to listOf("ß", "ś", "š", "ş"),
        'y' to listOf("ý", "ÿ"),
        'z' to listOf("ž", "ź", "ż"),
        'l' to listOf("ł", "ľ")
    )

    private val hints = mapOf(
        'q' to "1", 'w' to "2", 'e' to "3", 'r' to "4", 't' to "5",
        'y' to "6", 'u' to "7", 'i' to "8", 'o' to "9", 'p' to "0",
        'a' to "@", 's' to "#", 'd' to "$", 'f' to "%", 'g' to "&",
        'h' to "-", 'j' to "+", 'k' to "(", 'l' to ")",
        'z' to "*", 'x' to "\"", 'c' to "'", 'v' to ":", 'b' to ";",
        'n' to "!", 'm' to "?"
    )

    /** Returns the single visible symbol/digit hint for an English letter. */
    fun hint(key: Char): String? = hints[key.lowercaseChar()]

    /**
     * Returns alternate strings in menu order: common Latin accents first,
     * followed by the key hint. Non-letters have no alternate catalog.
     */
    fun choices(key: Char, uppercase: Boolean): List<String> {
        val lower = key.lowercaseChar()
        if (lower !in 'a'..'z') return emptyList()
        val values = buildList {
            addAll(accents[lower].orEmpty())
            hints[lower]?.let(::add)
        }
        return values.map { value ->
            if (uppercase && value.all(Char::isLetter)) value.uppercase(Locale.ROOT) else value
        }.distinct().take(10)
    }
}
