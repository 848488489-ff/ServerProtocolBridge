# Server Protocol Bridge — native Android APK

On Android the program embeds a Python runtime through **Chaquopy** (an Android
Studio Gradle plugin). pywebview is not available on Android, so the control
panel is a **built-in WebView** that loads the program's own Web UI
(`http://127.0.0.1:8765`). The relay is started and stopped from the panel, and
the UI is identical to the desktop / browser build.

The app layer is written in **Kotlin**: there is no Java source file and no
Java library in the project (the only added dependency is `kotlin-stdlib`;
Chaquopy embeds the Python runtime and is not a Java dependency).

## Language

The interface language defaults to **auto** (follow the system) and can be
switched in the Web UI, exactly as on desktop. The shell's user-visible strings
follow it: the persistent-notification title and content, the notification
channel description and the permission toast are read from the Python i18n
table in the active language. The notification is rebuilt whenever the app
returns to the foreground, so a language switch takes effect on the next visit
to the app.

## Prerequisites

- **Android Studio** with the Android SDK: SDK Platform 35 and Build-Tools.
- **JDK 17** (the JBR bundled with Android Studio is fine).
- Internet access for the first build (Gradle 8.9, AGP 8.7.3, Chaquopy 17.2.0,
  Python 3.13 and the pip dependencies are downloaded then).

## Building the APK

1. **Open this directory** (`android/`) in Android Studio and wait for the
   Gradle sync to finish (the first run downloads Gradle 8.9 and the
   dependencies).
2. Menu **Build → Build Bundle(s) / APK(s) → Build APK(s)**.
3. The APK is written to `android/app/build/outputs/apk/release/app-release.apk`
   (the release build is debug-signed, so it installs directly).

Command-line build (needs a Gradle wrapper first; generate it with
`File → Sync` in Android Studio, or run `gradle wrapper` with a local Gradle):

```
gradlew assembleRelease
```

The APK contains two ABIs: `arm64-v8a` (devices) and `x86_64` (emulators).

## Installing and running

```
adb install app-release.apk
```

Open the **Server Protocol Bridge** app: the built-in WebView shows the control
panel, the same one the desktop build uses. Program data (`config.json`,
certificates, accounts) lives in the app's private directory:

```
/data/data/com.serverprotocolbridge/files/ServerProtocolBridge/
```

You can inspect and edit it from Android Studio's **Device Explorer**
(View → Tool Windows → Device Explorer).

## Notes

- **Certificate trust**: the relay's wss:// endpoint uses a self-signed CA. On
  desktop the client only trusts the connection after the CA is installed; on
  Android `certs/cert.pem` must likewise be installed as a system/user trusted
  CA (Settings → Security → Encryption & credentials → Install a certificate),
  otherwise a browser client connecting to `wss://127.0.0.1:8443` reports a
  certificate error. This is the same limitation as on desktop, not specific to
  the APK.
- **Network permissions**: `INTERNET` and `ACCESS_NETWORK_STATE` are declared in
  the manifest; cleartext `http://127.0.0.1` is allowed only in
  `network_security_config` (localhost). All other traffic uses the secure
  default (cleartext disabled).
- **Account sign-in**: Microsoft / Java account sign-in from the panel calls
  `window.open`, which opens the authorization page in the **system browser**
  and returns to the panel afterwards.
- **Data directory**: `data_dir()` in `proxy/utils.py` resolves to
  `$HOME/ServerProtocolBridge` on Android (`HOME` is the app's internal storage,
  which Chaquopy guarantees is writable and persists until uninstall).
- **Certificate generation**: Android has no openssl binary, so
  `proxy/certs.py` falls back to the pure-Python (cryptography) generator.
