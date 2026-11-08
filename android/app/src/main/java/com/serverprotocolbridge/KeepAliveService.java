package com.serverprotocolbridge;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

/**
 * Foreground "keep-alive" service.
 *
 * Android kills background processes when the user leaves the app; the proxy
 * must keep running to serve the Minecraft connection, so a persistent
 * notification is shown and the process is pinned to the foreground.  The
 * user can tap the notification to return to the control panel.
 */
public class KeepAliveService extends Service {
    private static final String CHANNEL_ID = "spb_keepalive";
    private static final int NOTIFICATION_ID = 0x5350; // 'SP'

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        // Must be called within a few seconds of startForegroundService().
        startForeground(NOTIFICATION_ID, buildNotification());
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // Restart automatically if the system kills us (best effort).
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.app_name),
                    NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Keep Server Protocol Bridge running in the background");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private Notification buildNotification() {
        Intent launch = new Intent(this, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(
                this, 0, launch,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return builder
                .setContentTitle(getString(R.string.app_name))
                .setContentText("Proxy service is running")
                .setSmallIcon(R.drawable.ic_stat_bridge)
                .setContentIntent(pending)
                .setOngoing(true)
                .build();
    }
}
