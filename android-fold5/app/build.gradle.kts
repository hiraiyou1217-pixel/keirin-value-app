plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "jp.hirai.keirinai"
    compileSdk = 35

    defaultConfig {
        applicationId = "jp.hirai.keirinai"
        minSdk = 34
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0"

        testInstrumentationRunner =
            "android.app.InstrumentationTestRunner"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
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
    testImplementation("junit:junit:4.13.2")
}
