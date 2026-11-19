# Server Protocol Bridge — Android native APK

On Android the program embeds Python via **Chaquopy** (the Android Studio
Gradle plugin).  `pywebview` is unavailable on Android, so the control panel is
a **built-in WebView** that loads the program's own Flask Web UI
(`http://127.0.0.1:8765`); the proxy service is controlled from the panel's
"Start service" button, exactly like the desktop / browser interface.

## Requirements

- **Android Studio** (including the Android SDK), SDK Platform 35 + Build-Tools
- **JDK 17** (the JBR bundled with Android Studio is enough)
- Internet access on first build (Gradle 8.9, AGP 8.7.3, Chaquopy 17.2.0,
  Python 3.13 and the pip dependencies are downloaded then)

## Building the APK

1. Open this directory (`android/`) in Android Studio and wait for the Gradle
   sync to finish (the first run downloads Gradle 8.9 and the dependencies).
2. Menu **Build → Build Bundle(s) / APK(s) → Build APK(s)**.
3. The APK is written to
   `android/app/build/outputs/apk/release/app-release.apk` (the release is
   signed with the debug key, so it installs directly).

Command line build (a Gradle wrapper is needed first; generate it in Android
Studio via `File → Sync`, or run `gradle wrapper` with a local Gradle):

```
gradlew assembleRelease
```

The APK contains two ABIs: `arm64-v8a` (real devices) and `x86_64`
(emulators).

## Installing and running

```
adb install app-release.apk
```

Open the "Server Protocol Bridge" app: the built-in WebView shows the control
panel, the same as the desktop version.  Program data (config.json, certs,
accounts) lives in the app's private directory:

```
/data/data/com.serverprotocolbridge/files/ServerProtocolBridge/
```

You can browse and edit it in Android Studio's **Device Explorer** (View →
Tool Windows → Device Explorer).

## Notes

- **Certificate trust**: the proxy's wss:// uses a self-signed CA.  On the
  desktop the client trusts the connection only after the CA is installed; on
  Android you likewise need to install `certs/cert.pem` into the system/user
  trusted CAs (Settings → Security → Encryption & credentials → Install a
  certificate), otherwise the web client will report a certificate error when
  connecting to `wss://127.0.0.1:8443`.  This is the same limitation as the
  desktop build, not APK-specific.
- **Network permissions**: `INTERNET` + `ACCESS_NETWORK_STATE` are declared in
  the manifest; cleartext `http://127.0.0.1` is allowed only for localhost via
  network_security_config, and everything else uses the secure default (no
  cleartext).
- **Account sign-in**: the Microsoft/Java account sign-in in the panel calls
  `window.open`, which opens the authorization page in the **system browser**;
  after signing in you return to the panel.
- **Data directory**: `proxy/utils.py`'s `data_dir()` resolves to
  `$HOME/ServerProtocolBridge` on Android (`HOME` = the app's internal storage,
  which Chaquopy guarantees to be writable and persistent until uninstall).
- **Certificate generation**: Android has no openssl binary, so
  `proxy/certs.py` falls back automatically to the pure-Python (cryptography)
  generator.
