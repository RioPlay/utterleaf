package com.android.inputmethod.keyboard

import android.text.InputType
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodSubtype
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.android.inputmethod.latin.common.Constants
import com.android.inputmethod.latin.RichInputMethodManager
import com.android.inputmethod.latin.RichInputMethodSubtype
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.utterleaf.keyboard.KeyboardEditorInfo

@RunWith(AndroidJUnit4::class)
class KeyboardEditorMetadataTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Before fun initializeRichInputMethodManager() {
        // Builder.setSubtype may select the no-language subtype for FORCE_ASCII. Initialize
        // the same process singleton LatinIME initializes before looking that subtype up.
        RichInputMethodManager.init(context)
    }

    private fun paramsFor(builder: KeyboardLayoutSet.Builder): KeyboardLayoutSet.Params =
        builder.javaClass.getDeclaredField("mParams").apply { isAccessible = true }
            .get(builder) as KeyboardLayoutSet.Params

    private fun idFor(info: EditorInfo): KeyboardId {
        val params = KeyboardLayoutSet.Params()
        params.mEditorMetadata = KeyboardEditorInfo.from(info)
        params.mSubtype = RichInputMethodSubtype.getNoLanguageSubtype()
        return KeyboardId(KeyboardId.ELEMENT_ALPHABET, params)
    }

    @Test fun builderCapturesMutableFrameworkMetadataBeforeSubtypeSelection() {
        val label = StringBuilder("Review")
        val original = EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            imeOptions = EditorInfo.IME_ACTION_NEXT or EditorInfo.IME_FLAG_NAVIGATE_PREVIOUS
            privateImeOptions = "${context.packageName}.${Constants.ImeOption.FORCE_ASCII}," +
                "${context.packageName}.${Constants.ImeOption.NO_SETTINGS_KEY}"
            actionLabel = label
            packageName = "unrelated.host"
            fieldId = 73
        }
        val builder = KeyboardLayoutSet.Builder(context, original)
        label.append(" changed")
        original.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        original.imeOptions = EditorInfo.IME_ACTION_DONE
        original.privateImeOptions = "changed"
        original.actionLabel = "changed"
        // setSubtype is intentionally after the mutation: it must still read the captured
        // FORCE_ASCII private option, never the live EditorInfo.
        val nonAsciiSubtype = RichInputMethodSubtype.getRichInputMethodSubtype(
            InputMethodSubtype.InputMethodSubtypeBuilder()
                .setSubtypeLocale("zz")
                .setSubtypeMode("keyboard")
                .setIsAsciiCapable(false)
                .build()
        )
        builder.setSubtype(nonAsciiSubtype)
        val params = paramsFor(builder)
        val id = KeyboardId(KeyboardId.ELEMENT_ALPHABET, params)

        assertEquals(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE,
            params.mEditorMetadata.inputType)
        assertEquals(EditorInfo.IME_ACTION_NEXT or EditorInfo.IME_FLAG_NAVIGATE_PREVIOUS,
            params.mEditorMetadata.imeOptions)
        assertTrue(params.mNoSettingsKey)
        assertTrue(params.mSubtype.isNoLanguage)
        assertEquals("Review", params.mEditorMetadata.actionLabel)
        assertTrue(id.isMultiLine)
        assertFalse(id.passwordInput())
        // A custom action label takes precedence over IME_ACTION_NEXT, so the action no
        // longer contributes navigation. The separately captured previous flag still does.
        assertFalse(id.navigateNext())
        assertTrue(id.navigatePrevious())
        assertEquals(com.android.inputmethod.latin.utils.InputTypeUtils.IME_ACTION_CUSTOM_LABEL,
            id.imeAction())
        assertEquals("Review", id.mCustomActionLabel)
    }

    @Test fun nullBuilderUsesThePriorEmptyEditorDefaults() {
        val params = paramsFor(KeyboardLayoutSet.Builder(context, null))

        assertEquals(KeyboardId.MODE_TEXT, params.mMode)
        assertEquals(0, params.mEditorMetadata.inputType)
        assertEquals(0, params.mEditorMetadata.imeOptions)
        assertEquals(null, params.mEditorMetadata.privateImeOptions)
        assertEquals(null, params.mEditorMetadata.actionLabel)
        assertFalse(params.mNoSettingsKey)
    }

    @Test fun actionAndPasswordSemanticsUseOnlySnapshotFields() {
        val noEnter = idFor(EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_NEXT or EditorInfo.IME_FLAG_NO_ENTER_ACTION
            actionLabel = StringBuilder("custom")
        })
        val visiblePassword = idFor(EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
        })
        val password = idFor(EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        })
        val explicitNavigateNext = idFor(EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_DONE or EditorInfo.IME_FLAG_NAVIGATE_NEXT
            actionLabel = StringBuilder("custom")
        })

        assertEquals(EditorInfo.IME_ACTION_NONE, noEnter.imeAction())
        assertTrue(visiblePassword.passwordInput())
        assertTrue(password.passwordInput())
        assertTrue(explicitNavigateNext.navigateNext())
    }

    @Test fun cacheIdentityUsesOnlyKeyboardMetadataAndKeepsEmptyActionLabelDistinct() {
        val first = EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_DONE
            privateImeOptions = "${context.packageName}.${Constants.ImeOption.FORCE_ASCII}"
            actionLabel = StringBuilder("Send")
            packageName = "first.host"
            fieldId = 1
        }
        val second = EditorInfo().apply {
            inputType = first.inputType
            imeOptions = first.imeOptions
            privateImeOptions = first.privateImeOptions
            actionLabel = StringBuilder("Send")
            packageName = "second.host"
            fieldId = 2
        }
        val noLabel = idFor(EditorInfo().apply { inputType = InputType.TYPE_CLASS_TEXT })
        val emptyLabel = idFor(EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT
            actionLabel = StringBuilder()
        })

        assertEquals(idFor(first), idFor(second))
        assertFalse(noLabel == emptyLabel)
        assertEquals("", emptyLabel.mCustomActionLabel)
    }

    @Test fun cachedKeyboardTypesHaveNoFrameworkEditorInfoField() {
        val frameworkEditorInfo = EditorInfo::class.java
        assertTrue(KeyboardEditorInfo::class.java.declaredFields.none {
            frameworkEditorInfo.isAssignableFrom(it.type)
        })
        assertTrue(KeyboardLayoutSet.Params::class.java.declaredFields.none {
            frameworkEditorInfo.isAssignableFrom(it.type)
        })
        assertTrue(KeyboardId::class.java.declaredFields.none {
            frameworkEditorInfo.isAssignableFrom(it.type)
        })

        // Force cache entries retain KeyboardIds, so this structural boundary also covers both
        // the soft map and the forcible cache without changing their retirement policy.
        val cache = KeyboardLayoutSet::class.java.getDeclaredField("sForcibleKeyboardCache")
            .apply { isAccessible = true }.get(null) as Array<*>
        cache.filterNotNull().forEach { keyboard ->
            assertTrue((keyboard as Keyboard).mId.mEditorMetadata is KeyboardEditorInfo)
        }
    }
}
