package de.saigak.opelbridge

import android.content.Context
import org.json.JSONObject

/**
 * Marken- und Laenderkonfiguration.
 *
 * Die Werte stammen unveraendert aus assets/brands.json (aus dem opelapi-Repo),
 * damit App und Python-Bibliothek garantiert dieselben Endpunkte benutzen.
 */
object Brands {

    private var root: JSONObject? = null

    fun load(context: Context) {
        if (root != null) return
        val text = context.assets.open("brands.json").bufferedReader().use { it.readText() }
        root = JSONObject(text)
    }

    private fun require(): JSONObject =
        root ?: throw IllegalStateException("Brands.load(context) wurde nicht aufgerufen")

    val oauthUrl: String get() = require().getString("oauth_url")
    val realm: String get() = require().getString("realm")
    val scheme: String get() = require().getString("scheme")

    val authorizeUrl: String get() = "$oauthUrl/am/oauth2/authorize"
    val tokenUrl: String get() = "$oauthUrl/am/oauth2/access_token"

    fun countries(): List<String> {
        val configs = require().getJSONObject("configs")
        return configs.keys().asSequence().toList().sorted()
    }

    fun has(country: String): Boolean =
        require().getJSONObject("configs").has(country.uppercase())

    private fun config(country: String): JSONObject {
        val configs = require().getJSONObject("configs")
        val key = country.uppercase()
        if (!configs.has(key)) {
            throw IllegalArgumentException("Land $key unbekannt. Bekannt: ${countries().joinToString()}")
        }
        return configs.getJSONObject(key)
    }

    fun locale(country: String): String = config(country).getString("locale")
    fun clientId(country: String): String = config(country).getString("client_id")
    fun clientSecret(country: String): String = config(country).getString("client_secret")

    /** mymopsdk://oauth2redirect/de - die App-Rueckleitung nach dem Login. */
    fun redirectUri(country: String): String = "$scheme://oauth2redirect/${country.lowercase()}"

    object Api {
        const val BASE = "https://api.groupe-psa.com"
        const val VEHICLES = "$BASE/connectedcar/v4/user/vehicles"
        const val USER_AGENT = "okhttp/4.8.0"
        fun status(vehicleId: String) = "$VEHICLES/$vehicleId/status"
    }
}
