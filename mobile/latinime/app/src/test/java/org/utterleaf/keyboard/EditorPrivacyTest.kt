package org.utterleaf.keyboard

import android.text.InputType
import org.junit.Assert.*
import org.junit.Test

class EditorPrivacyTest {
    @Test fun passwordsAndUnclassifiedEditorsDoNotSupplyContext() {
        for (variation in listOf(InputType.TYPE_TEXT_VARIATION_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD, InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD)) {
            assertFalse(EditorPrivacy.allowsContext(InputType.TYPE_CLASS_TEXT or variation))
        }
        assertFalse(EditorPrivacy.allowsContext(InputType.TYPE_NULL))
        assertFalse(EditorPrivacy.allowsContext(InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD))
        assertFalse(EditorPrivacy.allowsContext(InputType.TYPE_CLASS_PHONE))
        assertFalse(EditorPrivacy.allowsContext(InputType.TYPE_CLASS_TEXT or 0xff0))
    }

    @Test fun ordinaryTextFlagsDoNotAccidentallyDisableContext() {
        assertTrue(EditorPrivacy.allowsContext(InputType.TYPE_CLASS_TEXT))
        assertTrue(EditorPrivacy.allowsContext(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE))
        assertTrue(EditorPrivacy.allowsContext(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS))
    }
}
