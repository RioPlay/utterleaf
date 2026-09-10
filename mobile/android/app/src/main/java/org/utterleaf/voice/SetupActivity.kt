package org.utterleaf.voice

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.*
import java.util.Locale

class SetupActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var keyboardStatus: TextView
    private lateinit var voiceStatus: TextView
    private lateinit var companionStatus: TextView
    private lateinit var enableKeyboard: Button
    private lateinit var chooseKeyboard: Button
    private lateinit var modelDetails: TextView
    private lateinit var downloadModel: Button
    private lateinit var importModel: Button
    private var selectedModel = ModelStore.catalog.first()
    private var importPending = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        selectedModel = ModelStore.catalog.firstOrNull { it.id == savedInstanceState?.getString("model") }
            ?: ModelStore.installed(noBackupFilesDir) ?: ModelStore.catalog.first()
        importPending = savedInstanceState?.getBoolean("importPending") ?: false
        val column = Ui.column(this)
        column.addView(Ui.mascot(this))
        column.addView(Ui.title(this, "Make yourself at home."))
        column.addView(Ui.text(this, "Utterleaf Keyboard · Android preview", 18f))
        column.addView(Ui.text(this, "Start typing in two steps. Add offline English dictation whenever you want. No Internet permission, accounts, or saved recordings."))
        column.addView(Ui.title(this, "Your keyboard"))
        keyboardStatus = Ui.text(this, "")
        column.addView(keyboardStatus)
        enableKeyboard = Ui.button(this, "1 · Enable Utterleaf Keyboard") {
            startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
        }
        column.addView(enableKeyboard)
        chooseKeyboard = Ui.button(this, "2 · Choose Utterleaf Keyboard") {
            (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
        }
        column.addView(chooseKeyboard)
        column.addView(Ui.text(this, "Then open any app and tap a text field. Typing needs neither a speech model nor microphone permission."))
        column.addView(Ui.button(this, "Keyboard preferences and preview") { startActivity(Intent(this, KeyboardSettingsActivity::class.java)) })
        status = Ui.text(this, "")
        status.accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        column.addView(status)

        column.addView(Ui.title(this, "Optional · offline voice"))
        voiceStatus = Ui.text(this, "")
        column.addView(voiceStatus)
        column.addView(Ui.text(this, "Choose an English model, import its verified file, then allow your microphone. Use the keyboard's Voice button to dictate; no extra keyboard is required."))
        column.addView(Ui.text(this, "1 · Add a speech model", 19f))
        column.addView(Ui.text(this, "One model is kept at a time. Larger models need more storage, RAM and processing time; speed and accuracy depend on your phone and speech. All three options are English only."))
        importModel = Ui.button(this, "Import a model") {
            importPending = true
            try { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE); type = "*/*"
            }, 10) } catch (_: android.content.ActivityNotFoundException) {
                importPending = false
                status.text = "No document picker is available."
            }
        }
        column.addView(importModel)
        column.addView(Ui.text(this, "Already downloaded a model? Import identifies tiny.en, base.en or small.en automatically and verifies the file. Need a download? Choose an option below; this only changes the browser link."))
        val choices = RadioGroup(this)
        ModelStore.catalog.forEach { spec ->
            choices.addView(RadioButton(this).apply {
                id = View.generateViewId()
                text = "${spec.id} · ${megabytes(spec.size)} MB\n${spec.description}"
                setTextColor(Ui.ink)
                buttonTintList = android.content.res.ColorStateList.valueOf(Ui.green)
                minHeight = Ui.dp(this@SetupActivity, 56)
                setPadding(0, Ui.dp(this@SetupActivity, 4), 0, Ui.dp(this@SetupActivity, 4))
                isChecked = spec == selectedModel
                setOnCheckedChangeListener { _, checked ->
                    if (checked) { selectedModel = spec; refreshModelChoice() }
                }
            })
        }
        column.addView(choices)
        modelDetails = Ui.text(this, "")
        column.addView(modelDetails)
        downloadModel = Ui.button(this, "") {
            val spec = selectedModel
            AlertDialog.Builder(this).setTitle("Download ${spec.id} in your browser?")
                .setMessage("Your browser will connect to Hugging Face for ${spec.filename} (${megabytes(spec.size)} MB). Utterleaf does not download files itself. Return here to import the downloaded file.")
                .setNegativeButton("Cancel", null).setPositiveButton("Open browser") { _, _ ->
                    try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(spec.url))) }
                    catch (_: android.content.ActivityNotFoundException) { status.text = "No browser available. Transfer ${spec.filename} from another device, then import it here." }
                }.show()
        }
        column.addView(downloadModel)
        refreshModelChoice()
        column.addView(Ui.text(this, "2 · Allow your microphone", 19f))
        column.addView(Ui.button(this, "Allow microphone") {
            if (microphoneAllowed()) status.text = "Microphone permission is already allowed. Recording starts only after you tap Speak."
            else requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 11)
        })
        column.addView(Ui.button(this, "Open app permissions") {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        })
        column.addView(Ui.text(this, "3 · Try it in a text field", 19f))
        column.addView(Ui.text(this, "Tap Dictate on Utterleaf Keyboard to start recording, then Stop to review. In the separate voice provider, tap Speak first. Edit transcript lets you make changes before Insert. Optional hold mode inserts after release and recognition. Each take has a 120-second limit. Preview clears after two minutes unless you choose Keep reviewing, and immediately when you leave or change fields. Password typing works; dictation is disabled in password fields."))
        column.addView(Ui.button(this, "Delete imported model") {
            AlertDialog.Builder(this).setTitle("Delete the model?").setMessage("Typing will still work. Import a model again whenever you want to dictate.")
                .setNegativeButton("Cancel", null).setPositiveButton("Delete") { _, _ ->
                    if (WorkLease.acquire()) {
                        try { status.text = if (!ModelStore.file(noBackupFilesDir).exists() || ModelStore.file(noBackupFilesDir).delete()) "Model deleted. Typing still works without a model." else "Could not delete model. Try again." }
                        finally { WorkLease.release() }
                        refreshReadiness()
                    } else status.text = "Wait for the current take or import to finish."
                }.show()
        })
        val companion = Ui.column(this).apply { visibility = View.GONE }
        column.addView(Ui.button(this, "Advanced · voice with another keyboard") {
            companion.visibility = if (companion.visibility == View.VISIBLE) View.GONE else View.VISIBLE
            refreshReadiness()
        })
        companionStatus = Ui.text(this, "")
        companion.addView(companionStatus)
        companion.addView(Ui.text(this, "Optional: Utterleaf Voice is a separate voice-only input method for compatible keyboards. It is not needed for Utterleaf Keyboard's Voice button. Gboard and Samsung Keyboard do not offer this integration."))
        companion.addView(Ui.button(this, "Manage voice input methods") { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) })
        column.addView(companion)
        column.addView(Ui.button(this, "Set up updates in Obtainium") {
            val config = assets.open("obtainium.json").bufferedReader().use { it.readText() }
            try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("obtainium://app/" + Uri.encode(config)))) }
            catch (_: android.content.ActivityNotFoundException) {
                status.text = "Obtainium is not installed. Install it separately, then return here. Utterleaf does not download or install updates itself."
            }
        })
        column.addView(Ui.button(this, "Licenses and privacy") {
            AlertDialog.Builder(this).setTitle("Utterleaf Voice")
                .setMessage(assets.open("NOTICE.txt").bufferedReader().use { it.readText() })
                .setNeutralButton("Full licenses") { _, _ ->
                    val licenses = listOf("UTTERLEAF-LICENSE.txt", "WHISPER-LICENSE.txt", "MODEL-LICENSE.txt", "LIBCXX-LICENSE.txt")
                        .joinToString("\n\n") { name -> name + "\n\n" + assets.open(name).bufferedReader().use { it.readText() } }
                    AlertDialog.Builder(this).setTitle("Third-party licenses").setMessage(licenses).setPositiveButton("Close", null).show()
                }
                .setPositiveButton("Close", null).show()
        })
        setContentView(ScrollView(this).apply { addView(column); Ui.applySystemInsets(this) })
        refreshReadiness()
    }
    private fun megabytes(size: Long) = String.format(Locale.US, "%.1f", size / 1_000_000.0)
    private fun refreshModelChoice() {
        if (!::modelDetails.isInitialized || !::downloadModel.isInitialized || !::importModel.isInitialized) return
        modelDetails.text = "${selectedModel.filename}\nDownload: ${megabytes(selectedModel.size)} MB. Allow about ${megabytes(selectedModel.size * 2)} MB free for the browser download and verified import. Your current model stays installed until verification succeeds. You can remove the browser's downloaded copy afterwards."
        downloadModel.text = "Download ${selectedModel.id} in browser"
    }
    private fun microphoneAllowed() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    private fun refreshReadiness() {
        if (!::companionStatus.isInitialized) return
        val manager = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        val enabled = manager.enabledInputMethodList
        val keyboardEnabled = enabled.any { it.packageName == packageName && it.serviceName == KeyboardIme::class.java.name }
        val selected = ComponentName.unflattenFromString(Settings.Secure.getString(contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD).orEmpty())
        val keyboardSelected = selected == ComponentName(this, KeyboardIme::class.java)
        keyboardStatus.text = when {
            keyboardEnabled && keyboardSelected -> "Typing ready · Utterleaf Keyboard is enabled and selected."
            keyboardEnabled -> "Step 1 complete · Keyboard enabled. Choose Utterleaf Keyboard to start typing."
            else -> "Step 1 · Enable Utterleaf Keyboard in Android settings."
        }
        enableKeyboard.text = if (keyboardEnabled) "1 · Enabled · manage keyboards" else "1 · Enable Utterleaf Keyboard"
        chooseKeyboard.text = if (keyboardSelected) "2 · Selected · change keyboard" else "2 · Choose Utterleaf Keyboard"
        chooseKeyboard.isEnabled = keyboardEnabled
        val model = ModelStore.installed(noBackupFilesDir)
        val mic = microphoneAllowed()
        voiceStatus.text = when {
            model != null && mic -> "Voice setup ready · ${model.id} installed · microphone permission allowed. Tap Speak in a compatible field to record."
            model != null -> "Voice needs microphone permission · ${model.id} installed."
            mic -> "Voice needs a model · microphone permission allowed."
            else -> "Voice not set up · import a model and allow your microphone if you want dictation."
        }
        val voiceEnabled = enabled.any { it.packageName == packageName && it.serviceName == VoiceIme::class.java.name }
        companionStatus.text = if (voiceEnabled) "Optional Utterleaf Voice input method is enabled." else "Optional Utterleaf Voice input method is not enabled."
    }
    override fun onResume() { super.onResume(); refreshReadiness() }
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) refreshReadiness()
    }
    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("model", selectedModel.id)
        outState.putBoolean("importPending", importPending)
        super.onSaveInstanceState(outState)
    }
    @Deprecated("Platform callback")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 10) return
        val pending = importPending
        importPending = false
        if (resultCode != RESULT_OK || !pending) return
        val uri = data?.data ?: return
        if (!WorkLease.acquire()) { status.text = "Wait for the current take or import to finish."; return }
        status.text = "Identifying and verifying the model locally…"
        val app = applicationContext
        Thread({
            val message = try {
                val installed = app.contentResolver.openInputStream(uri).use { input ->
                    requireNotNull(input) { "Could not open the selected file." }
                    ModelStore.install(input, app.noBackupFilesDir)
                }
                "${installed.id} verified and installed. The downloaded copy can now be removed from Downloads."
            } catch (_: Exception) { "Import failed. Use an original tiny.en, base.en or small.en file from the download links and check free storage. Existing model kept." }
            finally { WorkLease.release() }
            runOnUiThread { if (!isDestroyed) { status.text = message; refreshReadiness() } }
        }, "utterleaf-import").start()
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != 11) return
        status.text = if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) "Microphone permission allowed. Recording starts only after you tap Speak."
                      else "Microphone permission is off. Typing still works. Use Open app permissions if Android no longer shows the prompt."
        refreshReadiness()
    }
}
