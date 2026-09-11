package org.utterleaf.keyboard.next.core

import android.text.InputType
import android.view.inputmethod.EditorInfo

/** Conservative field classification. It retains no editor or host metadata. */
data class FieldPolicy private constructor(
    val sensitive: Boolean,
    val noPersonalizedLearning: Boolean,
    val raw: Boolean,
) {
    val forcedIncognito: Boolean get() = sensitive || noPersonalizedLearning || raw
    val permitsContext: Boolean get() = !sensitive && !raw && !noPersonalizedLearning
    val permitsSuggestions: Boolean get() = permitsContext && !noPersonalizedLearning

    companion object {
        fun from(inputType: Int?, imeOptions: Int): FieldPolicy {
            if (inputType == null) return FieldPolicy(sensitive = true, noPersonalizedLearning = false, raw = false)
            val inputClass = inputType and InputType.TYPE_MASK_CLASS
            val variation = inputType and InputType.TYPE_MASK_VARIATION
            val raw = inputClass == InputType.TYPE_NULL
            val knownText = setOf(
                InputType.TYPE_TEXT_VARIATION_NORMAL, InputType.TYPE_TEXT_VARIATION_URI,
                InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS, InputType.TYPE_TEXT_VARIATION_EMAIL_SUBJECT,
                InputType.TYPE_TEXT_VARIATION_SHORT_MESSAGE, InputType.TYPE_TEXT_VARIATION_LONG_MESSAGE,
                InputType.TYPE_TEXT_VARIATION_PERSON_NAME, InputType.TYPE_TEXT_VARIATION_POSTAL_ADDRESS,
                InputType.TYPE_TEXT_VARIATION_PASSWORD, InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
                InputType.TYPE_TEXT_VARIATION_WEB_EDIT_TEXT, InputType.TYPE_TEXT_VARIATION_FILTER,
                InputType.TYPE_TEXT_VARIATION_PHONETIC, InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS,
                InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,
            )
            val textPassword = variation in setOf(
                InputType.TYPE_TEXT_VARIATION_PASSWORD, InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
                InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,
            )
            val recognized = when (inputClass) {
                InputType.TYPE_CLASS_TEXT -> variation in knownText
                InputType.TYPE_CLASS_NUMBER -> variation in setOf(
                    InputType.TYPE_NUMBER_VARIATION_NORMAL, InputType.TYPE_NUMBER_VARIATION_PASSWORD,
                )
                InputType.TYPE_CLASS_PHONE -> variation == 0
                InputType.TYPE_CLASS_DATETIME -> variation in setOf(
                    InputType.TYPE_DATETIME_VARIATION_NORMAL, InputType.TYPE_DATETIME_VARIATION_DATE,
                    InputType.TYPE_DATETIME_VARIATION_TIME,
                )
                else -> false
            }
            val numberPassword = inputClass == InputType.TYPE_CLASS_NUMBER && variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD
            return FieldPolicy(
                sensitive = !recognized || textPassword || numberPassword,
                noPersonalizedLearning = imeOptions and EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING != 0,
                raw = raw,
            )
        }
    }
}
