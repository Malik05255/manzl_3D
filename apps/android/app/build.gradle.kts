plugins {
    id("com.android.application")
}

android {
    namespace = "com.manzilh.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.manzilh.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
}
