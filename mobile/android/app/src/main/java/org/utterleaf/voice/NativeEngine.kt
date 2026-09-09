package org.utterleaf.voice

object NativeEngine {
    init { System.loadLibrary("utterleaf") }
    external fun reset()
    external fun cancel()
    external fun decode(model: String, audio: FloatArray): ByteArray?
}
