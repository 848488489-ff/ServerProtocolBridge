package com.serverprotocolbridge

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Message
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject

/**
 * The APK entry point.  pywebview is not available on Android, so the control
 * panel is the existing Web UI served on 127.0.0.1 and rendered in a WebView.
 * Python is started once (Chaquopy), then the Web UI is brought up and loaded.
 */
class MainActivity : Activity() {
    private var web: WebView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        startKeepAlive()
        // Android 13+ needs a runtime permission to show the notification.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }

        // Bring up the Web UI; it returns the URL the WebView should load.
        // The proxy service itself is started from the panel (ServiceManager),
        // exactly as in the desktop and browser interfaces.
        val entry: PyObject = Python.getInstance().getModule("proxy.android_entry")
        val url: String = entry.callAttr("start_web_ui").toString()

        val webView = WebView(this)
        val settings: WebSettings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = false
        settings.javaScriptCanOpenWindowsAutomatically = true
        settings.setSupportMultipleWindows(true)
        settings.mediaPlaybackRequiresUserGesture = false

        webView.webViewClient = WebViewClient()
        webView.webChromeClient = object : WebChromeClient() {
            override fun onCreateWindow(
                view: WebView,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: Message
            ): Boolean {
                // The Web UI calls window.open() to launch the Microsoft / Java
                // account login and the REST API docs.  Open the target in the
                // system browser instead of a second embedded WebView.
                val transport = resultMsg.obj as WebView.WebViewTransport
                val popup = WebView(this@MainActivity)
                transport.webView = popup
                resultMsg.sendToTarget()
                popup.webViewClient = object : WebViewClient() {
                    override fun onPageStarted(
                        view: WebView,
                        url: String,
                        favicon: Bitmap?
                    ) {
                        try {
                            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                        } catch (_: Exception) {
                            // No browser installed; leave the popup as-is.
                        }
                        view.destroy()
                    }
                }
                return true
            }
        }
        webView.loadUrl(url)
        web = webView
        setContentView(webView)
    }

    /** (Re)start the keep-alive service so the notification text follows the
     *  language picked in the Web UI: coming back to the app rebuilds it. */
    override fun onResume() {
        super.onResume()
        startKeepAlive()
    }

    private fun startKeepAlive() {
        val keepAlive = Intent(this, KeepAliveService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(keepAlive)
        } else {
            startService(keepAlive)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 1) {
            val granted = grantResults.isNotEmpty() &&
                grantResults[0] == PackageManager.PERMISSION_GRANTED
            if (!granted) {
                Toast.makeText(this, uiText().optString("toast_not_permitted"),
                    Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun uiText(): JSONObject = try {
        val entry: PyObject = Python.getInstance().getModule("proxy.android_entry")
        JSONObject(entry.callAttr("ui_texts").toString())
    } catch (_: Exception) {
        JSONObject()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        val current = web
        if (current != null && current.canGoBack()) {
            current.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        web?.destroy()
        web = null
        super.onDestroy()
    }
}
