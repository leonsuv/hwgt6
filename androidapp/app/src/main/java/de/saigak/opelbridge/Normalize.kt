package de.saigak.opelbridge

import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import java.util.regex.Pattern

/**
 * Wandelt die Rohantwort von /vehicles/{id}/status in dieselbe kompakte
 * Nutzlast um, die auch die Python-Bridge liefert. Die Uhr-App kennt nur
 * dieses Format und muss daher nicht wissen, woher die Daten kommen.
 *
 * Aktuelle Antwortform (MyOpel-App):
 *   energies[] -> type Electric/Fuel, level, autonomy
 *                 extension.electric.charging.{plugged,status,remainingTime,
 *                                              chargingRate,chargingMode}
 */
object Normalize {

    private val DURATION = Pattern.compile(
        "^P(?:(\\d+)D)?T?(?:(\\d+)H)?(?:(\\d+)M)?(?:(\\d+)S)?$"
    )

    private val DOOR_MAP = mapOf(
        "driver" to "fl", "frontleft" to "fl",
        "passenger" to "fr", "frontright" to "fr",
        "rearleft" to "rl", "rearright" to "rr",
        "trunk" to "trunk", "boot" to "trunk",
        "hood" to "hood", "bonnet" to "hood",
        "sunroof" to "roof", "rearwindow" to "rear"
    )

    // ------------------------------------------------------------- Helfer
    private fun obj(parent: JSONObject?, key: String): JSONObject? =
        parent?.optJSONObject(key)

    private fun number(parent: JSONObject?, key: String): Double? {
        if (parent == null || !parent.has(key) || parent.isNull(key)) return null
        val value = parent.opt(key)
        return when (value) {
            is Number -> value.toDouble()
            is String -> value.toDoubleOrNull()
            else -> null
        }
    }

    /** Ersten Eintrag aus energies[] mit passendem Typ suchen. */
    private fun energy(raw: JSONObject, type: String): JSONObject? {
        val list = raw.optJSONArray("energies") ?: raw.optJSONArray("energy") ?: return null
        var fallback: JSONObject? = null
        for (index in 0 until list.length()) {
            val item = list.optJSONObject(index) ?: continue
            if (!item.optString("type").equals(type, ignoreCase = true)) continue
            val level = number(item, "level") ?: 0.0
            if (level > 0.0) return item
            if (fallback == null) fallback = item
        }
        return fallback
    }

    private fun charging(entry: JSONObject?): JSONObject? {
        if (entry == null) return null
        val flat = entry.optJSONObject("charging")
        if (flat != null && flat.length() > 0) return flat
        return obj(obj(obj(entry, "extension"), "electric"), "charging")
    }

    /** ISO-8601-Dauer ("PT1H25M") in Minuten. */
    fun durationMinutes(value: String?): Int? {
        if (value.isNullOrBlank()) return null
        val matcher = DURATION.matcher(value.trim().uppercase(Locale.ROOT))
        if (!matcher.matches()) return null
        val days = matcher.group(1)?.toIntOrNull() ?: 0
        val hours = matcher.group(2)?.toIntOrNull() ?: 0
        val minutes = matcher.group(3)?.toIntOrNull() ?: 0
        val seconds = matcher.group(4)?.toIntOrNull() ?: 0
        return days * 1440 + hours * 60 + minutes + seconds / 60
    }

    /** ISO-Zeitstempel in Sekunden seit 1970. */
    fun epochSeconds(value: String?): Long? {
        if (value.isNullOrBlank()) return null
        val text = value.trim().replace("Z", "+0000").replace(Regex("([+-]\\d{2}):(\\d{2})$"), "$1$2")
        val patterns = listOf(
            "yyyy-MM-dd'T'HH:mm:ss.SSSZ",
            "yyyy-MM-dd'T'HH:mm:ssZ",
            "yyyy-MM-dd'T'HH:mm:ss"
        )
        for (pattern in patterns) {
            try {
                val format = SimpleDateFormat(pattern, Locale.US)
                if (!pattern.endsWith("Z")) format.timeZone = TimeZone.getTimeZone("UTC")
                return format.parse(text)?.time?.div(1000)
            } catch (e: Exception) {
                // naechstes Muster versuchen
            }
        }
        return null
    }

    private fun door(name: String): String {
        val key = name.lowercase(Locale.ROOT).replace("_", "").replace(" ", "")
        return DOOR_MAP[key] ?: key.take(8)
    }

