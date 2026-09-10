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
    private fun update(text: String, phase: CapturePhase = CapturePhase.RECORDING) =
        main.post { if (!cancelled.get()) state(CaptureStatus(phase, text)) }
    override fun start() {
        if (started) return
        started = true
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            error("Open Utterleaf Voice and grant microphone permission first."); return
        }
        if (!ModelStore.ready(context.noBackupFilesDir)) {
            error("Open Utterleaf Voice and import the English model first."); return
        }
        if (!WorkLease.acquire()) { error("Another take or model import is finishing. Try again shortly."); return }
        ownsLease = true
        try { NativeEngine.reset() } catch (_: LinkageError) {
            ownsLease = false; WorkLease.release(); error("The speech engine is unavailable on this device."); return
        }
        update("Opening microphone…")
        Thread({ runTake() }, "utterleaf-take").start()
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
            val bytes = try { NativeEngine.decode(ModelStore.file(context.noBackupFilesDir).absolutePath, samples) }
                        finally { samples.fill(0f) }
            if (cancelled.get()) { bytes?.fill(0); return }
            check(bytes != null) { "Could not transcribe. Try a shorter take or restart the app." }
            val text = bytes.toString(Charsets.UTF_8).trim()
            bytes.fill(0)
            check(text.isNotBlank()) { "No speech recognized. Try again." }
            main.post { if (!cancelled.get()) result(text) }
        } catch (failure: Exception) {
            val message = if (failure is SecurityException) "Microphone permission was denied. Enable it in Utterleaf Voice settings."
                          else if (failure is IllegalStateException) failure.message ?: "Capture failed. Try again."
                          else "Capture failed. Check the microphone and try again."
            main.post { if (!cancelled.get()) error(message) }
        } catch (_: OutOfMemoryError) {
            main.post { if (!cancelled.get()) error("Not enough memory. Close other apps and try again.") }
        } finally {
            try { recorder?.stop() } catch (_: Exception) { }
            try { recorder?.release() } catch (_: Exception) { }
            audio.fill(0f)
            main.post { ownsLease = false; WorkLease.release() }
        }
    }
}
