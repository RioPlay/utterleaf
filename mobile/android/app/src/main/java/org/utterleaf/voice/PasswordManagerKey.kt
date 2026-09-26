package org.utterleaf.voice

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.provider.Settings

/**
 * The password-manager key offers an explicit route to the user's configured
 * autofill application. It appears only on explicit password fields — never on
 * ordinary text, email or number fields, where a credential shortcut would
 * invite wrong-field use. The keyboard sends no text to the target application;
 * the launch is the whole action.
 */
object PasswordManagerKey {
    /** Mirrors the hidden Settings.Secure autofill key (API 26+). */
    private const val AUTOFILL_SETTING = "autofill_service"

    /** Restricted credential set shared with every other editor policy consumer. */
    fun isPasswordField(inputType: Int?): Boolean = EditorCapabilities.resolve(inputType).sensitive

    /**
     * Launch intent for the configured autofill application, or null when the
     * field is not a password field or no launchable autofill app is configured.
     */
    fun launchIntent(context: Context, inputType: Int?): Intent? {
        return launchIntent(context, EditorCapabilities.resolve(inputType))
    }

    internal fun launchIntent(context: Context, capabilities: EditorCapabilities): Intent? {
        if (!capabilities.sensitive) return null
        val service = Settings.Secure.getString(context.contentResolver, AUTOFILL_SETTING) ?: return null
        val component = ComponentName.unflattenFromString(service) ?: return null
        return context.packageManager.getLaunchIntentForPackage(component.packageName)
    }
}
