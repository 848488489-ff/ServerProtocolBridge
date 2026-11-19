package com.serverprotocolbridge

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import org.json.JSONObject

/**
 * Foreground "keep-alive" service.
 *
 * Android kills background processes when the user leaves the app; the proxy
 * must keep running to serve the Minecraft connection, so a persistent
 * notification is shown and the process is pinned to the foreground.  The
 * user can tap the notification to return to the control panel.
 *
 * The notification title, content and channel description are read from the
 * Python i18n table in the active interface language, so they follow the
 * language selected in the Web UI (the service rebuilds the notification on
 * every onStartCommand, which MainActivity triggers when the app is resumed).
 */
class KeepAliveService : Service() {

    override fun onCreate() {
        super.onCreate()
        createChannel()
        // Must be called within a few seconds of startForegroundService().
        startForeground(NOTIFICATION_ID, buildNotification())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Rebuild the notification on every start: after a language switch the
        // title/content must follow the new interface language.
        startForeground(NOTIFICATION_ID, buildNotification())
        // Restart automatically if the system kills us (best effort).
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val texts = uiText()
            val channel = NotificationChannel(
                CHANNEL_ID,
                texts.optString("app_name", getString(R.string.app_name)),
                NotificationManager.IMPORTANCE_LOW
            )
            channel.description = texts.optString("notif_channel_desc")
            val manager = getSystemService(NotificationManager::class.java)
            if (manager != null) {
                manager.createNotificationChannel(channel)
            }
        }
    }

    private fun buildNotification(): Notification {
        val texts = uiText()
        val title = texts.optString("app_name", getString(R.string.app_name))
        val content = texts.optString("notif_content", "Proxy service is running")
        val launch = Intent(this, MainActivity::class.java)
        val pending = PendingIntent.getActivity(
            this, 0, launch,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            Notification.Builder(this)
        }
        return builder
            .setContentTitle(title)
            .setContentText(content)
            .setSmallIcon(R.drawable.ic_stat_bridge)
            .setContentIntent(pending)
            .setOngoing(true)
            .build()
    }

    private fun uiText(): JSONObject = try {
        val entry: PyObject = Python.getInstance().getModule("proxy.android_entry")
        JSONObject(entry.callAttr("ui_texts").toString())
    } catch (_: Exception) {
        JSONObject()
    }

    companion object {
        private const val CHANNEL_ID = "spb_keepalive"
        private const val NOTIFICATION_ID = 0x5350 // 'SP'
    }
}
