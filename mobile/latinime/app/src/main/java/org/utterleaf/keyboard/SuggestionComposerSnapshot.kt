package org.utterleaf.keyboard

import com.android.inputmethod.latin.WordComposer
import com.android.inputmethod.latin.common.ComposedData
import com.android.inputmethod.latin.common.InputPointers
import java.util.function.BooleanSupplier

/**
 * Immutable decoder input, captured on the composer owner thread before enqueueing.
 * The legacy JNI carrier is mutable, so each access receives its own deep pointer copy.
 */
class SuggestionComposerSnapshot @JvmOverloads constructor(
    composer: WordComposer,
    private val requestCurrent: BooleanSupplier = BooleanSupplier { true }
) {
    private val pointers = InputPointers(composer.inputPointers.pointerSize).apply {
        copy(composer.inputPointers)
    }
    private val typedWord = composer.typedWord
    private val batchMode = composer.isBatchMode
    private val composingWord = composer.isComposingWord
    private val allUpperCase = composer.isAllUpperCase
    private val resumed = composer.isResumed
    private val firstCapitalized = composer.isOrWillBeOnlyFirstCharCapitalized
    private val shiftedNoLock = composer.wasShiftedNoLock()
    private val digits = composer.hasDigits()
    private val mostlyCaps = composer.isMostlyCaps
    private val rejectedSuggestion = composer.rejectedBatchModeSuggestion

    fun getTypedWord(): String = typedWord
    fun isBatchMode(): Boolean = batchMode
    fun isComposingWord(): Boolean = composingWord
    fun isAllUpperCase(): Boolean = allUpperCase
    fun isResumed(): Boolean = resumed
    fun isOrWillBeOnlyFirstCharCapitalized(): Boolean = firstCapitalized
    fun wasShiftedNoLock(): Boolean = shiftedNoLock
    fun hasDigits(): Boolean = digits
    fun isMostlyCaps(): Boolean = mostlyCaps
    fun getRejectedBatchModeSuggestion(): String? = rejectedSuggestion

    fun getComposedDataSnapshot(): ComposedData = object : ComposedData(
        InputPointers(pointers.pointerSize).apply { copy(pointers) }, batchMode, typedWord
    ) {
        override fun isRequestCurrent(): Boolean = requestCurrent.asBoolean
    }
}
