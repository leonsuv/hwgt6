package de.saigak.opelbridge

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.net.Uri
import android.os.Bundle

/**
 * Schnittstelle fuer Gadgetbridge (Opel-Variante), das die Daten per
 * Bluetooth an die Uhr-App weiterreicht.
 *
 * Ein ContentProvider statt HTTP, weil Android den Prozess fuer einen
 * Provider-Aufruf selbst startet - auch wenn der Akku-Manager die App im
 * Hintergrund beendet hat. Kein Dauerdienst noetig.
 *
 * Aufruf: contentResolver.call("content://de.saigak.opelbridge.watch",
 *         "watch" | "info", null, Bundle{ force: Boolean })
 * Antwort: Bundle{ json: String }
 */
class WatchProvider : ContentProvider() {

    override fun onCreate(): Boolean = true

    override fun call(method: String, arg: String?, extras: Bundle?): Bundle? {
        val ctx = context ?: return null
        // Nur Gadgetbridge und die eigene App - die Daten verraten den Standort
        val caller = callingPackage
        if (caller != null && caller !in ALLOWED && caller != ctx.packageName) {
            throw SecurityException("Nicht erlaubt: $caller")
        }
        val json = when (method) {
            "watch" -> {
                val payload = VehicleData.watchPayload(ctx, extras?.getBoolean("force") == true)
                payload?.toString()
                    ?: "{\"err\":\"${VehicleData.store(ctx).lastError ?: "Keine Daten"}\"}"
            }
            "info" -> VehicleData.info(ctx).toString()
            else -> return null
        }
        return Bundle().apply { putString("json", json) }
    }

    override fun query(uri: Uri, projection: Array<out String>?, selection: String?,
                       selectionArgs: Array<out String>?, sortOrder: String?): Cursor? = null

    override fun getType(uri: Uri): String? = null
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?,
                        selectionArgs: Array<out String>?): Int = 0

    companion object {
        const val AUTHORITY = "de.saigak.opelbridge.watch"
        private val ALLOWED = setOf(
            "nodomain.freeyourgadget.gadgetbridge.opel",
            "nodomain.freeyourgadget.gadgetbridge",
            "nodomain.freeyourgadget.gadgetbridge.nightly"
        )
    }
}
