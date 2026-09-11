package org.utterleaf.keyboard

import android.os.Bundle
import android.text.InputType
import android.view.inputmethod.EditorInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KeyboardEditorInfoTest {
    @Test fun nullEditorUsesFrameworkDefaultMetadata() {
        val snapshot = KeyboardEditorInfo.from(null)

        assertEquals(0, snapshot.inputType)
        assertEquals(0, snapshot.imeOptions)
        assertNull(snapshot.privateImeOptions)
        assertNull(snapshot.actionLabel)
    }

    @Test fun captureDetachesMutableLabelAndIgnoresEditorContext() {
        val label = StringBuilder("Search")
        val extras = Bundle().apply { putString("sentinel", "editor-only") }
        val editor = EditorInfo().apply {
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_SEARCH
            privateImeOptions = "private-option"
            actionLabel = label
            packageName = "host.package"
            fieldId = 42
            this.extras = extras
        }

        val snapshot = KeyboardEditorInfo.from(editor)
        label.append(" changed")
        extras.putString("sentinel", "mutated")
        editor.inputType = InputType.TYPE_CLASS_NUMBER
        editor.imeOptions = EditorInfo.IME_ACTION_DONE
        editor.privateImeOptions = "changed-option"
        editor.actionLabel = "changed-label"
        editor.packageName = "other.package"
        editor.fieldId = 99

        assertEquals(InputType.TYPE_CLASS_TEXT, snapshot.inputType)
        assertEquals(EditorInfo.IME_ACTION_SEARCH, snapshot.imeOptions)
        assertEquals("private-option", snapshot.privateImeOptions)
        assertEquals("Search", snapshot.actionLabel)
    }

    @Test fun nullAndEmptyLabelsRemainDistinctAndCarrierHasNoFrameworkReferences() {
        val nullLabel = KeyboardEditorInfo.from(EditorInfo())
        val emptyLabel = KeyboardEditorInfo.from(EditorInfo().apply { actionLabel = "" })

        assertNull(nullLabel.actionLabel)
        assertEquals("", emptyLabel.actionLabel)

        val editorInfoClass = EditorInfo::class.java
        assertTrue(KeyboardEditorInfo::class.java.declaredFields.none {
            editorInfoClass.isAssignableFrom(it.type)
        })
        assertTrue(KeyboardEditorInfo::class.java.declaredFields.none {
            Bundle::class.java.isAssignableFrom(it.type)
        })
    }
}
