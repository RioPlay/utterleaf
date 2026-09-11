package org.utterleaf.keyboard.next.core

import android.text.InputType
import android.view.inputmethod.EditorInfo
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FieldPolicyTest {
    @Test fun nullAndRawInputsForceIncognito() {
        assertTrue(FieldPolicy.from(null, 0).forcedIncognito)
        assertTrue(FieldPolicy.from(InputType.TYPE_NULL, 0).forcedIncognito)
    }

    @Test fun passwordAndNoLearningAreConservative() {
        assertTrue(FieldPolicy.from(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD, 0).sensitive)
        val noLearning = FieldPolicy.from(InputType.TYPE_CLASS_TEXT, EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING)
        assertTrue(noLearning.forcedIncognito)
        assertFalse(noLearning.permitsContext)
        assertFalse(noLearning.permitsSuggestions)
    }

    @Test fun ordinaryTextCanUseBoundedContext() {
        val policy = FieldPolicy.from(InputType.TYPE_CLASS_TEXT, 0)
        assertFalse(policy.forcedIncognito)
        assertTrue(policy.permitsContext)
        assertTrue(policy.permitsSuggestions)
    }

    @Test fun unrecognizedMetadataIsSensitive() {
        val unknownClass = FieldPolicy.from(0x0f, 0)
        val unknownTextVariation = FieldPolicy.from(InputType.TYPE_CLASS_TEXT or 0x0f0, 0)
        assertTrue(unknownClass.sensitive)
        assertTrue(unknownTextVariation.sensitive)
        assertFalse(unknownTextVariation.permitsContext)
    }

    @Test fun allPasswordVariantsAreSensitive() {
        for (variation in listOf(
            InputType.TYPE_TEXT_VARIATION_PASSWORD, InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,
        )) assertTrue(FieldPolicy.from(InputType.TYPE_CLASS_TEXT or variation, 0).sensitive)
        assertTrue(FieldPolicy.from(
            InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD,
            0,
        ).sensitive)
    }
}
