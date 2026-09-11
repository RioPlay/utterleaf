package com.android.inputmethod.latin

import android.text.InputType
import android.view.inputmethod.EditorInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.android.inputmethod.latin.common.Constants
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class InputAttributesTest {
    private val imePackage = "org.utterleaf.keyboard.experimental"

    private fun textEditor(privateImeOptions: String?) = EditorInfo().apply {
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        this.privateImeOptions = privateImeOptions
    }

    @Test fun microphoneOptionUsesCapturedExactCommaTokens() {
        val option = "$imePackage.${Constants.ImeOption.NO_MICROPHONE}"
        val editor = textEditor("unrelated,$option,${Constants.ImeOption.NO_MICROPHONE_COMPAT}")

        val attributes = InputAttributes(editor, false, imePackage)
        editor.privateImeOptions = "$imePackage.${Constants.ImeOption.NO_MICROPHONE}Suffix"

        assertFalse(attributes.mShouldShowVoiceInputKey)
        assertTrue(InputAttributes(textEditor("$option-Suffix"), false, imePackage)
            .mShouldShowVoiceInputKey)
    }

    @Test fun inputAttributesDoesNotRetainFrameworkEditorInfo() {
        assertTrue(InputAttributes::class.java.declaredFields.none {
            EditorInfo::class.java.isAssignableFrom(it.type)
        })
    }
}
