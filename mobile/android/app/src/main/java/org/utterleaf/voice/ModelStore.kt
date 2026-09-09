package org.utterleaf.voice

import java.io.File
import java.io.InputStream
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean

object WorkLease {
    private val busy = AtomicBoolean(false)
    fun acquire() = busy.compareAndSet(false, true)
    fun release() { busy.set(false) }
}

/** Accept only the reviewed tiny.en model, before handing any bytes to native code. */
object ModelStore {
    const val SIZE = 77704715L
    const val SHA256 = "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f"
    const val URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
    fun file(directory: File) = File(directory, "tiny.en.bin")
    fun ready(directory: File) = file(directory).length() == SIZE
    fun install(input: InputStream, directory: File) {
        directory.mkdirs()
        val pending = File(directory, "model-import.tmp")
        try {
            val digest = MessageDigest.getInstance("SHA-256")
            var size = 0L
            pending.outputStream().use { out ->
                val buffer = ByteArray(65536)
                while (true) {
                    val n = input.read(buffer)
                    if (n < 0) break
                    size += n
                    require(size <= SIZE) { "Choose the original ggml-tiny.en.bin model (77.7 MB)." }
                    digest.update(buffer, 0, n)
                    out.write(buffer, 0, n)
                }
                out.fd.sync()
            }
            val hash = digest.digest().joinToString("") { "%02x".format(it) }
            require(size == SIZE && hash == SHA256) { "Model verification failed. Choose the original ggml-tiny.en.bin file." }
            java.nio.file.Files.move(pending.toPath(), file(directory).toPath(),
                java.nio.file.StandardCopyOption.ATOMIC_MOVE, java.nio.file.StandardCopyOption.REPLACE_EXISTING)
        } finally { pending.delete() }
    }
}
