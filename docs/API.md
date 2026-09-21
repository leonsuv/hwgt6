# Schnittstelle der Bridge

Basisadresse: `http://<host>:8787`

Authentifizierung bei allen `/api/v1/*`-Aufrufen ueber das Token aus
`bridge/config.json` &ndash; wahlweise

* Header `X-Token: <token>`
* Header `Authorization: Bearer <token>`
* Query `?t=<token>`

Fehlendes oder falsches Token: **401**. Der Vergleich laeuft zeitkonstant
(`hmac.compare_digest`).

## Endpunkte

| Methode | Pfad | Zweck |
| --- | --- | --- |
| GET | `/health` | Lebenszeichen, **ohne** Token |
| GET | `/api/v1/watch` | Kompaktes JSON fuer die Uhr |
| GET | `/api/v1/state` | Vollstaendiges, sprechendes JSON |
| GET | `/api/v1/refresh` | Erzwungene Abfrage, liefert Ergebnis |
| GET | `/api/v1/info` | Provider, Cache-Zustand, Konfiguration ohne Geheimnisse |
| POST | `/api/v1/command/<name>` | Fernbefehl (nur bei `allow_commands: true`) |
| GET | `/` | Statusseite im Browser |
| GET | `/preview` | Uhr-Vorschau (`tools/preview.html`) |

`?force=1` an `/api/v1/watch` umgeht den Cache und fragt das Fahrzeug frisch ab.

## `/api/v1/watch`

Auf Kuerze getrimmt, weil die Uhr das auf schwacher Hardware parst
(typisch < 700 Byte).

```json
{
  "v": 1, "ts": 1789984112, "age": 33,
  "nm": "Corsa-e", "et": "electric",
  "lvl": 46, "rng": 154,
  "chg": 1, "plg": 1, "kw": 7.9, "kmh": 38, "eta": 17, "tgt": 80,
  "lvl2": null, "rng2": null,
  "odo": 24310,
  "lck": 1, "opn": 0, "opl": [],
  "clm": 0, "tin": 19.6, "tout": 11.9,
  "lat": 51.2277, "lon": 6.7775,
  "alt": [], "src": "mock", "cache_s": 2
}
```

| Feld | Bedeutung |
| --- | --- |
| `v` | Schemaversion (derzeit 1) |
| `ts` | Serverzeit (Unix-Sekunden) |
| `age` | Alter der Fahrzeugmeldung in Sekunden |
| `nm` / `et` | Name, Energieart (`electric`, `fuel`, `hybrid`) |
| `lvl` / `rng` | Ladestand bzw. Tankfuellung in %, Reichweite in km |
| `chg` / `plg` | laedt (0/1), Stecker verbunden (0/1) |
| `kw` | Ladeleistung in kW - nur wenn die Quelle sie kennt, sonst `null` |
| `kmh` | Reichweitenzuwachs in km/h (das liefert die PSA-API statt kW) |
| `eta` / `tgt` | Restzeit in Minuten, Ladeziel in % |
| `lvl2` / `rng2` | Zweitenergie bei Hybrid (Tank) |
| `odo` | Kilometerstand |
| `lck` | verriegelt: 1 ja, 0 nein, -1 unbekannt |
| `opn` / `opl` | Anzahl offener Tueren, Kurzcodes (`fl`,`fr`,`rl`,`rr`,`trunk`,`hood`) |
| `clm` | Klimatisierung aktiv (0/1) |
| `tin` / `tout` | Innen-/Aussentemperatur in Grad Celsius |
| `lat` / `lon` | letzte bekannte Position |
| `alt` | Warnungen als Text (max. 3) |
| `src` | Datenquelle: `opelapi`, `android`, `psacc`, `stellantis`, `mock` |
| `cache_s` | Alter des Bridge-Caches in Sekunden |
| `err` | nur bei Problemen: Kurzbeschreibung, Daten sind dann aus dem Cache |

Fehlende Werte sind `null`, nie erfunden. Die Uhr zeigt dafuer `--`.

## `/api/v1/state`

Gleiche Daten, ausgeschrieben &ndash; fuer Skripte, Home Assistant oder Fehlersuche:

```json
{
  "v": 1, "ts": 1789984109, "updated": 1789984079, "age_s": 30,
  "source": "mock",
  "vehicle": { "vin": "W0VZZZMOCK0000001", "name": "Corsa-e", "brand": "Opel" },
  "energy": {
    "type": "electric", "level": 42, "range_km": 141,
    "charging": true, "plugged": true, "charge_kw": 7.4,
    "charge_remaining_min": 18, "charge_mode": "immediate", "target_level": 80,
    "secondary_level": null, "secondary_range_km": null
  },
  "doors": { "locked": true, "open": [] },
  "climate": { "active": false, "cabin_c": 18.0, "outside_c": 11.5 },
  "position": { "lat": 51.2277, "lon": 6.7775, "heading": 0, "updated": 1789984049 },
  "odometer_km": 24310,
  "alerts": []
}
```

## Fernbefehle

Nur aktiv bei `"allow_commands": true`. Nicht unterstuetzte Befehle: **501**.

```
POST /api/v1/command/preconditioning?activate=1&minutes=10
POST /api/v1/command/wakeup
POST /api/v1/command/charge_now?hour=-1&minute=0
```

Antwort: `{"ok": true, "message": "Vorklimatisierung gestartet"}`.
Nach einem Befehl fragt die Bridge das Fahrzeug automatisch frisch ab.

| Quelle | Befehle |
| --- | --- |
| `opelapi` | wakeup, preconditioning, lock, unlock, horn, lights, charge_now, stop_charge |
| `psacc` | wakeup, preconditioning, charge_now |
| `mock` | wakeup, preconditioning, charge_now, lock, unlock |
| `stellantis` | keine (verlangt MQTT mit OTP-Geraeteschluessel) |
| Android-App | keine - meldet 501 mit Hinweis auf die Bridge |

## Statuscodes

| Code | Wann |
| --- | --- |
| 200 | Alles in Ordnung |
| 401 | Token fehlt oder falsch |
| 404 | Unbekannter Pfad |
| 501 | Befehl vom Provider nicht unterstuetzt oder abgeschaltet |
| 503 | Noch keine Daten vorhanden (erster Start ohne erfolgreiche Abfrage) |

Ist eine Abfrage fehlgeschlagen, liefert die Bridge trotzdem **200** mit den
letzten bekannten Daten plus `err`. So zeigt die Uhr weiter sinnvolle Werte und
markiert sie als veraltet, statt leer zu bleiben.

## Eigenen Provider ergaenzen

```python
# bridge/opelbridge/providers/meiner.py
from .base import Provider
from ..model import VehicleState, Energy

class MeinProvider(Provider):
    name = "meiner"

    def fetch(self) -> VehicleState:
        return VehicleState(
            vin="...", name="Mein Auto", source=self.name,
            energy=Energy(type="electric", level=55, range_km=180),
        )
```

In `providers/__init__.py` in `build_provider()` eintragen, in `config.json`
`"provider": "meiner"` setzen. Die Uhr merkt von der Aenderung nichts.
