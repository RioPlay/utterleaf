plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.utterleaf.voice.lifecyclehost"
    compileSdk = 36
    defaultConfig {
        applicationId = "org.utterleaf.voice.lifecyclehost"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "synthetic-lifecycle-host"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    lint { abortOnError = true }
}

// This fixture can never produce a release APK and is absent from ordinary builds.
androidComponents {
    beforeVariants(selector().withBuildType("release")) { it.enable = false }
}

dependencies {
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:rules:1.6.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
}

// The fixture queries the installed product IME before it can select or test it.
// Keep configuration lazy while making that device-state prerequisite explicit.
tasks.matching { it.name == "connectedDebugAndroidTest" }.configureEach {
    dependsOn(":app:installDebug")
}
