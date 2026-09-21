package de.saigak.opelbridge

import android.util.Log
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.URLDecoder
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Winziger HTTP-Server auf dem Telefon, von dem die Uhr ihre Daten holt.
 *
 * Warum auf dem Telefon: Die Watch GT6 hat fuer Apps kein eigenes
 * IP-Networking. Jede Anfrage aus der Uhr-App wird von Huawei Health durch
 * das gekoppelte Telefon geleitet - dort endet sie dann hier, entweder ueber
 * 127.0.0.1 oder ueber die WLAN-Adresse des Telefons.
 *
 * Die Schnittstelle ist identisch zur Python-Bridge, damit dieselbe Uhr-App
 * mit beiden Quellen funktioniert.
 */
class WatchServer(
    private val port: Int,
    private val token: String,
    private val provider: DataProvider
) {

    /** Was der Server an Daten braucht - wird vom BridgeService geliefert. */
    interface DataProvider {
        /** Zwischengespeicherte Uhr-Nutzlast oder null. */
        fun watchPayload(force: Boolean): JSONObject?

        /** Roher Fahrzeugstatus fuer /state. */
        fun rawState(): JSONObject?

        /** Kurzinfo ueber den Zustand der Bruecke. */
        fun info(): JSONObject
    }

    @Volatile
    private var running = false
    private var socket: ServerSocket? = null
    private var acceptThread: Thread? = null
    private val workers: ExecutorService = Executors.newFixedThreadPool(4)

    val isRunning: Boolean get() = running

    fun start() {
        if (running) return
        val server = ServerSocket()
        server.reuseAddress = true
        // An alle Schnittstellen binden: die Uhr kommt je nach Geraet ueber
        // 127.0.0.1 oder ueber die WLAN-Adresse des Telefons herein.
        server.bind(InetSocketAddress("0.0.0.0", port))
        socket = server
        running = true
        acceptThread = Thread({
            Log.i(TAG, "Uhr-Server laeuft auf Port $port")
            while (running) {
                try {
                    val client = server.accept()
                    workers.execute { handle(client) }
                } catch (e: Exception) {
                    if (running) Log.w(TAG, "accept: ${e.message}")
                }
            }
        }, "watch-server").also { it.start() }
    }

    fun stop() {
        running = false
        try {
            socket?.close()
        } catch (e: Exception) {
            // egal - der Server wird ohnehin beendet
        }
        socket = null
        acceptThread = null
    }

    // ------------------------------------------------------------ Anfrage
    private fun handle(client: Socket) {
        try {
            client.soTimeout = 15000
            val reader = BufferedReader(InputStreamReader(client.getInputStream(), Charsets.UTF_8))
            val requestLine = reader.readLine() ?: return
            val parts = requestLine.split(" ")
            if (parts.size < 2) return
            val method = parts[0].uppercase()
            val target = parts[1]

            var suppliedToken = ""
            var contentLength = 0
            while (true) {
                val line = reader.readLine() ?: break
                if (line.isEmpty()) break
                val index = line.indexOf(':')
                if (index <= 0) continue
                val key = line.substring(0, index).trim().lowercase()
                val value = line.substring(index + 1).trim()
                when (key) {
                    "x-token" -> suppliedToken = value
                    "authorization" ->
                        if (value.startsWith("Bearer ", true)) suppliedToken = value.substring(7).trim()
                    "content-length" -> contentLength = value.toIntOrNull() ?: 0
                }
            }
            if (contentLength > 0) {
                val body = CharArray(minOf(contentLength, 8192))
                reader.read(body)                       // Rumpf verwerfen
            }

            val path = target.substringBefore('?')
            val query = parseQuery(target.substringAfter('?', ""))
            if (suppliedToken.isBlank()) {
                suppliedToken = query["t"] ?: query["token"] ?: ""
            }

            route(client.getOutputStream(), method, path.trimEnd('/').ifEmpty { "/" },
                query, suppliedToken)
        } catch (e: Exception) {
            Log.w(TAG, "Anfrage fehlgeschlagen: ${e.message}")
        } finally {
            try {
                client.close()
            } catch (e: Exception) {
                // ignorieren
            }
        }
    }

    private fun parseQuery(query: String): Map<String, String> {
        if (query.isBlank()) return emptyMap()
        val result = HashMap<String, String>()
        for (pair in query.split("&")) {
            if (pair.isBlank()) continue
            val index = pair.indexOf('=')
            try {
                if (index < 0) {
                    result[URLDecoder.decode(pair, "UTF-8")] = ""
                } else {
                    result[URLDecoder.decode(pair.substring(0, index), "UTF-8")] =
                        URLDecoder.decode(pair.substring(index + 1), "UTF-8")
                }
            } catch (e: Exception) {
                // kaputte Kodierung ignorieren
            }
        }
        return result
    }

    private fun route(
        out: OutputStream,
        method: String,
        path: String,
        query: Map<String, String>,
        suppliedToken: String
    ) {
        if (method == "OPTIONS") {
            send(out, 204, "")
            return
        }
        if (path == "/health" || path == "/api/v1/health") {
            send(out, 200, JSONObject().put("ok", true)
                .put("t", System.currentTimeMillis() / 1000).toString())
            return
        }
        if (path == "/") {
            send(out, 200, "Opel Bridge (Android) laeuft. Endpunkt: /api/v1/watch?t=...",
                "text/plain")
            return
        }
        if (!path.startsWith("/api/v1")) {
            send(out, 404, JSONObject().put("error", "not_found").toString())
            return
        }
        // Zeitkonstanter Vergleich, damit das Token nicht erratbar wird
        if (!constantTimeEquals(suppliedToken, token)) {
            send(out, 401, JSONObject().put("error", "unauthorized")
                .put("hint", "X-Token Header oder ?t=<token>").toString())
            return
        }

        val force = query["force"] == "1" || query["force"] == "true"
        when {
            path == "/api/v1/watch" -> {
                val payload = provider.watchPayload(force)
                if (payload == null) {
                    send(out, 503, JSONObject().put("error", "no_data")
                        .put("detail", "noch keine Fahrzeugdaten geladen").toString())
                } else {
                    send(out, 200, payload.toString())
                }
            }
            path == "/api/v1/state" -> {
                val raw = provider.rawState()
                send(
                    out,
                    if (raw == null) 503 else 200,
                    (raw ?: JSONObject().put("error", "no_data")).toString()
                )
            }
            path == "/api/v1/refresh" -> {
                val payload = provider.watchPayload(true)
                send(
                    out,
                    if (payload == null) 503 else 200,
                    JSONObject().put("ok", payload != null)
                        .put("data", payload ?: JSONObject.NULL).toString()
                )
            }
            path == "/api/v1/info" -> send(out, 200, provider.info().toString())
            path.startsWith("/api/v1/command/") -> send(
                out, 501,
                JSONObject()
                    .put("ok", false)
                    .put(
                        "error",
                        "Fernbefehle brauchen die MQTT-Anmeldung mit OTP und sind in " +
                            "der Android-Bruecke nicht enthalten. Dafuer die Python-Bridge " +
                            "mit Provider 'opelapi' verwenden."
                    ).toString()
            )
            else -> send(out, 404, JSONObject().put("error", "not_found").toString())
        }
    }

    private fun constantTimeEquals(a: String, b: String): Boolean {
        if (a.length != b.length) return false
        var diff = 0
        for (index in a.indices) {
            diff = diff or (a[index].code xor b[index].code)
        }
        return diff == 0
    }

    private fun send(out: OutputStream, status: Int, body: String,
                     contentType: String = "application/json") {
        val reason = when (status) {
            200 -> "OK"
            204 -> "No Content"
            401 -> "Unauthorized"
            404 -> "Not Found"
            501 -> "Not Implemented"
            503 -> "Service Unavailable"
            else -> "OK"
        }
        val bytes = body.toByteArray(Charsets.UTF_8)
        val header = StringBuilder()
        header.append("HTTP/1.1 $status $reason\r\n")
        header.append("Content-Type: $contentType; charset=utf-8\r\n")
        header.append("Content-Length: ${bytes.size}\r\n")
        header.append("Cache-Control: no-store\r\n")
        header.append("Access-Control-Allow-Origin: *\r\n")
        header.append("Access-Control-Allow-Headers: X-Token, Authorization, Content-Type\r\n")
        header.append("Connection: close\r\n\r\n")
        out.write(header.toString().toByteArray(Charsets.US_ASCII))
        out.write(bytes)
        out.flush()
    }

    private companion object {
        const val TAG = "WatchServer"
    }
}