    // -------------------------------------------------------- Umwandlung
    /**
     * @param raw    Antwort von /status (darf leer sein)
     * @param name   Anzeigename des Fahrzeugs
     * @return kompakte Nutzlast fuer die Uhr
     */
    fun toWatchPayload(raw: JSONObject, name: String): JSONObject {
        val now = System.currentTimeMillis() / 1000
        val out = JSONObject()
        out.put("v", 1)
        out.put("ts", now)
        out.put("nm", name)
        out.put("src", "android")

        val electric = energy(raw, "Electric")
        val fuel = energy(raw, "Fuel")
        val electricLevel = number(electric, "level")
        val fuelLevel = number(fuel, "level")

        val type = when {
            electricLevel != null && (fuelLevel ?: 0.0) > 0.0 -> "hybrid"
            electricLevel != null -> "electric"
            fuelLevel != null -> "fuel"
            else -> "unknown"
        }
        out.put("et", type)

        if (electricLevel != null) {
            out.put("lvl", Math.round(electricLevel))
            number(electric, "autonomy")?.let { out.put("rng", Math.round(it)) }
        } else if (fuelLevel != null) {
            out.put("lvl", Math.round(fuelLevel))
            number(fuel, "autonomy")?.let { out.put("rng", Math.round(it)) }
        } else {
            out.put("lvl", JSONObject.NULL)
            out.put("rng", JSONObject.NULL)
        }

        val charge = charging(electric)
        val status = charge?.optString("status")?.lowercase(Locale.ROOT) ?: ""
        out.put("chg", if (status == "inprogress") 1 else 0)
        out.put("plg", if (charge?.optBoolean("plugged", false) == true) 1 else 0)
        out.put("kw", JSONObject.NULL)               // API liefert keine Ladeleistung
        number(charge, "chargingRate")?.let { out.put("kmh", Math.round(it)) }
        durationMinutes(charge?.optString("remainingTime"))?.let { out.put("eta", it) }
        number(charge, "targetLevel")?.let { out.put("tgt", Math.round(it)) }

        if (type == "hybrid") {
            out.put("lvl2", Math.round(fuelLevel ?: 0.0))
            number(fuel, "autonomy")?.let { out.put("rng2", Math.round(it)) }
        }

        number(obj(raw, "odometer") ?: obj(raw, "timedOdometer"), "mileage")
            ?.let { out.put("odo", Math.round(it)) }

        // Tueren
        val doors = obj(raw, "doorsState")
        var locked = -1
        val lockedStates = doors?.optJSONArray("lockedStates")
        if (lockedStates != null) {
            var sawLocked = false
            var sawUnlocked = false
            for (index in 0 until lockedStates.length()) {
                when (lockedStates.optString(index).lowercase(Locale.ROOT)) {
                    "locked" -> sawLocked = true
                    "unlocked" -> sawUnlocked = true
                }
            }
            locked = if (sawLocked && !sawUnlocked) 1 else if (sawUnlocked) 0 else -1
        } else if (doors?.has("lockedState") == true) {
            locked = if (doors.optString("lockedState") == "Locked") 1 else 0
        }
        out.put("lck", locked)

        val opened = doors?.optJSONArray("opened") ?: JSONArray()
        val openList = JSONArray()
        for (index in 0 until minOf(opened.length(), 4)) {
            openList.put(door(opened.optString(index)))
        }
        out.put("opn", opened.length())
        out.put("opl", openList)

        // Klima und Temperaturen
        val precond = obj(raw, "preconditionning") ?: obj(raw, "preconditioning")
        val airConditioning = obj(precond, "airConditioning")
        val acStatus = airConditioning?.optString("status")?.lowercase(Locale.ROOT) ?: ""
        out.put("clm", if (acStatus == "enabled" || acStatus == "inprogress") 1 else 0)

        val air = obj(obj(raw, "environment"), "air")
        number(air, "cabinTemp")?.let { out.put("tin", it) }
        number(air, "temp")?.let { out.put("tout", it) }

        // Position
        val position = obj(raw, "lastPosition")
        val coordinates = obj(position, "geometry")?.optJSONArray("coordinates")
        if (coordinates != null && coordinates.length() >= 2) {
            out.put("lon", coordinates.optDouble(0))
            out.put("lat", coordinates.optDouble(1))
        }

        // Warnungen
        val alerts = JSONArray()
        if ((obj(raw, "privacy")?.optString("state") ?: "None") != "None") {
            alerts.put("Privatmodus aktiv - keine Position")
        }
        if (obj(raw, "kinetic")?.optBoolean("moving", false) == true) {
            alerts.put("Fahrzeug faehrt")
        }
        out.put("alt", alerts)

        // Alter der Fahrzeugmeldung
        val updated = epochSeconds(raw.optString("createdAt"))
            ?: epochSeconds(obj(raw, "odometer")?.optString("createdAt"))
            ?: epochSeconds(electric?.optString("updatedAt"))
        out.put("age", if (updated != null) maxOf(0L, now - updated) else 0L)

        return out
    }

    /**
     * Alter der Messung neu berechnen, wenn eine zwischengespeicherte Nutzlast
     * erneut ausgeliefert wird - sonst zeigt die Uhr "gerade eben" fuer alte Daten.
     */
    fun refreshAge(payload: JSONObject, cachedAtSeconds: Long): JSONObject {
        val now = System.currentTimeMillis() / 1000
        val extra = maxOf(0L, now - cachedAtSeconds)
        val copy = JSONObject(payload.toString())
        copy.put("age", payload.optLong("age", 0L) + extra)
        copy.put("ts", now)
        copy.put("cache_s", extra)
        return copy
    }
}
