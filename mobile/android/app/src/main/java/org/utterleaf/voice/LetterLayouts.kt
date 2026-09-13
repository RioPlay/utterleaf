package org.utterleaf.voice

/** Original fixed Latin letter positions. This does not select a language model. */
enum class LetterLayout(
    val stored: String,
    val label: String,
    val top: String,
    val home: String,
    val bottom: String,
) {
    QWERTY("qwerty", "QWERTY", "qwertyuiop", "asdfghjkl", "zxcvbnm"),
    QWERTZ("qwertz", "QWERTZ", "qwertzuiop", "asdfghjkl", "yxcvbnm"),
    AZERTY("azerty", "AZERTY", "azertyuiop", "qsdfghjklm", "wxcvbn");

    val rows: List<String> get() = listOf(top, home, bottom)

    fun hint(key: Char): String? {
        val lower = key.lowercaseChar()
        return rows.zip(HINT_ROWS).firstNotNullOfOrNull { (letters, hints) ->
            letters.indexOf(lower).takeIf { it >= 0 }?.let { hints[it].toString() }
        }
    }

    companion object {
        private val HINT_ROWS = listOf("1234567890", "@#$%&-+()/", "*\"':;!?")

        fun fromStored(value: String?) = entries.firstOrNull { it.stored == value } ?: QWERTY
    }
}
