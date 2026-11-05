pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
// Security fixes for AGP/lint transitive dependencies. Apply before plugin
// classpaths resolve, and to tool/test configurations as well as app graphs.
// Advisory evidence and scope: docs/plans/active/android-dependency-security.md.
val securityVersions = mapOf(
    "com.google.guava:guava" to "33.7.2-jre",
    "com.google.protobuf:protobuf-java" to "3.25.5",
    "com.google.protobuf:protobuf-kotlin" to "3.25.5",
    "org.apache.commons:commons-compress" to "1.26.0",
    "org.apache.commons:commons-lang3" to "3.18.0",
    "org.bitbucket.b_c:jose4j" to "0.9.6",
    "org.jdom:jdom2" to "2.0.6.1",
)
gradle.beforeProject {
    val applySecurityVersions: org.gradle.api.Action<org.gradle.api.artifacts.DependencyResolveDetails> =
        org.gradle.api.Action {
            val fixed = when {
                requested.group == "io.netty" && requested.name.startsWith("netty-") &&
                    !requested.name.startsWith("netty-tcnative") -> "4.1.137.Final"
                requested.group == "org.bouncycastle" && requested.name.endsWith("-jdk18on") -> "1.85"
                else -> securityVersions["${requested.group}:${requested.name}"]
            }
            if (fixed != null) {
                useVersion(fixed)
                because("Reviewed security fixes; see Android dependency security plan")
            }
        }
    buildscript.configurations.configureEach { resolutionStrategy.eachDependency(applySecurityVersions) }
    configurations.configureEach { resolutionStrategy.eachDependency(applySecurityVersions) }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "UtterleafVoice"
include(":app")
// Opt-in, debug-only editor host for lifecycle tests that must survive an IME process kill.
if (providers.gradleProperty("includeLifecycleHost").orNull == "true") {
    include(":lifecycleHost")
}
