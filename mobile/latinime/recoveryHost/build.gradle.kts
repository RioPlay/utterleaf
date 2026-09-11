plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.utterleaf.keyboard.recoveryhost"
    compileSdk = 36
    defaultConfig {
        applicationId = "org.utterleaf.keyboard.recoveryhost"
        minSdk = 30
        targetSdk = 36
        versionCode = 1
        versionName = "synthetic-recovery-probe"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    lint { abortOnError = true }
}

// This fixture cannot produce a release APK and is absent from ordinary settings.
androidComponents {
    beforeVariants(selector().withBuildType("release")) { it.enable = false }
}
