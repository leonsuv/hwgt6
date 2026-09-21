package de.saigak.opelbridge

import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

class AuthException(message: String) : Exception(message)
class ApiException(message: String, val status: Int = 0) : Exception(message)

/**
 * Zugriff auf die MyOpel-/Stellantis-Schnittstelle.
 *
 * Logik eins zu eins aus der funktionierenden Python-Bibliothek 'opelapi'
 * uebernommen (auth.py / client.py):
 *
 *  - Autorisierungsanfrage mit UNKODIERTEN Query-Parametern. Die ForgeRock-
 *    Endpunkte weisen prozentkodierte redirect_uri/scope ab.
 *  - Token-Tausch und -Erneuerung per HTTP-Basic aus client_id:client_secret,
 *    Parameter ebenfalls in der URL.
 *  - Lesezugriffe mit Bearer-Token, x-introspect-realm und client_id+locale.
 */
class OpelApi(private val store: Store) {

    // ------------------------------------------------------------- Helfer
    private val country: String get() = store.country

    /** Query ohne Prozentkodierung - genau so senden es die Apps. */
    private fun rawQuery(params: List<Pair<String, String>>): String =
        params.joinToString("&") { "${it.first}=${it.second}" }

    private fun basicAuth(): String {
        val raw = "${Brands.clientId(country)}:${Brands.clientSecret(country)}"
        return "Basic " + Base64.encodeToString(raw.toByteArray(Charsets.UTF_8), Base64.NO_WRAP)
    }

    private fun readBody(connection: HttpURLConnection): String {
        val stream = (if (connection.responseCode >= 400) connection.errorStream
        else connection.inputStream) ?: return ""
        return BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { it.readText() }
    }

    private fun jsonOrThrow(connection: HttpURLConnection, what: String): JSONObject {
        val code = connection.responseCode
        val body = readBody(connection)
        val payload = try {
            if (body.isBlank()) JSONObject() else JSONObject(body)
        } catch (e: Exception) {
            JSONObject()
        }
        if (code >= 400) {
            val message = payload.optString(
                "error_description",
                payload.optString("moreInformation", payload.optString("message", body.take(200)))
            )
            if (code == 400 || code == 401) {
                if (payload.optString("error") == "invalid_grant" || code == 401) {
                    throw AuthException("$what abgelehnt ($code): $message")
                }
            }
            throw ApiException("$what fehlgeschlagen ($code): $message", code)
        }
        return payload
    }

    // ---------------------------------------------------------- 1. Login
    /** Adresse der Anmeldeseite, die im WebView geoeffnet wird. */
    fun authorizeUrl(extra: List<Pair<String, String>> = emptyList()): String {
        val params = mutableListOf(
            "client_id" to Brands.clientId(country),
            "response_type" to "code",
            "redirect_uri" to Brands.redirectUri(country),
            "scope" to "openid%20profile%20email",
            "locale" to Brands.locale(country)
        )
        params.addAll(extra)
        return Brands.authorizeUrl + "?" + rawQuery(params)
    }

    /** 'code' aus der Rueckleitungs-URL herausziehen. */
    fun extractCode(redirectUrl: String): String? {
        val marker = "code="
        val index = redirectUrl.indexOf(marker)
        if (index < 0) return null
        var code = redirectUrl.substring(index + marker.length)
        val end = code.indexOfFirst { it == '&' || it == '#' }
        if (end >= 0) code = code.substring(0, end)
        return code.ifBlank { null }
    }

    /**
     * Rettungsweg, wenn die Zustimmungsseite haengen bleibt.
     *
     * Mit dem Sitzungs-Cookie iPlanetDirectoryPro fragt man den Code direkt an:
     * erst normal, dann mit inline erteilter Zustimmung - genau das, was die
     * kaputte Seite sonst absenden wuerde.
     */
    fun codeFromSsoCookie(ssoToken: String): String {
        val attempts = listOf(
            emptyList(),
            listOf("decision" to "allow", "save_consent" to "on", "csrf" to ssoToken)
        )
        val seen = StringBuilder()
        for (extra in attempts) {
            val connection = URL(authorizeUrl(extra)).openConnection() as HttpURLConnection
            try {
                connection.instanceFollowRedirects = false
                connection.requestMethod = "GET"
                connection.setRequestProperty("User-Agent", Brands.Api.USER_AGENT)
                connection.setRequestProperty("Accept", "*/*")
                connection.setRequestProperty("Cookie", "iPlanetDirectoryPro=$ssoToken")
                connection.connectTimeout = 20000
                connection.readTimeout = 20000
                val location = connection.getHeaderField("Location") ?: ""
                seen.append("\n  ${connection.responseCode} -> ${location.take(110)}")
                if (location.startsWith(Brands.scheme + "://") && location.contains("code=")) {
                    return extractCode(location)
                        ?: throw AuthException("Rueckleitung ohne code: $location")
                }
            } finally {
                connection.disconnect()
            }
        }
        throw AuthException(
            "Kein Autorisierungscode aus der Sitzung zu holen.$seen\n" +
                "Das Cookie ist vermutlich abgelaufen - bitte neu anmelden."
        )
    }

