plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt.android)
}

android {
    namespace = "com.example.phoneagent"
    compileSdk {
        version = release(36)
    }

    // WS_URL 解析优先级(从高到低):
    //   1. 命令行 -PwsUrl=...(最高,临时用)
    //   2. android/local.properties(已 gitignore,本机用户级,真机改这里)
    //   3. android/gradle.properties(项目级默认 ws://10.0.2.2:8000)
    // 注意:providers.gradleProperty() 会自动读 gradle.properties,不会读 local.properties,
    // 所以 local.properties 必须自己 file() 解析,才能压在 gradle.properties 之上。
    val wsUrl: String = run {
        // 1) 命令行 -P
        providers.gradleProperty("wsUrl").orNull
            // 2) local.properties 的 wsUrl= 行(Gradle 不会自动读它)
            ?: run {
                val local = rootProject.file("local.properties")
                if (local.exists()) {
                    local.readLines()
                        .firstOrNull { it.trim().startsWith("wsUrl=") }
                        ?.substringAfter("=")?.trim()
                        ?.takeIf { it.isNotEmpty() }
                } else null
            }
            // 3) gradle.properties(项目默认值)— 已经在 gradleProperty() 里自动加载
            ?: "ws://10.0.2.2:8000"
    }

    defaultConfig {
        applicationId = "com.example.phoneagent"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "WS_URL", "\"$wsUrl\"")
    }

    buildTypes {
        debug {
            // 真机经 WiFi 同网段直连服务端 —— IP 走 local.properties 的 wsUrl
            buildConfigField("String", "WS_URL", "\"$wsUrl\"")
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // 部署时改 local.properties 的 wsUrl 即可,不必再改 build.gradle.kts
            buildConfigField("String", "WS_URL", "\"$wsUrl\"")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(libs.appcompat)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.androidx.core.ktx)

    // Lifecycle
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)

    // Compose
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons.extended)
    debugImplementation(libs.androidx.compose.ui.tooling)

    // Hilt
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.androidx.hilt.navigation.compose)

    // Test
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}