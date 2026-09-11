package org.utterleaf.keyboard

import android.view.inputmethod.EditorInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.android.inputmethod.keyboard.KeyboardId
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AppliedEditorInfoTest {
    @Test
    fun snapshotKeepsAllComparedFieldsAfterFrameworkInfoMutates() {
        val editor = EditorInfo().apply {
            inputType = 0x21
            imeOptions = EditorInfo.IME_ACTION_SEARCH
            privateImeOptions = "original-private"
        }
        val snapshot = AppliedEditorInfo.from(editor)

        editor.inputType = 0x12
        editor.imeOptions = EditorInfo.IME_ACTION_DONE
        editor.privateImeOptions = "changed-private"

        assertTrue(snapshot != null)
        assertTrue(KeyboardId.equivalentEditorInfoForKeyboardSnapshot(
            EditorInfo().apply {
                inputType = 0x21
                imeOptions = EditorInfo.IME_ACTION_SEARCH
                privateImeOptions = "original-private"
            }, snapshot))

        editor.inputType = 0x21
        editor.imeOptions = EditorInfo.IME_ACTION_SEARCH
        editor.privateImeOptions = "original-private"
        assertTrue(KeyboardId.equivalentEditorInfoForKeyboardSnapshot(editor, snapshot))

        editor.inputType = 0x12
        assertFalse(KeyboardId.equivalentEditorInfoForKeyboardSnapshot(editor, snapshot))
        editor.inputType = 0x21
        editor.imeOptions = EditorInfo.IME_ACTION_DONE
        assertFalse(KeyboardId.equivalentEditorInfoForKeyboardSnapshot(editor, snapshot))
        editor.imeOptions = EditorInfo.IME_ACTION_SEARCH
        editor.privateImeOptions = "changed-private"
        assertFalse(KeyboardId.equivalentEditorInfoForKeyboardSnapshot(editor, snapshot))
    }

    @Test
    fun comparatorDistinguishesNullFromZeroValuedEditorInfo() {
        val zeroEditor = EditorInfo()
        val zeroSnapshot = AppliedEditorInfo.from(zeroEditor)

        assertTrue(KeyboardId.equivalentEditorInfoForKeyboardSnapshot(null, null))
        assertFalse(KeyboardId.equivalentEditorInfoForKeyboardSnapshot(null, zeroSnapshot))
        assertFalse(KeyboardId.equivalentEditorInfoForKeyboardSnapshot(zeroEditor, null))
    }

    @Test
    fun snapshotHasNoFrameworkEditorInfoReference() {
        val editorInfoClass = EditorInfo::class.java
        assertTrue(AppliedEditorInfo::class.java.declaredFields.none {
            editorInfoClass.isAssignableFrom(it.type)
        })
    }
}
