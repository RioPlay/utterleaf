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

class SetupActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var keyboardStatus: TextView
    private lateinit var voiceStatus: TextView
    private lateinit var companionStatus: TextView
    private lateinit var enableKeyboard: Button
    private lateinit var chooseKeyboard: Button
    private lateinit var modelSummary: TextView
    private lateinit var modelDetails: TextView
    private lateinit var modelDetailsToggle: Button
    private lateinit var useModel: Button
    private lateinit var removeModel: Button
    private val modelChoices = mutableMapOf<ModelStore.Spec, RadioButton>()
    private lateinit var downloadModel: Button
    private lateinit var importModel: Button
    private var selectedModel = ModelStore.catalog.first()
    private var importPending = false
    private var voiceExpanded = false
    private var modelDetailsExpanded = false
    private lateinit var modelImports: ModelImportWork
    private var importObserver: AutoCloseable? = null
    private var readinessObserver: AutoCloseable? = null
    private var observerGeneration = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val colors = Ui.palette(this)
        modelImports = ModelImports.forDirectory(noBackupFilesDir)
        selectedModel = ModelStore.catalog.firstOrNull { it.id == savedInstanceState?.getString("model") }
            ?: ModelStore.installed(noBackupFilesDir) ?: ModelStore.catalog.first()
        importPending = savedInstanceState?.getBoolean("importPending") ?: false
        voiceExpanded = savedInstanceState?.getBoolean("voiceExpanded") ?: false
        modelDetailsExpanded = savedInstanceState?.getBoolean("modelDetailsExpanded") ?: false
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
        val voiceDetails = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = if (voiceExpanded) View.VISIBLE else View.GONE
        }
        lateinit var voiceToggle: Button
        voiceToggle = Ui.button(this, if (voiceExpanded) "Hide voice setup" else "Set up offline voice") {
            val expanding = voiceDetails.visibility != View.VISIBLE
            voiceExpanded = expanding
            voiceDetails.visibility = if (expanding) View.VISIBLE else View.GONE
            voiceToggle.text = if (expanding) "Hide voice setup" else "Set up offline voice"
            if (expanding) ModelStore.verifyAvailableAsync(noBackupFilesDir)
            refreshModelChoice()
        }
        voiceCard.addView(voiceToggle)
        voiceDetails.addView(Ui.text(this, "1 · Add a speech model", 19f))
        voiceDetails.addView(Ui.text(this, "All models work offline in English. Choose based on download size and resource use."))
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
        voiceDetails.addView(Ui.text(this, "Already downloaded a supported English model? Import identifies and verifies it automatically. Need a download? Choose an option below; this only changes the browser link."))
        val choices = RadioGroup(this)
        ModelStore.catalog.forEach { spec ->
            choices.addView(RadioButton(this).apply {
                modelChoices[spec] = this
                id = View.generateViewId()
                val presentation = ModelPresentation.forSpec(spec)
                text = "${presentation.summary(spec)}\n${presentation.tradeoff}"
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
        modelSummary = Ui.text(this, "")
        voiceDetails.addView(modelSummary)
        modelDetailsToggle = Ui.button(this, "Show technical model details") {
            modelDetailsExpanded = !modelDetailsExpanded
            refreshModelDetails()
        }
        voiceDetails.addView(modelDetailsToggle)
        modelDetails = Ui.text(this, "").apply {
            visibility = if (modelDetailsExpanded) View.VISIBLE else View.GONE
        }
        voiceDetails.addView(modelDetails)
        useModel = Ui.button(this, "Use selected model") {
            if (WorkLease.acquire()) {
                try { status.text = if (ModelStore.select(noBackupFilesDir, selectedModel))
                    "${ModelPresentation.forSpec(selectedModel).name} selected for the next take." else "Import this model first." }
                catch (_: Exception) { status.text = "Could not switch models. The previous choice is kept." }
                finally { WorkLease.release() }
                refreshReadiness(); refreshModelChoice()
            } else status.text = "Wait for the current take or import to finish."
        }
        voiceDetails.addView(useModel)
        downloadModel = Ui.button(this, "") {
            val spec = selectedModel
            val presentation = ModelPresentation.forSpec(spec)
            AlertDialog.Builder(this).setTitle("Download ${presentation.name} in your browser?")
                .setMessage("Your browser will connect to Hugging Face for a ${ModelPresentation.sizeLabel(spec.size)} download. Utterleaf does not download files itself. Return here to import the downloaded model.")
                .setNegativeButton("Cancel", null).setPositiveButton("Open browser") { _, _ ->
                    try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(spec.url))) }
                    catch (_: android.content.ActivityNotFoundException) { status.text = "No browser available. Transfer the ${presentation.name} model from another device, then import it here." }
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
            val presentation = ModelPresentation.forSpec(deleting)
            AlertDialog.Builder(this).setTitle("Delete ${presentation.name}?").setMessage("Only this imported model is removed. Typing will still work. You can select another installed model or import it again later.")
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
    private fun refreshModelDetails() {
        if (!::modelSummary.isInitialized || !::modelDetails.isInitialized || !::modelDetailsToggle.isInitialized) return
        val presentation = ModelPresentation.forSpec(selectedModel)
        modelSummary.text = "${presentation.summary(selectedModel)}\n${presentation.tradeoff}. Allow about ${ModelPresentation.sizeLabel(selectedModel.size * 2)} free for the browser download and verified import. Your current model stays installed until verification succeeds. You can remove the browser's downloaded copy afterwards."
        modelDetails.text = presentation.technicalDetails(selectedModel)
        modelDetails.visibility = if (modelDetailsExpanded) View.VISIBLE else View.GONE
        modelDetailsToggle.text = if (modelDetailsExpanded) "Hide technical model details" else "Show technical model details"
    }
    private fun refreshModelChoice() {
        if (!::modelSummary.isInitialized || !::downloadModel.isInitialized || !::importModel.isInitialized) return
        refreshModelDetails()
        val selectedPresentation = ModelPresentation.forSpec(selectedModel)
        downloadModel.text = "Download ${selectedPresentation.name} in browser"
        val installed = ModelStore.available(noBackupFilesDir)
        val active = ModelStore.installed(noBackupFilesDir)
        val importing = modelImports.state.busy
        importModel.isEnabled = !importing
        modelChoices.forEach { (spec, choice) ->
            val presentation = ModelPresentation.forSpec(spec)
            val state = when {
                spec == active -> "Active"
                spec in installed -> "Installed"
                ModelStore.hasStoredFile(noBackupFilesDir, spec) -> "Not verified"
                else -> "Not installed"
            }
            choice.text = "${presentation.summary(spec)} · $state\n${presentation.tradeoff}"
        }
        if (::useModel.isInitialized) {
            useModel.text = if (selectedModel == active) "${selectedPresentation.name} is active" else "Use ${selectedPresentation.name}"
            useModel.isEnabled = !importing && selectedModel in installed && selectedModel != active
        }
        if (::removeModel.isInitialized) removeModel.isEnabled =
            !importing && ModelStore.hasStoredFile(noBackupFilesDir, selectedModel)
    }
    private fun microphoneAllowed() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    private fun refreshReadiness() {
        if (::modelImports.isInitialized) modelImports.recoverInterrupted()
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
        val modelReadiness = ModelStore.readiness(noBackupFilesDir)
        val model = (modelReadiness as? ModelStore.Readiness.Ready)?.spec
        val mic = microphoneAllowed()
        voiceStatus.text = when {
            modelReadiness is ModelStore.Readiness.Checking -> "Checking the model on this device… Typing still works."
            modelReadiness is ModelStore.Readiness.Invalid -> "The model could not be verified. Typing is unaffected. Open voice setup and import the original model file again."
            model != null && mic -> "Offline dictation ready · ${ModelPresentation.forSpec(model).name} verified · microphone permission allowed. In a compatible field, tap Dictate, then Start dictation."
            model != null -> "Voice needs microphone permission · ${ModelPresentation.forSpec(model).name} installed."
            mic -> "Voice needs a model · microphone permission allowed."
            else -> "Voice not set up · import a model and allow your microphone if you want dictation."
        }
        val voiceEnabled = enabled.any { it.packageName == packageName && it.serviceName == VoiceIme::class.java.name }
        companionStatus.text = if (voiceEnabled) "Optional Utterleaf dictation input method is enabled." else "Optional Utterleaf dictation input method is not enabled."
    }
    override fun onStart() {
        super.onStart()
        val generation = ++observerGeneration
        readinessObserver = ModelStore.observe(noBackupFilesDir) {
            runOnUiThread {
                if (generation == observerGeneration && !isDestroyed && !isFinishing) refreshReadiness()
            }
        }
        importObserver = modelImports.observe { state ->
            if (generation == observerGeneration && !isDestroyed && !isFinishing) {
                if (state.message.isNotEmpty()) status.text = state.message
                refreshReadiness()
            }
        }
        modelImports.recoverInterrupted()
        if (voiceExpanded) ModelStore.verifyAvailableAsync(noBackupFilesDir)
    }
    override fun onStop() {
        observerGeneration++
        readinessObserver?.close()
        readinessObserver = null
        importObserver?.close()
        importObserver = null
        super.onStop()
    }
    override fun onResume() { super.onResume(); refreshReadiness() }
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) refreshReadiness()
    }
    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("model", selectedModel.id)
        outState.putBoolean("importPending", importPending)
        outState.putBoolean("voiceExpanded", voiceExpanded)
        outState.putBoolean("modelDetailsExpanded", modelDetailsExpanded)
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
        val app = applicationContext
        if (!modelImports.start {
                requireNotNull(app.contentResolver.openInputStream(uri)) { "Could not open the selected file" }
            }) status.text = "Another take or model change is finishing. Typing is unaffected. Try the import again shortly."
        refreshModelChoice()
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != 11) return
        status.text = if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) "Microphone permission allowed. Recording starts only after you tap Start dictation."
                      else "Microphone permission is off. Typing still works. Use Open app permissions if Android no longer shows the prompt."
        refreshReadiness()
    }
}
