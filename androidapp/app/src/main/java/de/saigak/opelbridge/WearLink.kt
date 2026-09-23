package de.saigak.opelbridge

import android.content.Context
import android.util.Log
import com.huawei.wearengine.HiWear
import com.huawei.wearengine.WearEngineException
import com.huawei.wearengine.auth.AuthCallback
import com.huawei.wearengine.auth.Permission
import com.huawei.wearengine.device.Device
import com.huawei.wearengine.p2p.Message
import com.huawei.wearengine.p2p.P2pClient
import com.huawei.wearengine.p2p.Receiver
import com.huawei.wearengine.p2p.SendCallback
import org.json.JSONObject

/**
 * Nachrichtenkanal zur Uhr-App ueber Wear Engine.
 *
 * Die GT-Uhr kann aus Apps heraus nicht ins Netz - auch nicht ueber das
 * Handy. Der einzige Datenweg ist Wear Engine: Huawei Health tunnelt kleine
 * Nachrichten per Bluetooth zwischen einer Android-App und der Uhr-App,
 * sofern beide Seiten einander ueber Paketname + Zertifikat-Fingerabdruck
 * kennen und die Android-App in AppGallery Connect fuer Wear Engine
 * freigeschaltet ist.
 *
 * Protokoll (JSON-Text, unter 1 KB):
 *   Uhr  -> Handy  {"cmd":"state","force":0|1}
 *                  {"cmd":"info"}
 *                  {"cmd":"command","name":"wakeup","params":{}}
 *   Handy -> Uhr   Nutzlast wie GET /api/v1/watch bzw. /info, plus "rt".
 */
