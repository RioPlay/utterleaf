plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "org.utterleaf.keyboard.next"
    compileSdk = 36
    defaultConfig {
        applicationId = "org.utterleaf.keyboard.next"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0-core01"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    buildTypes { release { isMinifyEnabled = true; proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt")) } }
    lint { abortOnError = true }
}
dependencies {
    implementation("androidx.core:core:1.16.0")
    implementation("androidx.customview:customview:1.2.0")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:rules:1.6.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
}
