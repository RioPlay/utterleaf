package org.utterleaf.voice

import android.text.InputType
import android.view.inputmethod.EditorInfo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EditorCapabilitiesTest {
    private data class FieldCase(
        val name: String,
        val inputType: Int?,
        val imeOptions: Int = EditorInfo.IME_ACTION_NONE,
        val fieldKind: EditorFieldKind,
        val sensitive: Boolean = false,
        val multiline: Boolean = false,
        val numeric: Boolean = false,
        val email: Boolean = false,
        val uri: Boolean = false,
        val phone: Boolean = false,
        val search: Boolean = false,
    )

    @Test fun fieldMetadataIsResolvedFromOneTable() {
        val text = InputType.TYPE_CLASS_TEXT
        val cases = listOf(
            FieldCase("missing editor", null, fieldKind = EditorFieldKind.UNKNOWN),
            FieldCase("raw editor", InputType.TYPE_NULL, fieldKind = EditorFieldKind.RAW),
            FieldCase("unknown class", 0x0f, fieldKind = EditorFieldKind.UNKNOWN),
            FieldCase("ordinary text", text, fieldKind = EditorFieldKind.TEXT),
            FieldCase("number", InputType.TYPE_CLASS_NUMBER, fieldKind = EditorFieldKind.NUMBER,
                numeric = true),
            FieldCase("datetime", InputType.TYPE_CLASS_DATETIME, fieldKind = EditorFieldKind.DATETIME,
                numeric = true),
            FieldCase("phone", InputType.TYPE_CLASS_PHONE, fieldKind = EditorFieldKind.PHONE,
                phone = true),
            FieldCase("email", text or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS,
                fieldKind = EditorFieldKind.TEXT, email = true),
            FieldCase("web email", text or InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS,
                fieldKind = EditorFieldKind.TEXT, email = true),
            FieldCase("URI", text or InputType.TYPE_TEXT_VARIATION_URI,
                fieldKind = EditorFieldKind.TEXT, uri = true),
            FieldCase("filter", text or InputType.TYPE_TEXT_VARIATION_FILTER,
                fieldKind = EditorFieldKind.TEXT, search = true),
            FieldCase("search", text, EditorInfo.IME_ACTION_SEARCH,
                fieldKind = EditorFieldKind.TEXT, search = true),
            FieldCase("multiline", text or InputType.TYPE_TEXT_FLAG_MULTI_LINE,
                fieldKind = EditorFieldKind.TEXT, multiline = true),
            FieldCase("fullscreen IME multiline hint", text or InputType.TYPE_TEXT_FLAG_IME_MULTI_LINE,
                fieldKind = EditorFieldKind.TEXT),
            FieldCase("long message", text or InputType.TYPE_TEXT_VARIATION_LONG_MESSAGE,
                fieldKind = EditorFieldKind.TEXT),
            FieldCase("long multiline message", text or InputType.TYPE_TEXT_VARIATION_LONG_MESSAGE or
                InputType.TYPE_TEXT_FLAG_MULTI_LINE, fieldKind = EditorFieldKind.TEXT, multiline = true),
        )

        cases.forEach { case ->
            val actual = EditorCapabilities.resolve(case.inputType, case.imeOptions)
            assertEquals("${case.name} kind", case.fieldKind, actual.fieldKind)
            assertEquals("${case.name} sensitive", case.sensitive, actual.sensitive)
            assertEquals("${case.name} multiline", case.multiline, actual.multiline)
            assertEquals("${case.name} numeric", case.numeric, actual.numeric)
            assertEquals("${case.name} email", case.email, actual.email)
            assertEquals("${case.name} URI", case.uri, actual.uri)
            assertEquals("${case.name} phone", case.phone, actual.phone)
            assertEquals("${case.name} search", case.search, actual.search)
            if (case.fieldKind == EditorFieldKind.UNKNOWN || case.fieldKind == EditorFieldKind.RAW) {
                assertNoEditorFeatures(case.name, actual)
            } else {
                assertTrue("${case.name} should allow explicit emoji input", actual.emoji)
            }
        }
    }

    @Test fun everyPasswordKindFailsClosedWithoutBlockingPasteOrSelection() {
        val text = InputType.TYPE_CLASS_TEXT
        val cases = listOf(
            "text password" to (text or InputType.TYPE_TEXT_VARIATION_PASSWORD),
            "visible password" to (text or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD),
            "web password" to (text or InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD),
            "number password" to
                (InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD),
        )

        cases.forEach { (name, inputType) ->
            val actual = EditorCapabilities.resolve(inputType)
            assertEquals(name, if (name == "number password") EditorFieldKind.NUMBER else EditorFieldKind.TEXT,
                actual.fieldKind)
            assertTrue("$name should be sensitive", actual.sensitive)
            assertEquals("$name numeric", name == "number password", actual.numeric)
            assertTrue("$name keeps explicit selection available", actual.selection)
            assertFalse("$name must not inspect complex editor context", actual.complexEditing)
            assertFalse("$name must not inspect surrounding text", actual.surroundingText)
            assertFalse("$name must not offer suggestions", actual.suggestions)
            assertFalse("$name must not allow dictation", actual.dictation)
            assertFalse("$name must not allow a private draft", actual.privateDraft)
            assertEquals("$name clipboard policy",
                EditorClipboardCapabilities(copy = false, cut = false, paste = true, preview = false),
                actual.clipboard)
            assertFalse("$name must not expose emoji browsing", actual.emoji)
        }
    }

    @Test fun ordinaryTextKeepsTheFullSafeEditorContract() {
        val actual = EditorCapabilities.resolve(InputType.TYPE_CLASS_TEXT)

        assertEquals(EditorFieldKind.TEXT, actual.fieldKind)
        assertFalse(actual.sensitive)
        assertTrue(actual.complexEditing)
        assertTrue(actual.suggestions)
        assertTrue(actual.selection)
        assertTrue(actual.dictation)
        assertEquals(EditorClipboardCapabilities(copy = true, cut = true, paste = true, preview = true),
            actual.clipboard)
        assertTrue(actual.privateDraft)
        assertTrue(actual.emoji)
        assertTrue(actual.surroundingText)
    }

    @Test fun editorSuggestionFlagsDisableOnlySuggestionEligibility() {
        val ordinary = EditorCapabilities.resolve(InputType.TYPE_CLASS_TEXT)
        val noSuggestions = EditorCapabilities.resolve(
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS)
        val appCompletions = EditorCapabilities.resolve(
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_AUTO_COMPLETE)

        assertTrue(ordinary.suggestions)
        for (suppressed in listOf(noSuggestions, appCompletions)) {
            assertFalse(suppressed.suggestions)
            assertEquals(ordinary.copy(suggestions = false), suppressed)
        }
    }

    @Test fun literalAddressFieldsSuppressEnglishSuggestionsButProseSearchKeepsThem() {
        val text = InputType.TYPE_CLASS_TEXT
        val cases = listOf(
            Triple("ordinary prose", text, true),
            Triple("search action", text, true),
            Triple("filter field", text or InputType.TYPE_TEXT_VARIATION_FILTER, true),
            Triple("email address", text or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS, false),
            Triple("web email address", text or InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS, false),
            Triple("URI", text or InputType.TYPE_TEXT_VARIATION_URI, false),
            Triple("number", InputType.TYPE_CLASS_NUMBER, false),
            Triple("phone", InputType.TYPE_CLASS_PHONE, false),
            Triple("datetime", InputType.TYPE_CLASS_DATETIME, false),
        )

        cases.forEach { (name, inputType, expected) ->
            val imeOptions = if (name == "search action") EditorInfo.IME_ACTION_SEARCH
                else EditorInfo.IME_ACTION_NONE
            assertEquals("$name suggestion eligibility", expected,
                EditorCapabilities.resolve(inputType, imeOptions).suggestions)
        }
    }

    @Test fun enterActionsMaskFlagsAndUnsupportedValuesFallBackToEnter() {
        data class ActionCase(
            val name: String,
            val imeOptions: Int,
            val expected: EditorEnterAction,
        )

        val cases = listOf(
            ActionCase("none", EditorInfo.IME_ACTION_NONE, EditorEnterAction.ENTER),
            ActionCase("unspecified", EditorInfo.IME_ACTION_UNSPECIFIED, EditorEnterAction.ENTER),
            ActionCase("go", EditorInfo.IME_ACTION_GO, EditorEnterAction.GO),
            ActionCase("search", EditorInfo.IME_ACTION_SEARCH, EditorEnterAction.SEARCH),
            ActionCase("send", EditorInfo.IME_ACTION_SEND, EditorEnterAction.SEND),
            ActionCase("next", EditorInfo.IME_ACTION_NEXT, EditorEnterAction.NEXT),
            ActionCase("done", EditorInfo.IME_ACTION_DONE, EditorEnterAction.DONE),
            ActionCase("previous", EditorInfo.IME_ACTION_PREVIOUS, EditorEnterAction.PREVIOUS),
            ActionCase("masked flags", EditorInfo.IME_ACTION_SEND or EditorInfo.IME_FLAG_NAVIGATE_NEXT,
                EditorEnterAction.SEND),
            ActionCase("no enter action", EditorInfo.IME_ACTION_SEARCH or EditorInfo.IME_FLAG_NO_ENTER_ACTION,
                EditorEnterAction.ENTER),
            ActionCase("unsupported action", 0x08, EditorEnterAction.ENTER),
        )

        cases.forEach { case ->
            assertEquals(case.name, case.expected,
                EditorCapabilities.resolve(InputType.TYPE_CLASS_TEXT, case.imeOptions).enterAction)
        }
    }

    @Test fun rawAndUnknownEditorsDoNotAdvertiseEditorActions() {
        for (inputType in listOf(null, InputType.TYPE_NULL, 0x0f)) {
            for (action in listOf(EditorInfo.IME_ACTION_SEND, EditorInfo.IME_ACTION_SEARCH)) {
                val actual = EditorCapabilities.resolve(inputType, action)
                assertEquals("inputType=$inputType action=$action", EditorEnterAction.ENTER,
                    actual.enterAction)
                assertFalse(actual.search)
                assertNoEditorFeatures("inputType=$inputType action=$action", actual)
            }
        }
    }

    @Test fun enterActionMetadataMatchesTheAndroidContract() {
        val cases = listOf(
            Triple(EditorEnterAction.ENTER, null, "Enter"),
            Triple(EditorEnterAction.GO, EditorInfo.IME_ACTION_GO, "Go"),
            Triple(EditorEnterAction.SEARCH, EditorInfo.IME_ACTION_SEARCH, "Search"),
            Triple(EditorEnterAction.SEND, EditorInfo.IME_ACTION_SEND, "Send"),
            Triple(EditorEnterAction.NEXT, EditorInfo.IME_ACTION_NEXT, "Next"),
            Triple(EditorEnterAction.DONE, EditorInfo.IME_ACTION_DONE, "Done"),
            Triple(EditorEnterAction.PREVIOUS, EditorInfo.IME_ACTION_PREVIOUS, "Previous"),
        )

        cases.forEach { (action, imeAction, label) ->
            assertEquals("$action IME action", imeAction, action.imeAction)
            assertEquals("$action label", label, action.label)
        }
    }

    private fun assertNoEditorFeatures(name: String, actual: EditorCapabilities) {
        assertFalse("$name complex editing", actual.complexEditing)
        assertFalse("$name suggestions", actual.suggestions)
        assertFalse("$name selection", actual.selection)
        assertFalse("$name dictation", actual.dictation)
        assertEquals("$name clipboard policy",
            EditorClipboardCapabilities(copy = false, cut = false, paste = false, preview = false),
            actual.clipboard)
        assertFalse("$name private draft", actual.privateDraft)
        assertFalse("$name emoji", actual.emoji)
        assertFalse("$name surrounding text", actual.surroundingText)
    }
}