class WearLink(
    private val context: Context,
    private val provider: WatchServer.DataProvider,
    private val onStatus: (String) -> Unit
) {
    private val p2p: P2pClient = HiWear.getP2pClient(context).apply {
        setPeerPkgName(BuildConfig.WATCH_BUNDLE)
        setPeerFingerPrint(BuildConfig.WATCH_FINGERPRINT)
    }

    @Volatile
    private var device: Device? = null

    @Volatile
    var state: String = "nicht verbunden"
        private set

    private val receiver = Receiver { message ->
        val text = try {
            String(message.data, Charsets.UTF_8)
        } catch (e: Exception) {
            ""
        }
        Log.d(TAG, "Uhr: $text")
        Thread { handle(text) }.start()
    }

    /** Verbindung aufbauen: Berechtigung pruefen, Uhr suchen, Empfaenger anmelden. */
    fun connect() {
        if (BuildConfig.WATCH_FINGERPRINT.isEmpty()) {
            setState("Uhr-Zertifikat fehlt (watchapp/signing) - APK neu bauen")
            return
        }
        HiWear.getAuthClient(context).checkPermission(Permission.DEVICE_MANAGER)
            .addOnSuccessListener { granted ->
                if (granted == true) findDevice() else setState("Berechtigung fehlt - 'Uhr koppeln' antippen")
            }
            .addOnFailureListener { e -> setState("Wear Engine nicht verfuegbar: ${describe(e)}") }
    }

    /** Oeffnet den Huawei-Health-Dialog, der die Wear-Engine-Berechtigung erteilt. */
    fun requestPermission() {
        HiWear.getAuthClient(context).requestPermission(object : AuthCallback {
            override fun onOk(permissions: Array<Permission>) {
                if (permissions.any { it == Permission.DEVICE_MANAGER }) findDevice()
                else setState("Berechtigung abgelehnt")
            }

            override fun onCancel() {
                setState("Berechtigung abgebrochen")
            }
        }, Permission.DEVICE_MANAGER)
            .addOnFailureListener { e -> setState("Berechtigungsanfrage fehlgeschlagen: ${describe(e)}") }
    }

    private fun findDevice() {
        HiWear.getDeviceClient(context).bondedDevices
            .addOnSuccessListener { devices ->
                val connected = devices?.firstOrNull { it.isConnected }
                if (connected == null) {
                    setState("Keine verbundene Uhr in Huawei Health")
                    return@addOnSuccessListener
                }
                register(connected)
            }
            .addOnFailureListener { e -> setState("Uhr-Suche fehlgeschlagen: ${describe(e)}") }
    }

    private fun register(target: Device) {
        device?.let { old ->
            if (old.uuid == target.uuid) {
                setState("Verbunden mit ${target.name}")
                return
            }
            p2p.unregisterReceiver(receiver)
        }
        p2p.registerReceiver(target, receiver)
            .addOnSuccessListener {
                device = target
                setState("Verbunden mit ${target.name}")
            }
            .addOnFailureListener { e -> setState("Empfaenger fehlgeschlagen: ${describe(e)}") }
    }

    fun disconnect() {
        device?.let {
            try {
                p2p.unregisterReceiver(receiver)
            } catch (e: Exception) {
                Log.w(TAG, "unregister: ${e.message}")
            }
        }
        device = null
        setState("nicht verbunden")
    }

    // ------------------------------------------------------------ Anfragen
    private fun handle(text: String) {
        val request = try {
            JSONObject(text)
        } catch (e: Exception) {
            JSONObject()
        }
        val reply = when (val cmd = request.optString("cmd", "state")) {
            "state" -> {
                val payload = provider.watchPayload(request.optInt("force", 0) == 1)
                payload?.put("rt", "state")
                    ?: JSONObject().put("rt", "error").put("msg", "noch keine Fahrzeugdaten")
            }
            "info" -> provider.info().put("rt", "info")
            "command" -> JSONObject()
                .put("rt", "command")
                .put("ok", false)
                .put("msg", "Fernbefehle nur ueber die PC-Bridge")
            else -> JSONObject().put("rt", "error").put("msg", "unbekannt: $cmd")
        }
        send(reply.toString())
    }

    private fun send(text: String) {
        val target = device ?: run {
            Log.w(TAG, "Antwort ohne Uhr verworfen")
            return
        }
        val message = Message.Builder().setPayload(text.toByteArray(Charsets.UTF_8)).build()
        p2p.send(target, message, object : SendCallback {
            override fun onSendResult(resultCode: Int) {
                // 207 = zugestellt, 206 = fehlgeschlagen (Uhr-App zu?)
                if (resultCode != 207) Log.w(TAG, "Senden: Code $resultCode")
            }

            override fun onSendProgress(progress: Long) {}
        }).addOnFailureListener { e -> Log.w(TAG, "Senden fehlgeschlagen: ${describe(e)}") }
    }

    private fun setState(text: String) {
        state = text
        Log.i(TAG, text)
        onStatus(text)
    }

    /** Wear-Engine-Fehlercodes in Klartext (Auszug aus der SDK-Doku). */
    private fun describe(e: Exception): String {
        val code = (e as? WearEngineException)?.errorCode ?: -1
        val hint = when (code) {
            1 -> "interner Fehler - meist: App-ID in AGC fehlt oder nicht fuer Wear Engine freigeschaltet"
            2 -> "ungueltiger Parameter"
            3 -> "SDK/Health-Version zu alt"
            4 -> "Wear-Engine-Dienst nicht erreichbar"
            5 -> "Huawei Health nicht installiert"
            6 -> "Huawei Health zu alt"
            7 -> "Berechtigung verweigert - 'Uhr koppeln'"
            8 -> "in Huawei Health nicht mit Huawei-ID angemeldet"
            9 -> "Uhr nicht verbunden"
            12 -> "App nicht fuer Wear Engine freigeschaltet (AGC)"
            13 -> "Uhr-App nicht installiert"
            14 -> "Uhr-App laeuft nicht"
            15 -> "Fingerabdruck der Gegenstelle passt nicht"
            16 -> "Nachricht zu gross (max. 1 KB)"
            else -> e.message ?: e.toString()
        }
        return "Code $code: $hint"
    }

    companion object {
        private const val TAG = "WearLink"
    }
}
