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

    /**
     * Returns the symbol/digit hint at this letter's position. With the number
     * row shown, the top row hints the mockup's bracket/symbol set so digits
     * are not repeated; with it hidden, digits return so every value stays
     * reachable by hold.
     */
    fun hint(key: Char, numberRowShown: Boolean = false): String? {
        val lower = key.lowercaseChar()
        val hintRows = if (numberRowShown) NUMBER_ROW_ROWS else DIGIT_ROWS
        return rows.zip(hintRows).firstNotNullOfOrNull { (letters, hints) ->
            letters.indexOf(lower).takeIf { it >= 0 }?.let { hints[it].toString() }
        }
    }

    companion object {
        private val DIGIT_ROWS = listOf("1234567890", "@#$%&-+()/", "*\"':;!?")
        private val NUMBER_ROW_ROWS = listOf("~\\|=[]<>{}", "@#$%&-+()/", "*\"':;!?")

        fun fromStored(value: String?) = entries.firstOrNull { it.stored == value } ?: QWERTY
    }
}
