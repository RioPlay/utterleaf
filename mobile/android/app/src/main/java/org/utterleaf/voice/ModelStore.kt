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

/** Only reviewed English GGML files reach native code. Imports never fetch a URL. */
object ModelStore {
    const val SIZE = 77704715L
    const val SHA256 = "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f"
    const val URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
    data class Spec(val id: String, val size: Long, val sha256: String, val description: String) {
        val filename get() = "ggml-$id.bin"
        val url get() = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$filename"
    }
    // Verified against the publisher's raw Git LFS pointers, 2026-09-09:
    // https://huggingface.co/ggerganov/whisper.cpp/raw/main/ggml-{tiny,base,small}.en.bin
    val catalog = listOf(
        Spec("tiny.en", SIZE, SHA256, "Smallest download · a good starting point"),
        Spec("base.en", 147964211L, "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002", "Larger model · more memory and processing"),
        Spec("small.en", 487614201L, "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d", "Largest option · best suited to more capable phones")
    )
    // Keep the original private path so upgrading preserves already verified tiny.en installs.
    fun file(directory: File) = File(directory, "tiny.en.bin")
    // Sizes are unique. This identifies a private, previously verified install; it is not
    // an import-validation substitute. External bytes always pass the full hash below.
    fun installed(directory: File): Spec? = file(directory).takeIf { it.isFile }?.let { stored ->
        catalog.singleOrNull { it.size == stored.length() }
    }
    fun ready(directory: File) = installed(directory) != null
    @Synchronized
    fun install(input: InputStream, directory: File, selected: Spec? = null) {
        require(selected == null || selected in catalog) { "Choose a supported English model." }
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
                    require(size <= (selected?.size ?: catalog.maxOf { it.size })) { "Model exceeds the selected model size." }
                    digest.update(buffer, 0, n)
                    out.write(buffer, 0, n)
                }
                out.fd.sync()
            }
            val hash = digest.digest().joinToString("") { "%02x".format(it) }
            val spec = selected ?: catalog.singleOrNull { it.size == size }
            require(spec != null && size == spec.size && hash == spec.sha256) {
                "Model verification failed. Choose the original supported English GGML file."
            }
            java.nio.file.Files.move(pending.toPath(), file(directory).toPath(),
                java.nio.file.StandardCopyOption.ATOMIC_MOVE, java.nio.file.StandardCopyOption.REPLACE_EXISTING)
        } finally { pending.delete() }
    }
}
