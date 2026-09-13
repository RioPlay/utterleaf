package org.utterleaf.voice

import java.text.Normalizer

/** Small reviewed Latin dead-mark table. It contains no words, language model or user data. */
enum class LatinComposeMark(
    val label: String,
    val symbol: String,
    internal val combining: Char,
    internal val bases: String,
) {
    ACUTE("Acute", "´", '\u0301', "aeiouycnsz"),
    GRAVE("Grave", "`", '\u0300', "aeiou"),
    DIAERESIS("Diaeresis", "¨", '\u0308', "aeiouy"),
    CIRCUMFLEX("Circumflex", "^", '\u0302', "aeiou"),
    TILDE("Tilde", "~", '\u0303', "aon"),
    RING("Ring", "°", '\u030a', "a"),
    CEDILLA("Cedilla", "¸", '\u0327', "cs"),
    MACRON("Macron", "¯", '\u0304', "aeiou"),
    CARON("Caron", "ˇ", '\u030c', "cnszl"),
    DOT_ABOVE("Dot above", "˙", '\u0307', "ez"),
}

object LatinCompose {
    /** Returns exactly one NFC code point for a declared pair, or null without partial output. */
    fun compose(mark: LatinComposeMark, base: Char, uppercase: Boolean): String? {
        val declared = mark.bases.firstOrNull { base == it || base == it.uppercaseChar() } ?: return null
        val cased = if (uppercase) declared.uppercaseChar() else declared
        val result = Normalizer.normalize("$cased${mark.combining}", Normalizer.Form.NFC)
        return result.takeIf { it.codePointCount(0, it.length) == 1 }
    }
}