    /** Einmal-Code gegen Access- und Refresh-Token tauschen. */
    fun exchangeCode(code: String) {
        val params = listOf(
            "redirect_uri" to Brands.redirectUri(country),
            "grant_type" to "authorization_code",
            "code" to code
        )
        val payload = postToken(params, "Token-Tausch")
        storeTokens(payload)
    }

    /** Access-Token mit dem Refresh-Token erneuern. */
    fun refresh() {
        val refreshToken = store.refreshToken
            ?: throw AuthException("Kein Refresh-Token gespeichert - bitte neu anmelden.")
        val params = listOf(
            "grant_type" to "refresh_token",
            "refresh_token" to refreshToken
        )
        val payload = postToken(params, "Token-Erneuerung")
        storeTokens(payload)
    }

    private fun postToken(params: List<Pair<String, String>>, what: String): JSONObject {
        val url = URL(Brands.tokenUrl + "?" + rawQuery(params))
        val connection = url.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            connection.setRequestProperty("Authorization", basicAuth())
            connection.setRequestProperty("User-Agent", Brands.Api.USER_AGENT)
            connection.setRequestProperty("Accept", "application/json")
            connection.connectTimeout = 25000
            connection.readTimeout = 25000
            connection.outputStream.use { it.write(ByteArray(0)) }
            return jsonOrThrow(connection, what)
        } finally {
            connection.disconnect()
        }
    }

    private fun storeTokens(payload: JSONObject) {
        val access = payload.optString("access_token")
        if (access.isBlank()) throw AuthException("Antwort ohne access_token")
        val refresh = payload.optString("refresh_token").takeIf { it.isNotBlank() }
        store.saveTokens(access, refresh, payload.optLong("expires_in", 3600L))
    }

    /** Gueltiges Access-Token, erneuert bei Bedarf selbsttaetig. */
    @Synchronized
    fun accessToken(): String {
        if (store.accessTokenExpired) refresh()
        return store.accessToken ?: throw AuthException("Kein Access-Token")
    }

    // ----------------------------------------------------------- 2. Lesen
    private fun apiGet(baseUrl: String, retryAuth: Boolean = true): JSONObject {
        val token = accessToken()
        val separator = if (baseUrl.contains("?")) "&" else "?"
        val url = URL(
            baseUrl + separator +
                "client_id=${Brands.clientId(country)}&locale=${Brands.locale(country)}"
        )
        val connection = url.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "GET"
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.setRequestProperty("x-introspect-realm", Brands.realm)
            connection.setRequestProperty("User-Agent", Brands.Api.USER_AGENT)
            connection.setRequestProperty("Accept", "application/hal+json")
            connection.connectTimeout = 25000
            connection.readTimeout = 30000

            val code = connection.responseCode
            if ((code == 401 || code == 403) && retryAuth) {
                store.expiresAt = 0                       // Erneuerung erzwingen
                connection.disconnect()
                return apiGet(baseUrl, retryAuth = false)
            }
            val body = readBody(connection)
            if (code == 404 && body.contains("40400")) {
                // "Kein Status fuer dieses Fahrzeug" - kein Fehler, nur leer.
                return JSONObject()
            }
            if (code >= 400) {
                throw ApiException("Abruf fehlgeschlagen ($code): ${body.take(200)}", code)
            }
            return if (body.isBlank()) JSONObject() else JSONObject(body)
        } finally {
            connection.disconnect()
        }
    }

    /** Fahrzeuge des Kontos. */
    fun vehicles(): JSONArray {
        val payload = apiGet(Brands.Api.VEHICLES)
        val embedded = payload.optJSONObject("_embedded") ?: return JSONArray()
        return embedded.optJSONArray("vehicles") ?: JSONArray()
    }

    /**
     * Fahrzeug bestimmen und merken. Ohne gespeicherte Auswahl wird das erste
     * genommen; bei mehreren Autos entscheidet die gespeicherte VIN.
     */
    fun resolveVehicle(): Triple<String, String, String> {
        val storedId = store.vehicleId
        val storedVin = store.vin
        val storedName = store.vehicleName
        if (!storedId.isNullOrBlank() && !storedVin.isNullOrBlank()) {
            return Triple(storedId, storedVin, storedName ?: "Opel")
        }
        val list = vehicles()
        if (list.length() == 0) throw ApiException("Keine Fahrzeuge im Konto gefunden")
        var chosen: JSONObject = list.getJSONObject(0)
        if (!storedVin.isNullOrBlank()) {
            for (index in 0 until list.length()) {
                val item = list.getJSONObject(index)
                if (item.optString("vin").equals(storedVin, ignoreCase = true)) {
                    chosen = item
                    break
                }
            }
        }
        val id = chosen.optString("id")
        val vin = chosen.optString("vin")
        var label = chosen.optString("label")
        if (label.isBlank()) {
            label = chosen.optJSONObject("_embedded")
                ?.optJSONObject("extension")
                ?.optJSONObject("vehicle")
                ?.optString("label")
                ?: "Opel"
        }
        if (label.isBlank()) label = "Opel"
        store.vehicleId = id
        store.vin = vin
        store.vehicleName = label
        return Triple(id, vin, label)
    }

    /** Rohen Fahrzeugstatus holen. */
    fun status(vehicleId: String): JSONObject = apiGet(Brands.Api.status(vehicleId))
}
