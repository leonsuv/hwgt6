package de.saigak.opelbridge

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import org.json.JSONObject

/**
 * Haelt die Bruecke am Leben: fragt das Fahrzeug im Intervall ab und bedient
 * den HTTP-Server fuer die Uhr.
 *
 * Als Vordergrunddienst mit sichtbarer Benachrichtigung - anders laesst
 * Android einen dauerhaft lauschenden Socket nicht zu.
 */
class BridgeService : Service(), WatchServer.DataProvider {

    private lateinit var store: Store
    private var server: WatchServer? = null
    private var wear: WearLink? = null

    private var pollThread: Thread? = null

    @Volatile
    private var stopping = false

    override fun onCreate() {
        super.onCreate()
        store = VehicleData.store(this)
        running = true
        startForeground(NOTIFICATION_ID, buildNotification("startet ..."))
        startServer()
        startWear()
        startPolling()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action == ACTION_REFRESH) {
            Thread { fetch(true) }.start()
        }
        if (intent?.action == ACTION_PAIR_WATCH) {
            wear?.requestPermission()
        }
        if (intent?.action == ACTION_RECONNECT_WATCH) {
            wear?.connect()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        stopping = true
        running = false
        server?.stop()
        server = null
        wear?.disconnect()
        wear = null
        watchState = "nicht verbunden"
        pollThread?.interrupt()
        pollThread = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ------------------------------------------------------------ Server
    private fun startServer() {
        try {
            val instance = WatchServer(store.port, store.watchToken, this)
            instance.start()
            server = instance
            lastMessage = "Server auf Port ${store.port}"
        } catch (e: Exception) {
            lastMessage = "Port ${store.port} belegt: ${e.message}"
            Log.e(TAG, "Server-Start fehlgeschlagen", e)
        }
        updateNotification()
    }

    // ------------------------------------------------------- Wear Engine
    private fun startWear() {
        val link = WearLink(this, this) { text ->
            watchState = text
            updateNotification()
        }
        wear = link
        link.connect()
    }

    // ------------------------------------------------------------ Abruf
    private fun startPolling() {
        pollThread = Thread({
            while (!stopping) {
                try {
                    fetch(true)
                } catch (e: Exception) {
                    Log.w(TAG, "Poller: ${e.message}")
                }
                try {
                    Thread.sleep(maxOf(60, store.pollSeconds) * 1000L)
                } catch (e: InterruptedException) {
                    return@Thread
                }
            }
        }, "opel-poller").also { it.start() }
    }

    /** Daten holen (gemeinsame Logik in VehicleData) und Benachrichtigung auffrischen. */
    private fun fetch(@Suppress("UNUSED_PARAMETER") force: Boolean): Boolean {
        val ok = VehicleData.fetch(this)
        lastMessage = VehicleData.lastMessage
        updateNotification()
        return ok
    }

    // -------------------------------------------- WatchServer.DataProvider
    override fun watchPayload(force: Boolean): JSONObject? {
        val payload = VehicleData.watchPayload(this, force)
        lastMessage = VehicleData.lastMessage
        updateNotification()
        return payload
    }

    override fun rawState(): JSONObject? = VehicleData.rawStatus

    override fun info(): JSONObject = VehicleData.info(this)

    // ----------------------------------------------------- Benachrichtigung
    private fun buildNotification(text: String): Notification {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Opel Bridge", NotificationManager.IMPORTANCE_LOW
            )
            channel.description = "Liefert Fahrzeugdaten an die Uhr"
            manager.createNotificationChannel(channel)
        }
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val stop = PendingIntent.getService(
            this, 1, Intent(this, BridgeService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle("Opel Bridge")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentIntent(open)
            .setOngoing(true)
            .addAction(
                Notification.Action.Builder(null, "Beenden", stop).build()
            )
            .build()
    }

    private fun updateNotification() {
        try {
            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.notify(NOTIFICATION_ID, buildNotification(lastMessage))
        } catch (e: Exception) {
            // Benachrichtigung ist Nebensache - den Dienst nie daran scheitern lassen
        }
    }

    companion object {
        const val ACTION_STOP = "de.saigak.opelbridge.STOP"
        const val ACTION_REFRESH = "de.saigak.opelbridge.REFRESH"
        const val ACTION_PAIR_WATCH = "de.saigak.opelbridge.PAIR_WATCH"
        const val ACTION_RECONNECT_WATCH = "de.saigak.opelbridge.RECONNECT_WATCH"
        private const val CHANNEL_ID = "opelbridge"
        private const val NOTIFICATION_ID = 4711
        private const val TAG = "BridgeService"

        /** Fuer die Oberflaeche: laeuft der Dienst gerade? */
        @Volatile
        var running: Boolean = false
            private set

        /** Letzte Statusmeldung, wird in der App angezeigt. */
        @Volatile
        var lastMessage: String = "gestoppt"
            private set

        /** Zustand der Wear-Engine-Verbindung zur Uhr. */
        @Volatile
        var watchState: String = "nicht verbunden"
            private set

        fun start(context: Context) {
            val intent = Intent(context, BridgeService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, BridgeService::class.java))
            lastMessage = "gestoppt"
        }

        fun pairWatch(context: Context) = sendAction(context, ACTION_PAIR_WATCH)
        fun reconnectWatch(context: Context) = sendAction(context, ACTION_RECONNECT_WATCH)

        private fun sendAction(context: Context, action: String) {
            val intent = Intent(context, BridgeService::class.java).setAction(action)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun refresh(context: Context) {
            val intent = Intent(context, BridgeService::class.java).setAction(ACTION_REFRESH)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
