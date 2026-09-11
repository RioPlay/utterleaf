pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "UtterleafKeyboardExperiment"
include(":app")
// Disposable editor host for the external emulator-only IME recovery probe.
if (providers.gradleProperty("includeRecoveryHost").orNull == "true") {
    include(":recoveryHost")
}
