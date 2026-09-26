package org.utterleaf.voice

import android.text.InputType
import android.view.inputmethod.EditorInfo

/** Stable field categories derived only from editor metadata, never editor text. */
internal enum class EditorFieldKind { UNKNOWN, RAW, TEXT, NUMBER, PHONE, DATETIME }

/** The action rendered by the primary key. [imeAction] is null when Enter inserts a newline. */
internal enum class EditorEnterAction(val imeAction: Int?, val label: String) {
    ENTER(null, "Enter"),
    GO(EditorInfo.IME_ACTION_GO, "Go"),
    SEARCH(EditorInfo.IME_ACTION_SEARCH, "Search"),
    SEND(EditorInfo.IME_ACTION_SEND, "Send"),
    NEXT(EditorInfo.IME_ACTION_NEXT, "Next"),
    DONE(EditorInfo.IME_ACTION_DONE, "Done"),
    PREVIOUS(EditorInfo.IME_ACTION_PREVIOUS, "Previous"),
}

/**
 * Metadata eligibility, not a claim that the host supports a clipboard command.
 * [preview] is policy for a future explicit preview; no preview surface or passive
 * clipboard read exists. It must never authorize background clipboard access.
 */
internal data class EditorClipboardCapabilities(
    val copy: Boolean,
    val cut: Boolean,
    val paste: Boolean,
    val preview: Boolean,
) {
    companion object {
        val NONE = EditorClipboardCapabilities(copy = false, cut = false, paste = false, preview = false)
        val EXPLICIT = EditorClipboardCapabilities(copy = true, cut = true, paste = true, preview = true)
        val SENSITIVE = EditorClipboardCapabilities(copy = false, cut = false, paste = true, preview = false)
    }
}

/**
 * One immutable interpretation of Android editor metadata for an input session.
 *
 * This value contains no editor contents or application identity. Metadata only
 * describes expected support: every host operation must still handle rejection.
 */
internal data class EditorCapabilities(
    val fieldKind: EditorFieldKind,
    val sensitive: Boolean,
    val multiline: Boolean,
    val numeric: Boolean,
    val email: Boolean,
    val uri: Boolean,
    val phone: Boolean,
    val search: Boolean,
    val enterAction: EditorEnterAction,
    val complexEditing: Boolean,
    val suggestions: Boolean,
    val selection: Boolean,
    val dictation: Boolean,
    val clipboard: EditorClipboardCapabilities,
    val privateDraft: Boolean,
    val emoji: Boolean,
    val surroundingText: Boolean,
) {
    val raw: Boolean get() = fieldKind == EditorFieldKind.RAW
    val knownEditable: Boolean get() =
        fieldKind != EditorFieldKind.UNKNOWN && fieldKind != EditorFieldKind.RAW

    companion object {
        fun from(info: EditorInfo?): EditorCapabilities =
            if (info == null) resolve(null) else resolve(info.inputType, info.imeOptions)

        fun resolve(
            inputType: Int?,
            imeOptions: Int = EditorInfo.IME_ACTION_NONE,
        ): EditorCapabilities {
            val cls = inputType?.and(InputType.TYPE_MASK_CLASS)
            val variation = inputType?.and(InputType.TYPE_MASK_VARIATION)
            val fieldKind = when {
                inputType == null -> EditorFieldKind.UNKNOWN
                inputType == InputType.TYPE_NULL -> EditorFieldKind.RAW
                cls == InputType.TYPE_CLASS_TEXT -> EditorFieldKind.TEXT
                cls == InputType.TYPE_CLASS_NUMBER -> EditorFieldKind.NUMBER
                cls == InputType.TYPE_CLASS_PHONE -> EditorFieldKind.PHONE
                cls == InputType.TYPE_CLASS_DATETIME -> EditorFieldKind.DATETIME
                else -> EditorFieldKind.UNKNOWN
            }
            val sensitive = (fieldKind == EditorFieldKind.TEXT && (variation ==
                InputType.TYPE_TEXT_VARIATION_PASSWORD || variation ==
                InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD || variation ==
                InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD)) || (fieldKind == EditorFieldKind.NUMBER &&
                variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD)
            val knownEditable = fieldKind != EditorFieldKind.UNKNOWN && fieldKind != EditorFieldKind.RAW
            val complexEditing = knownEditable && !sensitive
            val actionCode = imeOptions and EditorInfo.IME_MASK_ACTION
            val enterAction = if (!knownEditable ||
                imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION != 0) {
                EditorEnterAction.ENTER
            } else when (actionCode) {
                EditorInfo.IME_ACTION_GO -> EditorEnterAction.GO
                EditorInfo.IME_ACTION_SEARCH -> EditorEnterAction.SEARCH
                EditorInfo.IME_ACTION_SEND -> EditorEnterAction.SEND
                EditorInfo.IME_ACTION_NEXT -> EditorEnterAction.NEXT
                EditorInfo.IME_ACTION_DONE -> EditorEnterAction.DONE
                EditorInfo.IME_ACTION_PREVIOUS -> EditorEnterAction.PREVIOUS
                else -> EditorEnterAction.ENTER
            }
            val text = fieldKind == EditorFieldKind.TEXT
            // IME_MULTI_LINE changes fullscreen-IME presentation only; it does
            // not mean the host field itself accepts newline characters.
            val multiline = text && inputType!! and InputType.TYPE_TEXT_FLAG_MULTI_LINE != 0
            val email = text && (variation == InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS ||
                variation == InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS)
            val uri = text && variation == InputType.TYPE_TEXT_VARIATION_URI
            // English word completion inserts prose spacing, which is unsafe for
            // literal address fields. Search and filter fields can still contain prose.
            val suggestions = text && !sensitive && !email && !uri &&
                inputType!! and (InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS or
                    InputType.TYPE_TEXT_FLAG_AUTO_COMPLETE) == 0
            val clipboard = when {
                !knownEditable -> EditorClipboardCapabilities.NONE
                sensitive -> EditorClipboardCapabilities.SENSITIVE
                else -> EditorClipboardCapabilities.EXPLICIT
            }
            return EditorCapabilities(
                fieldKind = fieldKind,
                sensitive = sensitive,
                multiline = multiline,
                numeric = fieldKind == EditorFieldKind.NUMBER || fieldKind == EditorFieldKind.DATETIME,
                email = email,
                uri = uri,
                phone = fieldKind == EditorFieldKind.PHONE,
                search = knownEditable && (actionCode == EditorInfo.IME_ACTION_SEARCH ||
                    (text && variation == InputType.TYPE_TEXT_VARIATION_FILTER)),
                enterAction = enterAction,
                complexEditing = complexEditing,
                suggestions = suggestions,
                selection = knownEditable,
                dictation = complexEditing,
                clipboard = clipboard,
                privateDraft = complexEditing,
                emoji = knownEditable && !sensitive,
                surroundingText = complexEditing,
            )
        }
    }
}
