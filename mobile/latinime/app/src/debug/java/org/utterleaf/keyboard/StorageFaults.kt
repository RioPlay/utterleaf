package org.utterleaf.keyboard

/** Debug APK only. Callers retain a real dictionary owner throughout configuration/polling. */
object StorageFaults {
    external fun configureNative(owner: Long, stage: Int, mode: Int)
    external fun reachedNative(owner: Long): Int
    external fun releaseNative(owner: Long)
}
