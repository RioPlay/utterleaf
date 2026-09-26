pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
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
