package org.utterleaf.voice

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
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
    private lateinit var useModel: Button
    private lateinit var removeModel: Button
    private val modelChoices = mutableMapOf<ModelStore.Spec, RadioButton>()
    private lateinit var downloadModel: Button
    private lateinit var importModel: Button
    private var selectedModel = ModelStore.catalog.first()
    private var importPending = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val colors = Ui.palette(this)
        selectedModel = ModelStore.catalog.firstOrNull { it.id == savedInstanceState?.getString("model") }
            ?: ModelStore.installed(noBackupFilesDir) ?: ModelStore.catalog.first()
        importPending = savedInstanceState?.getBoolean("importPending") ?: false
        val column = Ui.column(this)
        column.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            addView(LinearLayout(this@SetupActivity).apply {
                orientation = LinearLayout.VERTICAL
                addView(Ui.text(this@SetupActivity, "WELCOME", 12f).apply {
                    setTextColor(colors.accent); setTypeface(typeface, Typeface.BOLD)
                })
                addView(Ui.title(this@SetupActivity, "Make yourself at home."))
                addView(Ui.text(this@SetupActivity, "Utterleaf for Android", 16f))
            }, LinearLayout.LayoutParams(0, -2, 1f))
            addView(Ui.mascot(this@SetupActivity))
        })
        column.addView(Ui.text(this,
            "Typing takes two quick steps. Offline voice is optional and can be added whenever you want."))
        column.addView(Ui.text(this, "No account · No Internet permission · No saved recordings", 13f).apply {
            setTextColor(colors.accent); setTypeface(typeface, Typeface.BOLD)
        })

        val keyboardCard = setupCard()
        keyboardCard.addView(Ui.title(this, "Your keyboard"))
        keyboardStatus = Ui.text(this, "")
        keyboardCard.addView(keyboardStatus)
        enableKeyboard = Ui.button(this, "1 · Enable Utterleaf") {
            startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
        }
        keyboardCard.addView(enableKeyboard)
        chooseKeyboard = Ui.button(this, "2 · Choose Utterleaf") {
            (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
        }
        keyboardCard.addView(chooseKeyboard)
        keyboardCard.addView(Ui.text(this, "Then open any app and tap a text field. Typing never needs a speech model or microphone permission.", 14f))
        keyboardCard.addView(Ui.button(this, "Keyboard preferences and preview") { startActivity(Intent(this, KeyboardSettingsActivity::class.java)) })
        column.addView(keyboardCard, spacedCard())
        status = Ui.text(this, "")
        status.accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        column.addView(status)

        val voiceCard = setupCard()
        voiceCard.addView(Ui.title(this, "Optional · offline voice"))
        voiceStatus = Ui.text(this, "")
        voiceCard.addView(voiceStatus)
        voiceCard.addView(Ui.text(this, "Choose a verified English model and allow the microphone only when you are ready to dictate.", 14f))
        val voiceDetails = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.GONE }
        lateinit var voiceToggle: Button
        voiceToggle = Ui.button(this, "Set up offline voice") {
            val expanding = voiceDetails.visibility != View.VISIBLE
            voiceDetails.visibility = if (expanding) View.VISIBLE else View.GONE
            voiceToggle.text = if (expanding) "Hide voice setup" else "Set up offline voice"
        }
        voiceCard.addView(voiceToggle)
        voiceDetails.addView(Ui.text(this, "1 · Add a speech model", 19f))
        voiceDetails.addView(Ui.text(this, "Tiny is fast, Base balances size and processing, and Small offers more capacity at a higher cost in memory and time. Larger does not guarantee accuracy. Models are English only."))
        importModel = Ui.button(this, "Import a model") {
            importPending = true
            try { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE); type = "*/*"
            }, 10) } catch (_: android.content.ActivityNotFoundException) {
                importPending = false
                status.text = "No document picker is available."
            }
        }
        voiceDetails.addView(importModel)
        voiceDetails.addView(Ui.text(this, "Already downloaded a model? Import identifies tiny.en, base.en or small.en automatically and verifies the file. Need a download? Choose an option below; this only changes the browser link."))
        val choices = RadioGroup(this)
        ModelStore.catalog.forEach { spec ->
            choices.addView(RadioButton(this).apply {
                modelChoices[spec] = this
                id = View.generateViewId()
                text = "${spec.id} · ${megabytes(spec.size)} MB\n${spec.description}"
                setTextColor(colors.ink)
                buttonTintList = android.content.res.ColorStateList.valueOf(colors.accent)
                minHeight = Ui.dp(this@SetupActivity, 56)
                setPadding(0, Ui.dp(this@SetupActivity, 4), 0, Ui.dp(this@SetupActivity, 4))
                isChecked = spec == selectedModel
                setOnCheckedChangeListener { _, checked ->
                    if (checked) { selectedModel = spec; refreshModelChoice() }
                }
            })
        }
        voiceDetails.addView(choices)
        modelDetails = Ui.text(this, "")
        voiceDetails.addView(modelDetails)
        useModel = Ui.button(this, "Use selected model") {
            if (WorkLease.acquire()) {
                try { status.text = if (ModelStore.select(noBackupFilesDir, selectedModel))
                    "${selectedModel.id} selected for the next take." else "Import this model first." }
                catch (_: Exception) { status.text = "Could not switch models. The previous choice is kept." }
                finally { WorkLease.release() }
                refreshReadiness(); refreshModelChoice()
            } else status.text = "Wait for the current take or import to finish."
        }
        voiceDetails.addView(useModel)
        downloadModel = Ui.button(this, "") {
            val spec = selectedModel
            AlertDialog.Builder(this).setTitle("Download ${spec.id} in your browser?")
                .setMessage("Your browser will connect to Hugging Face for ${spec.filename} (${megabytes(spec.size)} MB). Utterleaf does not download files itself. Return here to import the downloaded file.")
                .setNegativeButton("Cancel", null).setPositiveButton("Open browser") { _, _ ->
                    try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(spec.url))) }
                    catch (_: android.content.ActivityNotFoundException) { status.text = "No browser available. Transfer ${spec.filename} from another device, then import it here." }
                }.show()
        }
        voiceDetails.addView(downloadModel)
        refreshModelChoice()
        voiceDetails.addView(Ui.text(this, "2 · Allow your microphone", 19f))
        voiceDetails.addView(Ui.button(this, "Allow microphone") {
            if (microphoneAllowed()) status.text = "Microphone permission is already allowed. Recording starts only after you tap Start dictation."
            else requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 11)
        })
        voiceDetails.addView(Ui.button(this, "Open app permissions") {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        })
        voiceDetails.addView(Ui.text(this, "3 · Try it in a text field", 19f))
        voiceDetails.addView(Ui.text(this, "Tap Dictate, then Stop & transcribe. Review the result, use Fix transcript when needed, and tap Insert text. Each take has a 120-second limit. Dictation stays unavailable in password fields."))
        removeModel = Ui.button(this, "Delete selected model") {
            val deleting = selectedModel
            AlertDialog.Builder(this).setTitle("Delete ${deleting.id}?").setMessage("Only this imported model is removed. Typing will still work. You can select another installed model or import it again later.")
                .setNegativeButton("Cancel", null).setPositiveButton("Delete") { _, _ ->
                    if (WorkLease.acquire()) {
                        try { status.text = if (ModelStore.remove(noBackupFilesDir, deleting)) "Model deleted." else "Could not delete model. Try again." }
                        catch (_: Exception) { status.text = "Could not delete model. Try again." }
                        finally { WorkLease.release() }
                        refreshReadiness(); refreshModelChoice()
                    } else status.text = "Wait for the current take or import to finish."
                }.show()
        }
        voiceDetails.addView(removeModel)
        voiceCard.addView(voiceDetails)
        column.addView(voiceCard, spacedCard())
        val companion = Ui.column(this).apply { visibility = View.GONE }
        column.addView(Ui.button(this, "Advanced · voice with another keyboard") {
            companion.visibility = if (companion.visibility == View.VISIBLE) View.GONE else View.VISIBLE
            refreshReadiness()
        })
        companionStatus = Ui.text(this, "")
        companion.addView(companionStatus)
        companion.addView(Ui.text(this, "Optional: Utterleaf dictation is a separate voice-only input method for compatible keyboards. It is not needed for Utterleaf's dictation button. Gboard and Samsung Keyboard do not offer this integration."))
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
            AlertDialog.Builder(this).setTitle(R.string.app_name)
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
    private fun setupCard() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        val colors = Ui.palette(this@SetupActivity)
        background = GradientDrawable().apply {
            setColor(colors.key)
            setStroke(Ui.dp(this@SetupActivity, 1), colors.utility)
            cornerRadius = Ui.dp(this@SetupActivity, 18).toFloat()
        }
        val padding = Ui.dp(this@SetupActivity, 14)
        setPadding(padding, padding, padding, padding)
    }
    private fun spacedCard() = LinearLayout.LayoutParams(-1, -2).apply {
        topMargin = Ui.dp(this@SetupActivity, 12)
        bottomMargin = Ui.dp(this@SetupActivity, 4)
    }
    private fun megabytes(size: Long) = String.format(Locale.US, "%.1f", size / 1_000_000.0)
    private fun refreshModelChoice() {
        if (!::modelDetails.isInitialized || !::downloadModel.isInitialized || !::importModel.isInitialized) return
        modelDetails.text = "${selectedModel.filename}\nDownload: ${megabytes(selectedModel.size)} MB. Allow about ${megabytes(selectedModel.size * 2)} MB free for the browser download and verified import. Your current model stays installed until verification succeeds. You can remove the browser's downloaded copy afterwards."
        downloadModel.text = "Download ${selectedModel.id} in browser"
        val installed = ModelStore.available(noBackupFilesDir)
        val active = ModelStore.installed(noBackupFilesDir)
        modelChoices.forEach { (spec, choice) ->
            val profile = when (spec.id) { "tiny.en" -> "Fast"; "base.en" -> "Balanced"; else -> "Larger" }
            val state = if (spec == active) "Active" else if (spec in installed) "Installed" else "Not installed"
            choice.text = "$profile · ${spec.id} · ${megabytes(spec.size)} MB · $state\n${spec.description}"
        }
        if (::useModel.isInitialized) {
            useModel.text = if (selectedModel == active) "${selectedModel.id} is active" else "Use ${selectedModel.id}"
            useModel.isEnabled = selectedModel in installed && selectedModel != active
        }
        if (::removeModel.isInitialized) removeModel.isEnabled = selectedModel in installed
    }
    private fun microphoneAllowed() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    private fun refreshReadiness() {
        refreshModelChoice()
        if (!::companionStatus.isInitialized) return
        val manager = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        val enabled = manager.enabledInputMethodList
        val keyboardEnabled = enabled.any { it.packageName == packageName && it.serviceName == KeyboardIme::class.java.name }
        val selected = ComponentName.unflattenFromString(Settings.Secure.getString(contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD).orEmpty())
        val keyboardSelected = selected == ComponentName(this, KeyboardIme::class.java)
        keyboardStatus.text = when {
            keyboardEnabled && keyboardSelected -> "Typing ready · Utterleaf is enabled and selected."
            keyboardEnabled -> "Step 1 complete · Keyboard enabled. Choose Utterleaf to start typing."
            else -> "Step 1 · Enable Utterleaf in Android settings."
        }
        enableKeyboard.text = if (keyboardEnabled) "1 · Enabled · manage keyboards" else "1 · Enable Utterleaf"
        chooseKeyboard.text = if (keyboardSelected) "2 · Selected · change keyboard" else "2 · Choose Utterleaf"
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
        companionStatus.text = if (voiceEnabled) "Optional Utterleaf dictation input method is enabled." else "Optional Utterleaf dictation input method is not enabled."
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
        status.text = if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) "Microphone permission allowed. Recording starts only after you tap Start dictation."
                      else "Microphone permission is off. Typing still works. Use Open app permissions if Android no longer shows the prompt."
        refreshReadiness()
    }
}
