package de.saigak.opelbridge

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.util.concurrent.locks.ReentrantLock

/**
 * Abruf und Zwischenspeicher der Fahrzeugdaten - gemeinsam fuer
 * BridgeService (HTTP, Poller) und WatchProvider (Gadgetbridge).
 *
 * Bewusst ohne laufenden Dienst nutzbar: der Provider wird von Android bei
 * Bedarf gestartet, auch wenn das System den Prozess vorher beendet hat.
 */
object VehicleData {
    private const val TAG = "VehicleData"
    private val lock = ReentrantLock()

    @Volatile
    var rawStatus: JSONObject? = null
        private set

    @Volatile
    var lastMessage: String = "gestoppt"
        private set

    private var store: Store? = null
    private var api: OpelApi? = null

    @Synchronized
    fun store(context: Context): Store {
        store?.let { return it }
        Brands.load(context.applicationContext)
        val created = Store(context.applicationContext)
        store = created
        api = OpelApi(created)
        return created
    }

    private fun api(context: Context): OpelApi {
        store(context)
        return api!!
    }

    /** Daten frisch holen und im Store ablegen. Gibt true bei Erfolg zurueck. */
    fun fetch(context: Context): Boolean {
        val store = store(context)
        if (!store.loggedIn) {
            store.lastError = "Nicht angemeldet"
            lastMessage = "Nicht angemeldet"
            return false
        }
        if (!lock.tryLock()) {
            // Laeuft bereits (Poller oder andere Anfrage) - auf deren Ergebnis warten
            lock.lock()
            lock.unlock()
            return store.lastError == null
        }
        try {
            val api = api(context)
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
            if (lock.isHeldByCurrentThread) lock.unlock()
        }
        return false
    }

    /**
     * Nutzlast fuer die Uhr. Fragt das Fahrzeug nur neu ab, wenn erzwungen
     * oder der Zwischenspeicher aelter als das Abfrageintervall ist.
     */
    fun watchPayload(context: Context, force: Boolean): JSONObject? {
        val store = store(context)
        val cacheAge = System.currentTimeMillis() / 1000 - store.lastStateAt
        if (force || store.lastState == null || cacheAge > maxOf(60, store.pollSeconds)) {
            fetch(context)
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

    fun info(context: Context): JSONObject {
        val store = store(context)
        return JSONObject()
            .put("ok", store.lastError == null)
            .put("provider", "android")
            .put("logged_in", store.loggedIn)
            .put("country", store.country)
            .put("vehicle", store.vehicleName ?: "")
            .put("poll_interval_s", store.pollSeconds)
            .put("cache_age_s", if (store.lastStateAt > 0) System.currentTimeMillis() / 1000 - store.lastStateAt else JSONObject.NULL)
            .put("last_error", store.lastError ?: JSONObject.NULL)
            .put("commands", false)
            .put("config", JSONObject().put("provider", "android"))
    }
}
