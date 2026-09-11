package org.utterleaf.keyboard

import android.view.inputmethod.EditorInfo

/** Immutable keyboard-only copy of framework editor metadata. */
class KeyboardEditorInfo private constructor(
    @JvmField val inputType: Int,
    @JvmField val imeOptions: Int,
    @JvmField val privateImeOptions: String?,
    @JvmField val actionLabel: String?
) {
    companion object {
        @JvmStatic
        fun from(editorInfo: EditorInfo?): KeyboardEditorInfo = KeyboardEditorInfo(
            inputType = editorInfo?.inputType ?: 0,
            imeOptions = editorInfo?.imeOptions ?: 0,
            privateImeOptions = editorInfo?.privateImeOptions,
            actionLabel = editorInfo?.actionLabel?.toString()
        )
    }
}

/** Immutable editor metadata used only to compare deferred framework callbacks. */
class AppliedEditorInfo private constructor(
    @JvmField val inputType: Int,
    @JvmField val imeOptions: Int,
    @JvmField val privateImeOptions: String?
) {
    companion object {
        @JvmStatic
        fun from(editorInfo: EditorInfo?): AppliedEditorInfo? = editorInfo?.let {
            AppliedEditorInfo(
                inputType = it.inputType,
                imeOptions = it.imeOptions,
                privateImeOptions = it.privateImeOptions
            )
        }
    }
}
