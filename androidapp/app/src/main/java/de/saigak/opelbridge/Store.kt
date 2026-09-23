package de.saigak.opelbridge

import android.content.Context
import android.content.SharedPreferences
import java.security.SecureRandom

/**
 * Dauerhafter Speicher fuer Tokens und Einstellungen.
 *
 * Liegt in den privaten App-Daten (MODE_PRIVATE): ohne Root kommt keine andere
 * App daran. Die Tokens sind so viel wert wie ein Autoschluessel - daher
 * werden sie nie geloggt und nie ueber das Netz ausgegeben.
 */
class Store(context: Context) {

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences("opelbridge", Context.MODE_PRIVATE)

    // -------------------------------------------------------------- OAuth
    var country: String
        get() = prefs.getString(KEY_COUNTRY, "DE") ?: "DE"
        set(value) = prefs.edit().putString(KEY_COUNTRY, value.uppercase()).apply()

    var accessToken: String?
        get() = prefs.getString(KEY_ACCESS, null)
        set(value) = prefs.edit().putString(KEY_ACCESS, value).apply()

    var refreshToken: String?
        get() = prefs.getString(KEY_REFRESH, null)
        set(value) = prefs.edit().putString(KEY_REFRESH, value).apply()

    /** Ablauf des Access-Tokens in Millisekunden seit 1970. */
    var expiresAt: Long
        get() = prefs.getLong(KEY_EXPIRES, 0L)
        set(value) = prefs.edit().putLong(KEY_EXPIRES, value).apply()

    val loggedIn: Boolean get() = !refreshToken.isNullOrBlank()

    /** Token gilt als abgelaufen, wenn weniger als fuenf Minuten uebrig sind. */
    val accessTokenExpired: Boolean
        get() = accessToken.isNullOrBlank() || System.currentTimeMillis() > expiresAt - 5 * 60_000L

    fun saveTokens(access: String, refresh: String?, expiresInSeconds: Long) {
        prefs.edit()
            .putString(KEY_ACCESS, access)
            .apply()
        if (!refresh.isNullOrBlank()) {
            prefs.edit().putString(KEY_REFRESH, refresh).apply()
        }
        expiresAt = System.currentTimeMillis() + expiresInSeconds * 1000L
    }

    fun logout() {
        prefs.edit()
            .remove(KEY_ACCESS)
            .remove(KEY_REFRESH)
            .remove(KEY_EXPIRES)
            .remove(KEY_VEHICLE_ID)
            .remove(KEY_VEHICLE_NAME)
            .remove(KEY_VIN)
            .remove(KEY_LAST_STATE)
            .apply()
    }

    // ------------------------------------------------------------ Fahrzeug
    var vehicleId: String?
        get() = prefs.getString(KEY_VEHICLE_ID, null)
        set(value) = prefs.edit().putString(KEY_VEHICLE_ID, value).apply()

    var vin: String?
        get() = prefs.getString(KEY_VIN, null)
        set(value) = prefs.edit().putString(KEY_VIN, value).apply()

    var vehicleName: String?
        get() = prefs.getString(KEY_VEHICLE_NAME, null)
        set(value) = prefs.edit().putString(KEY_VEHICLE_NAME, value).apply()

    // --------------------------------------------------------------- Uhr
    /** Shared Secret, das die Uhr mitschickt. Beim ersten Start gewuerfelt. */
    var watchToken: String
        get() {
            val existing = prefs.getString(KEY_WATCH_TOKEN, null)
            if (!existing.isNullOrBlank()) return existing
            // Beim Bauen aus der config.js der Uhr uebernommen, sonst gewuerfelt
            val generated = BuildConfig.DEFAULT_WATCH_TOKEN.ifBlank { randomToken() }
            prefs.edit().putString(KEY_WATCH_TOKEN, generated).apply()
            return generated
        }
        set(value) = prefs.edit().putString(KEY_WATCH_TOKEN, value).apply()

    var port: Int
        get() = prefs.getInt(KEY_PORT, 8787)
        set(value) = prefs.edit().putInt(KEY_PORT, value).apply()

    /** Abfrageintervall in Sekunden - Standard 5 Minuten, wie in der Bridge. */
    var pollSeconds: Int
        get() = prefs.getInt(KEY_POLL, 300)
        set(value) = prefs.edit().putInt(KEY_POLL, value).apply()

    var autostart: Boolean
        get() = prefs.getBoolean(KEY_AUTOSTART, true)
        set(value) = prefs.edit().putBoolean(KEY_AUTOSTART, value).apply()

    // ------------------------------------------------------------- Cache
    /** Letzte erfolgreich geholte Uhr-Nutzlast, damit die Uhr sofort etwas sieht. */
    var lastState: String?
        get() = prefs.getString(KEY_LAST_STATE, null)
        set(value) = prefs.edit().putString(KEY_LAST_STATE, value).apply()

    var lastStateAt: Long
        get() = prefs.getLong(KEY_LAST_STATE_AT, 0L)
        set(value) = prefs.edit().putLong(KEY_LAST_STATE_AT, value).apply()

    var lastError: String?
        get() = prefs.getString(KEY_LAST_ERROR, null)
        set(value) = prefs.edit().putString(KEY_LAST_ERROR, value).apply()

    private fun randomToken(): String {
        val alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        val random = SecureRandom()
        val builder = StringBuilder(24)
        repeat(24) { builder.append(alphabet[random.nextInt(alphabet.length)]) }
        return builder.toString()
    }

    private companion object {
        const val KEY_COUNTRY = "country"
        const val KEY_ACCESS = "access_token"
        const val KEY_REFRESH = "refresh_token"
        const val KEY_EXPIRES = "expires_at"
        const val KEY_VEHICLE_ID = "vehicle_id"
        const val KEY_VEHICLE_NAME = "vehicle_name"
        const val KEY_VIN = "vin"
        const val KEY_WATCH_TOKEN = "watch_token"
        const val KEY_PORT = "port"
        const val KEY_POLL = "poll_seconds"
        const val KEY_AUTOSTART = "autostart"
        const val KEY_LAST_STATE = "last_state"
        const val KEY_LAST_STATE_AT = "last_state_at"
        const val KEY_LAST_ERROR = "last_error"
    }
}
