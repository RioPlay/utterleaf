package org.utterleaf.keyboard.next.ui

import java.util.Locale
import java.util.Collections

/** Reviewed Latin alternates for the initial English layout; no lexical learning. */
object AlternateCharacters {
    private val choices = mapOf(
        "a" to listOf("á", "à", "â", "ä", "ã", "å", "æ"), "c" to listOf("ç", "ć", "č"),
        "e" to listOf("é", "è", "ê", "ë", "ē"), "i" to listOf("í", "ì", "î", "ï", "ī"),
        "n" to listOf("ñ", "ń"), "o" to listOf("ó", "ò", "ô", "ö", "õ", "ø", "œ"),
        "s" to listOf("ß", "ś", "š"), "u" to listOf("ú", "ù", "û", "ü", "ū"),
        "y" to listOf("ý", "ÿ"), "z" to listOf("ź", "ž"),
        "." to listOf("…", "!", "?"), "," to listOf(",", ";", ":"),
    )
    fun forBase(base: String): List<String> = choices[base.lowercase(Locale.ROOT)]?.let { Collections.unmodifiableList(it) } ?: emptyList()
}
