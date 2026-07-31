plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

val signingStorePath =
    providers.environmentVariable(
        "ANDROID_SIGNING_KEYSTORE_PATH"
    ).orNull
val signingStorePassword =
    providers.environmentVariable(
        "ANDROID_SIGNING_STORE_PASSWORD"
    ).orNull
val signingKeyAlias =
    providers.environmentVariable(
        "ANDROID_SIGNING_KEY_ALIAS"
    ).orNull
val signingKeyPassword =
    providers.environmentVariable(
        "ANDROID_SIGNING_KEY_PASSWORD"
    ).orNull
val stableSigningReady = listOf(
    signingStorePath,
    signingStorePassword,
    signingKeyAlias,
    signingKeyPassword,
).all {
    !it.isNullOrBlank()
}

android {
    namespace = "jp.hirai.keirinai"
    compileSdk = 35

    defaultConfig {
        applicationId = "jp.hirai.keirinai"
        minSdk = 34
        targetSdk = 35
        versionCode = 5
        versionName = "0.5.0"

        testInstrumentationRunner =
            "android.app.InstrumentationTestRunner"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        if (stableSigningReady) {
            create("stableRelease") {
                storeFile = file(
                    signingStorePath!!
                )
                storePassword =
                    signingStorePassword
                keyAlias = signingKeyAlias
                keyPassword =
                    signingKeyPassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs
                .findByName(
                    "stableRelease"
                )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.all {
            it.useJUnit()
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"

        pip {
            install("numpy==1.26.2")
            install("pandas==2.1.3")
        }
    }

    sourceSets {
        getByName("main") {
            srcDir(
                "src/main/python/generated_sources"
            )
        }
    }
}

dependencies {
    implementation(
        "androidx.documentfile:documentfile:1.0.1"
    )
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}

tasks.register("verifyStableSigning") {
    doLast {
        check(stableSigningReady) {
            "固定署名の環境変数が不足しています。"
        }
        check(
            file(signingStorePath!!).isFile
        ) {
            "固定署名キーストアがありません。"
        }
    }
}
