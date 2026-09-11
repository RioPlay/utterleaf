import groovy.json.JsonOutput
import groovy.json.JsonSlurper
import java.security.MessageDigest

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
val restrictedSources = tasks.register<Sync>("prepareLatinimeSources") {
    from("../upstream/common/src")
    from("../upstream/java/src") {
        exclude(file("../excluded-sources.txt").readLines().filter { it.isNotBlank() && !it.startsWith("#") })
    }
    into(layout.buildDirectory.dir("generated/latinime/java"))
}
val restrictedResources = tasks.register<Sync>("prepareLatinimeResources") {
    from("../upstream/java/res") {
        exclude("**/setup_*.xml", "**/setup-*.xml", "**/setup_welcome_*", "**/ic_setup_*.xml")
        exclude("layout/download_over_metered.xml", "layout/dictionary_line.xml")
    }
    into(layout.buildDirectory.dir("generated/latinime/res"))
}

// Keep provenance current without modifying the reviewed source bundle during a build.
val noticeRepoRoot = rootProject.projectDir.resolve("../..").canonicalFile
val noticeCatalog = file("../notices/catalog.json")
val noticeAssets = layout.buildDirectory.dir("generated/notices/assets")
val refreshNoticeSources = mapOf(
    "AOSP-NOTICE.txt" to "mobile/latinime/upstream/NOTICE",
    "AOSP-JAVA-NOTICE.txt" to "mobile/latinime/upstream/java/NOTICE",
    "UTTERLEAF-NOTICE.md" to "mobile/latinime/upstream/UTTERLEAF-NOTICE.md"
)
fun confinedNoticeSource(path: String): File {
    require(path.matches(Regex("[A-Za-z0-9][A-Za-z0-9._/-]*")) &&
        path.split('/').none { it == "." || it == ".." || it.isEmpty() }) {
        "Invalid notice source path: $path"
    }
    val source = noticeRepoRoot.resolve(path).canonicalFile
    require(source.toPath().startsWith(noticeRepoRoot.toPath()) && source.isFile) {
        "Missing or unconfined notice source: $path"
    }
    return source
}
val noticeCatalogData = (JsonSlurper().parse(noticeCatalog) as? Map<*, *>)
    ?: error("Notice catalog must be an object")
require(noticeCatalogData["schema_version"] == 1) { "Unsupported notice schema" }
val noticeDocuments = (noticeCatalogData["documents"] as? List<*>)
    ?.map { it as? Map<*, *> ?: error("Invalid notice document") }
    ?: error("Notice catalog requires documents")
val noticeNames = mutableSetOf<String>()
val noticeIds = mutableSetOf<String>()
val refreshedNotices = mutableSetOf<String>()
val noticeInputs = noticeDocuments.map { document ->
    val name = document["file"] as? String ?: error("Notice requires file")
    val id = document["id"] as? String ?: error("Notice requires id")
    require(name.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]*")) && name != "catalog.json" &&
        noticeNames.add(name.lowercase()) && id.matches(Regex("[a-z0-9-]+")) && noticeIds.add(id)) {
        "Invalid or duplicate notice file/id: $name"
    }
    for (field in listOf("title", "license", "version")) {
        require((document[field] as? String)?.isNotBlank() == true) { "Notice $name lacks $field" }
    }
    require((document["sha256"] as? String)?.matches(Regex("[0-9a-f]{64}")) == true) {
        "Invalid notice hash: $name"
    }
    val source = document["source_path"] as? String ?: error("Notice requires source_path")
    if (document.containsKey("refresh_from_source")) {
        require(document["refresh_from_source"] == source && refreshNoticeSources[name] == source) {
            "Unapproved refresh source: $name"
        }
        refreshedNotices.add(name)
    } else {
        require(source == "mobile/latinime/notices/$name") { "Invalid staged source: $name" }
    }
    confinedNoticeSource(source)
}
require(refreshedNotices == refreshNoticeSources.keys) { "Required live upstream notices missing" }
val preparedNotices = tasks.register("prepareFoundationNotices") {
    inputs.file(noticeCatalog).withPathSensitivity(PathSensitivity.RELATIVE)
    inputs.files(noticeInputs).withPathSensitivity(PathSensitivity.RELATIVE)
    outputs.dir(noticeAssets)
    doLast {
        val contents = noticeInputs.map { it.readBytes() }
        val packagedDocuments = noticeDocuments.mapIndexed { index, document ->
            val hash = MessageDigest.getInstance("SHA-256").digest(contents[index])
                .joinToString("") { "%02x".format(it) }
            require(document.containsKey("refresh_from_source") || document["sha256"] == hash) {
                "Staged notice hash mismatch: ${document["file"]}"
            }
            LinkedHashMap(document).apply { put("sha256", hash) }
        }
        // Validate everything before replacing this task's generated output directory.
        val output = noticeAssets.get().asFile
        require(output.canonicalFile.toPath().startsWith(layout.buildDirectory.get().asFile
            .canonicalFile.toPath())) { "Generated notices must remain inside the build directory" }
        delete(output)
        val directory = output.resolve("notices")
        check(directory.mkdirs()) { "Cannot create generated notices directory" }
        noticeDocuments.forEachIndexed { index, document ->
            directory.resolve(document["file"] as String).writeBytes(contents[index])
        }
        val catalog = LinkedHashMap(noticeCatalogData).apply { put("documents", packagedDocuments) }
        directory.resolve("catalog.json").writeText(JsonOutput.prettyPrint(JsonOutput.toJson(catalog)) + "\n")
    }
}
android {
    namespace = "com.android.inputmethod.latin"
    compileSdk = 36
    ndkVersion = "28.0.13004108"
    defaultConfig {
        applicationId = "org.utterleaf.keyboard.experimental"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0-foundation01"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // This probe needs an external controller to kill/relaunch the instrumentation process.
        testInstrumentationRunnerArguments["notClass"] =
            "org.utterleaf.keyboard.ProcessDeathProbeTest,org.utterleaf.keyboard.ImeProcessRecoveryProbeTest," +
                "org.utterleaf.keyboard.DictionaryStorageCrashProbeTest"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
        externalNativeBuild { cmake { arguments += "-DANDROID_STL=c++_static" } }
    }
    sourceSets {
        getByName("main") {
            java.srcDirs(restrictedSources.map { it.destinationDir }, "src/main/java")
            res.srcDirs(restrictedResources.map { it.destinationDir }, "src/main/res")
            assets.srcDir(files(noticeAssets).builtBy(preparedNotices))
        }
    }
    externalNativeBuild { cmake { path = file("../native/CMakeLists.txt"); version = "3.22.1" } }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
    androidResources { noCompress += "dict" }
    lint { abortOnError = true; checkGeneratedSources = true }
}
tasks.named("preBuild") { dependsOn(restrictedSources, restrictedResources, preparedNotices) }
dependencies {
    implementation("androidx.core:core:1.16.0")
    implementation("androidx.legacy:legacy-support-v4:1.0.0")
    implementation("com.google.code.findbugs:jsr305:3.0.2")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:rules:1.6.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
}
