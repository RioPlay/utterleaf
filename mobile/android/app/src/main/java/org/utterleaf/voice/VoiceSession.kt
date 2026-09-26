package org.utterleaf.voice

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

interface CaptureSession {
    fun start()
    fun stop()
    fun cancel()
}

enum class CapturePhase { RECORDING, PROCESSING }
data class CaptureStatus(val phase: CapturePhase, val message: String)

class VoiceSession(private val context: Context, private val state: (CaptureStatus) -> Unit,
                   private val result: (String) -> Unit, private val error: (String) -> Unit) : CaptureSession {
    private val main = Handler(Looper.getMainLooper())
    private val stopped = AtomicBoolean(false)
    private val cancelled = AtomicBoolean(false)
    private var started = false
    private var ownsLease = false
    private var verifiedModel: File? = null
    private fun update(text: String, phase: CapturePhase = CapturePhase.RECORDING) =
        main.post { if (!cancelled.get()) state(CaptureStatus(phase, text)) }
    // Single-use, including failed starts: callers create a fresh session for each take/retry.
    override fun start() {
        if (started) return
        started = true
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            error("Open Utterleaf and grant microphone permission first."); return
        }
        if (!WorkLease.acquire()) { error("Another take or model import is finishing. Try again shortly."); return }
        ownsLease = true
        when (val readiness = ModelStore.readiness(context.noBackupFilesDir)) {
            is ModelStore.Readiness.Ready -> verifiedModel = readiness.file
            ModelStore.Readiness.Missing -> {
                failStart("Open Utterleaf and import the English model first."); return
            }
            is ModelStore.Readiness.Checking -> {
                failStart("The speech model is still being verified on this device. Try again shortly."); return
            }
            is ModelStore.Readiness.Invalid -> {
                failStart("The speech model could not be verified. Open Utterleaf to repair or import it again."); return
            }
        }
        try { NativeEngine.reset() }
        catch (_: LinkageError) { failStart("The speech engine is unavailable on this device."); return }
        catch (_: RuntimeException) { failStart("The speech engine could not start. Try again."); return }
        catch (_: OutOfMemoryError) { failStart("Not enough memory to start dictation. Close other apps and try again."); return }
        update("Opening microphone…")
        try { Thread({ runTake() }, "utterleaf-take").start() }
        catch (_: RuntimeException) { failStart("Capture could not start. Try again.") }
        catch (_: OutOfMemoryError) { failStart("Not enough memory to start capture. Close other apps and try again.") }
    }
    override fun stop() { stopped.set(true) }
    override fun cancel() {
        cancelled.set(true)
        stopped.set(true)
        if (ownsLease) NativeEngine.cancel()
    }
    @Suppress("MissingPermission") // Permission checked before starting; revocation is handled below.
    private fun runTake() {
        var audio = FloatArray(0)
        var count = 0
        var recorder: AudioRecord? = null
        var terminal: (() -> Unit)? = null
        try {
            audio = FloatArray(16000 * 120)
            val minimum = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            check(minimum > 0) { "This microphone does not support 16 kHz capture." }
            if (cancelled.get()) return
            recorder = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, 16000,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(minimum, 6400))
            check(recorder.state == AudioRecord.STATE_INITIALIZED) { "Microphone unavailable. Close competing capture and try again." }
            if (cancelled.get()) return
            recorder.startRecording()
            check(recorder.recordingState == AudioRecord.RECORDSTATE_RECORDING) { "Microphone could not start." }
            val block = ShortArray(1600)
            val start = SystemClock.elapsedRealtime()
            var lastSamples = start
            var lastSecond = -1
            try {
                while (!stopped.get() && count < audio.size) {
                    val n = recorder.read(block, 0, minOf(block.size, audio.size - count), AudioRecord.READ_NON_BLOCKING)
                    check(n >= 0) { "Microphone interrupted. This take was discarded; reconnect and try again." }
                    val now = SystemClock.elapsedRealtime()
                    if (n > 0) {
                        lastSamples = now
                        for (i in 0 until n) audio[count++] = block[i] / 32768f
                    } else {
                        check(now - lastSamples < 3000) { "Microphone stopped responding. Reconnect and try again." }
                        Thread.sleep(10)
                    }
                    val second = ((now - start) / 1000).toInt()
                    if (second != lastSecond) { lastSecond = second; update("Listening · ${second}s elapsed · ${maxOf(0, 120 - second)}s left") }
                    if (second >= 120) break
                }
            } finally { block.fill(0) }
            recorder.stop()
            recorder.release()
            recorder = null
            if (cancelled.get()) return
            check(count >= 5600) { "Take too short. Tap Speak and try again." }
            var energy = 0.0
            for (i in 0 until count) energy += audio[i] * audio[i]
            check(energy / count > 0.000001) { "Very little audio detected. Check your microphone and try again." }
            update("Microphone off · transcribing on this device…", CapturePhase.PROCESSING)
            val samples = audio.copyOf(count)
            val model = checkNotNull(verifiedModel) { "The verified speech model is unavailable." }
            val bytes = try { NativeEngine.decode(model.absolutePath, samples) }
                        finally { samples.fill(0f) }
            if (cancelled.get()) { bytes?.fill(0); return }
            check(bytes != null) { "Could not transcribe. Try a shorter take or restart the app." }
            val text = try { bytes.toString(Charsets.UTF_8).trim() }
                finally { bytes.fill(0) }
            check(text.isNotBlank()) { "No speech recognized. Try again." }
            terminal = { result(text) }
        } catch (failure: Exception) {
            val message = if (failure is SecurityException) "Microphone permission was denied. Enable it in Utterleaf settings."
                          else if (failure is IllegalStateException) failure.message ?: "Capture failed. Try again."
                          else "Capture failed. Check the microphone and try again."
            terminal = { error(message) }
        } catch (_: LinkageError) {
            terminal = { error("The speech engine became unavailable. Restart Utterleaf and try again.") }
        } catch (_: OutOfMemoryError) {
            terminal = { error("Not enough memory. Close other apps and try again.") }
        } finally {
            try { recorder?.stop() } catch (_: Exception) { }
            try { recorder?.release() } catch (_: Exception) { }
            audio.fill(0f)
            val delivery = terminal
            main.post {
                verifiedModel = null
                ownsLease = false
                WorkLease.release()
                if (!cancelled.get()) delivery?.invoke()
            }
        }
    }

    private fun failStart(message: String) {
        cancelled.set(true)
        verifiedModel = null
        if (ownsLease) { ownsLease = false; WorkLease.release() }
        error(message)
    }
}
