package org.utterleaf.voice

/** Local speech only. reset() starts a native generation; cancel() and a later reset abort older work. */
object NativeEngine {
    init { System.loadLibrary("utterleaf") }
    external fun reset()
    external fun cancel()
    external fun decode(model: String, audio: FloatArray): ByteArray?
}
