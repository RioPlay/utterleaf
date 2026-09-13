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
    val punctuation = listOf(",", "?", "!", "'", "\"", ":", ";", "…", "—")
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

    /** Returns the symbol/digit hint at this letter's position in the selected layout. */
    fun hint(key: Char, layout: LetterLayout = LetterLayout.QWERTY): String? = layout.hint(key)

    /**
     * Returns alternate strings in menu order: common Latin accents first,
     * followed by the key hint. Non-letters have no alternate catalog.
     */
    fun choices(key: Char, uppercase: Boolean, layout: LetterLayout = LetterLayout.QWERTY): List<String> {
        val lower = key.lowercaseChar()
        if (lower !in 'a'..'z') return emptyList()
        val values = accents[lower].orEmpty().map { value ->
            if (uppercase && value.all(Char::isLetter)) value.uppercase(Locale.ROOT) else value
        }.distinct()
        val hint = hint(lower, layout)
        return (values.filterNot { it == hint }.take(9) + listOfNotNull(hint)).distinct()
    }
}
