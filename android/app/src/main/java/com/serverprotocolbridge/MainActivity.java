package com.serverprotocolbridge;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.os.Message;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

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
