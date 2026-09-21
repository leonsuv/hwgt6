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
import java.util.concurrent.locks.ReentrantLock

/**
 * Haelt die Bruecke am Leben: fragt das Fahrzeug im Intervall ab und bedient
 * den HTTP-Server fuer die Uhr.
 *
 * Als Vordergrunddienst mit sichtbarer Benachrichtigung - anders laesst
 * Android einen dauerhaft lauschenden Socket nicht zu.
 */
class BridgeService : Service(), WatchServer.DataProvider {

    private lateinit var store: Store
    private lateinit var api: OpelApi
    private var server: WatchServer? = null

    private val fetchLock = ReentrantLock()
    private var pollThread: Thread? = null

    @Volatile
    private var stopping = false

    @Volatile
    private var rawStatus: JSONObject? = null

    override fun onCreate() {
        super.onCreate()
        Brands.load(this)
        store = Store(this)
        api = OpelApi(store)
        running = true
        startForeground(NOTIFICATION_ID, buildNotification("startet ..."))
        startServer()
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
        return START_STICKY
    }

    override fun onDestroy() {
        stopping = true
        running = false
        server?.stop()
        server = null
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

    /** Daten holen und im Store ablegen. Gibt true bei Erfolg zurueck. */
    private fun fetch(force: Boolean): Boolean {
        if (!store.loggedIn) {
            store.lastError = "Nicht angemeldet"
            lastMessage = "Nicht angemeldet"
            updateNotification()
            return false
        }
        if (!fetchLock.tryLock()) return false          // laeuft bereits
        try {
            val (vehicleId, _, name) = api.resolveVehicle()
            val raw = api.status(vehicleId)
            rawStatus = raw
            val payload = Normalize.toWatchPayload(raw, name)
            store.lastState = payload.toString()
            store.lastStateAt = System.currentTimeMillis() / 1000
            store.lastError = null
            lastMessage = "%s  %s%%  %s km".format(
                name,
                payload.opt("lvl")?.toString() ?: "--",
                payload.opt("rng")?.toString() ?: "--"
            )
            updateNotification()
            return true
        } catch (e: AuthException) {
            store.lastError = "Anmeldung abgelaufen: ${e.message}"
            lastMessage = "Anmeldung abgelaufen - neu anmelden"
            Log.w(TAG, "Auth: ${e.message}")
        } catch (e: Exception) {
            store.lastError = e.message ?: e.toString()
            lastMessage = "Fehler: ${e.message}"
            Log.w(TAG, "Abruf: ${e.message}")
        } finally {
            fetchLock.unlock()
            updateNotification()
        }
        return false
    }

    // -------------------------------------------- WatchServer.DataProvider
    override fun watchPayload(force: Boolean): JSONObject? {
        val cacheAge = System.currentTimeMillis() / 1000 - store.lastStateAt
        if (force || store.lastState == null || cacheAge > maxOf(60, store.pollSeconds)) {
            fetch(true)
        }
        val cached = store.lastState ?: return null
        return try {
            val payload = Normalize.refreshAge(JSONObject(cached), store.lastStateAt)
            store.lastError?.let { payload.put("err", it.take(120)) }
            payload
        } catch (e: Exception) {
            null
        }
    }

    override fun rawState(): JSONObject? = rawStatus

    override fun info(): JSONObject = JSONObject()
        .put("ok", store.lastError == null)
        .put("provider", "android")
        .put("logged_in", store.loggedIn)
        .put("country", store.country)
        .put("vehicle", store.vehicleName ?: "")
        .put("poll_interval_s", store.pollSeconds)
        .put("cache_age_s", System.currentTimeMillis() / 1000 - store.lastStateAt)
        .put("last_error", store.lastError ?: JSONObject.NULL)
        .put("commands", false)
        .put("config", JSONObject().put("provider", "android"))

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
