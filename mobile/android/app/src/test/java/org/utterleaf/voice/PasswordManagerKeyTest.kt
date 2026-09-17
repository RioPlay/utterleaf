package org.utterleaf.voice

import android.text.InputType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The credential shortcut must qualify only explicit password fields. */
class PasswordManagerKeyTest {
    private val text = InputType.TYPE_CLASS_TEXT

    @Test fun onlyExplicitPasswordVariationsQualify() {
        assertTrue(PasswordManagerKey.isPasswordField(
            text or InputType.TYPE_TEXT_VARIATION_PASSWORD))
        assertTrue(PasswordManagerKey.isPasswordField(
            text or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD))
        assertTrue(PasswordManagerKey.isPasswordField(
            text or InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD))
        assertTrue(PasswordManagerKey.isPasswordField(
            InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD))
    }

    @Test fun everyOtherFieldIsRefused() {
        assertFalse(PasswordManagerKey.isPasswordField(null))
        assertFalse(PasswordManagerKey.isPasswordField(0))
        assertFalse(PasswordManagerKey.isPasswordField(text))
        assertFalse(PasswordManagerKey.isPasswordField(
            text or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS))
        assertFalse(PasswordManagerKey.isPasswordField(
            text or InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS))
        assertFalse(PasswordManagerKey.isPasswordField(
            text or InputType.TYPE_TEXT_VARIATION_URI))
        assertFalse(PasswordManagerKey.isPasswordField(
            text or InputType.TYPE_TEXT_VARIATION_LONG_MESSAGE))
        assertFalse(PasswordManagerKey.isPasswordField(
            text or InputType.TYPE_TEXT_VARIATION_PERSON_NAME))
        assertFalse(PasswordManagerKey.isPasswordField(InputType.TYPE_CLASS_NUMBER))
        assertFalse(PasswordManagerKey.isPasswordField(InputType.TYPE_CLASS_DATETIME))
        assertFalse(PasswordManagerKey.isPasswordField(InputType.TYPE_CLASS_PHONE))
    }

    @Test fun classificationAgreesWithTheSensitiveFieldGate() {
        // Every password field is a restricted field for speech and drafts.
        for (variation in listOf(InputType.TYPE_TEXT_VARIATION_PASSWORD,
                InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
                InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD)) {
            val type = text or variation
            assertTrue(PasswordManagerKey.isPasswordField(type))
            assertFalse(VoiceIme.safeField(type))
        }
        val numberPassword = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
        assertTrue(PasswordManagerKey.isPasswordField(numberPassword))
        assertFalse(VoiceIme.safeField(numberPassword))
        // Ordinary text stays on the safe side of both gates.
        assertFalse(PasswordManagerKey.isPasswordField(text))
        assertTrue(VoiceIme.safeField(text))
    }
}
