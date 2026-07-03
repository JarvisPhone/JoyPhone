import org.gradle.api.tasks.testing.Test

plugins {
    kotlin("jvm")
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("junit:junit:4.13.2")
}

tasks.register<Test>("testDebugUnitTest") {
    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath
    useJUnit()
}

tasks.withType<Test>().configureEach {
    useJUnit()
}