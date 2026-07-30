plugins {
    id("com.android.application")
}

android {
    namespace = "jp.hirai.keirinai"
    compileSdk = 35

    defaultConfig {
        applicationId = "jp.hirai.keirinai"
        minSdk = 34
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner =
            "android.app.InstrumentationTestRunner"
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

dependencies {
    testImplementation("junit:junit:4.13.2")
}
