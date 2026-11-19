package com.serverprotocolbridge;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Message;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

/**
 * The APK entry point.  pywebview is not available on Android, so the control
 * panel is the existing Flask Web UI served on 127.0.0.1 and rendered in a
 * WebView.  Python is started once (Chaquopy), then the Web UI is brought up
 * and loaded.
 */
public class MainActivity extends Activity {
    private WebView web;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }

        // Pin the process to the foreground so Android does not kill the
        // proxy when the app goes to the background (persistent notification).
        Intent keepAlive = new Intent(this, KeepAliveService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(keepAlive);
        } else {
            startService(keepAlive);
        }
        // Android 13+ needs a runtime permission to show the notification.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                   != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(
                    new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }

        // Bring up the Flask Web UI; it returns the URL the WebView should load.
        // The proxy service itself is started from the panel (ServiceManager),
        // exactly as in the desktop and browser interfaces.
        PyObject entry = Python.getInstance().getModule("proxy.android_entry");
        String url = entry.callAttr("start_web_ui").toString();

        web = new WebView(this);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(true);
        settings.setSupportMultipleWindows(true);
        settings.setMediaPlaybackRequiresUserGesture(false);

        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onCreateWindow(WebView view, boolean isDialog,
                                          boolean isUserGesture, Message resultMsg) {
                // The Web UI calls window.open() to launch the Microsoft / Java
                // account login and the REST API docs.  Open the target in the
                // system browser instead of a second embedded WebView.
                WebView.WebViewTransport transport =
                        (WebView.WebViewTransport) resultMsg.obj;
                WebView popup = new WebView(MainActivity.this);
                transport.setWebView(popup);
                resultMsg.sendToTarget();
                popup.setWebViewClient(new WebViewClient() {
                    @Override
                    public void onPageStarted(WebView view, String url, Bitmap favicon) {
                        try {
                            startActivity(new Intent(Intent.ACTION_VIEW,
                                    Uri.parse(url)));
                        } catch (Exception ignored) {
                            // No browser installed; leave the popup as-is.
                        }
                        view.destroy();
                    }
                });
                return true;
            }
        });
        web.loadUrl(url);
        setContentView(web);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode,
                                           String[] permissions,
                                           int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == 1) {
            boolean granted = grantResults.length > 0
                    && grantResults[0] == PackageManager.PERMISSION_GRANTED;
            if (!granted) {
                Toast.makeText(this,
                        "Notification permission not granted: the persistent notification "
                                + "will not show and the background proxy may be stopped by the system. "
                                + "Allow notifications in system settings.",
                        Toast.LENGTH_LONG).show();
            }
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
