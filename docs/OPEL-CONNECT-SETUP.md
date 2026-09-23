# Echte Fahrzeugdaten anbinden

Opel Connect hat **keine offizielle oeffentliche API**. Alles hier nutzt
dieselbe Schnittstelle wie die MyOpel-App - mit dem eigenen Konto, fuer das
eigene Fahrzeug. Das ist der uebliche Weg der Community (Home Assistant,
psa_car_controller), bleibt aber inoffiziell: Stellantis kann jederzeit etwas
aendern.

Deshalb steckt der Zugriff in austauschbaren Providern unter
`bridge/opelbridge/providers/`. Aendert sich die API, wird nur dort
nachgezogen - die Uhr kennt ohnehin nur das normalisierte Format.

## Welcher Weg?

| Weg | Braucht einen laufenden PC | Fernbefehle | Aufwand |
| --- | --- | --- | --- |
| **A. Android-App** | nein | nein | gering |
| **B. Bridge + `opelapi`** | ja | ja | gering |
| C. Bridge + psa_car_controller | ja | ja | mittel |
| D. Bridge + `stellantis` direkt | ja | nein | hoch |

**Auf die Uhr kommen die Daten nur über Weg A** (Opel Bridge + Gadgetbridge,
siehe [GADGETBRIDGE.md](GADGETBRIDGE.md)) – die Uhr hat keinen Netzzugang und
erreicht keinen PC. Die Wege B–D speisen die PC-Bridge: Browser-Vorschau,
Tests und Fernbefehle. Beide liefern dasselbe Datenformat.

---

## Weg A: Android-App auf dem Telefon

Kein Server noetig, einmal anmelden, Tokens erneuern sich selbst. Der
komplette Ablauf steht in [ANDROID-APP.md](ANDROID-APP.md).

Kurz: `androidapp` bauen und installieren, in der App bei Opel anmelden,
Akku-Ausnahme zulassen. Gadgetbridge (opel) holt die Daten dann selbst ab.

---

## Weg B: Bridge mit der Bibliothek `opelapi` (empfohlen, wenn ein Server laeuft)

Nutzt die eigene, bereits funktionierende Python-Bibliothek. Sie erledigt
Login, Token-Erneuerung und - anders als die Android-App - auch die
Fernbefehle ueber MQTT.

```bat
:: 1. Bibliothek installieren
py -m pip install -e C:\Pfad\zu\opelapi-main

:: 2. Einmalig anmelden (Browser oeffnet sich)
py -m opelapi.cli login --country DE

:: 3. Optional: Fernbefehle freischalten (SMS-Code + PIN aus der MyOpel-App)
py -m opelapi.cli enable-remote
```

Die Sitzung landet in `~/.opelapi/session.json` und wird von der Bridge
mitbenutzt. Dann in `bridge/config.json`:

```json
{
  "provider": "opelapi",
  "allow_commands": true,
  "opelapi": {
    "session_path": "",
    "vin": "",
    "command_timeout_s": 45
  }
}
```

`session_path` leer lassen heisst: Standardpfad `~/.opelapi/session.json`.
`vin` nur setzen, wenn mehrere Fahrzeuge im Konto sind.

Testen:

```bat
cd bridge
py -m opelbridge --once
```

Unterstuetzte Befehle: `wakeup`, `preconditioning`, `lock`, `unlock`, `horn`,
`lights`, `charge_now`, `stop_charge`.

### Wenn der Login haengt

Die Zustimmungsseite von Opel (`id-dcr.opel.com/index/authorize-consentments`)
hat oft einen JavaScript-Fehler, sodass die Rueckleitung nie kommt. Dann in den
Entwicklertools des Browsers das Cookie `iPlanetDirectoryPro` von
`https://idpcvs.opel.com` kopieren und uebergeben:

```bat
py -m opelapi.cli login --country DE --sso-token "st2....."
```

Genau diesen Weg benutzt auch die Android-App, nur automatisch.

---

## Weg C: psa_car_controller

[psa_car_controller](https://github.com/flobz/psa_car_controller) laufen lassen
und dessen lokale REST-Schnittstelle anzapfen. Sinnvoll, wenn das Programm
ohnehin schon fuer Home Assistant laeuft.

```json
{
  "provider": "psacc",
  "psacc": {
    "base_url": "http://127.0.0.1:5000",
    "from_cache": true,
    "name": "Corsa-e"
  }
}
```

`from_cache: true` liefert den zuletzt empfangenen Stand, ohne das Auto zu
wecken. Befehle: `wakeup`, `preconditioning`, `charge_now`.

---

## Weg D: direkt gegen die Stellantis-API

Nur sinnvoll, wenn `client_id`, `client_secret` und ein gueltiges
`refresh_token` bereits vorliegen (etwa aus einer bestehenden
opelapi-Sitzung). Kann keine Befehle.

```json
{
  "provider": "stellantis",
  "vin": "W0V...",
  "stellantis": {
    "client_id": "...",
    "client_secret": "...",
    "refresh_token": "...",
    "realm": "clientsB2COpel",
    "token_url": "https://idpcvs.opel.com/am/oauth2/access_token",
    "api_base": "https://api.groupe-psa.com/connectedcar/v4/user"
  }
}
```

Rotiert Stellantis das `refresh_token`, schreibt die Bridge das neue
automatisch in `config.json` zurueck.

---

## Wie oft darf abgefragt werden?

`poll_interval_s` steht auf 300 Sekunden. Gruende, das nicht zu verkleinern:

* Ein parkendes Fahrzeug meldet neue Werte nur alle paar Stunden oder bei
  Ereignissen (Laden, Tuer, Zuendung). Haeufiger fragen liefert dieselben Zahlen.
* Erzwungene Abfragen wecken das Fahrzeugmodem und belasten die
  Starterbatterie - bei langen Standzeiten ein reales Problem.
* Stellantis drosselt auffaellig haeufige Zugriffe.
* `wake_up()` ist zusaetzlich begrenzt (etwa 6 Aufrufe je 20 Minuten),
  OTP-Codes auf etwa 6 pro Tag.

Die Uhr fragt nur die Bruecke und bekommt deren Zwischenspeicher. Nur die
Taste *Jetzt aktualisieren* loest eine echte Abfrage aus (`force=1`).

## Fehlersuche

| Meldung | Bedeutung |
| --- | --- |
| `Die Bibliothek 'opelapi' ist nicht installiert` | `py -m pip install -e <Pfad>` fehlt |
| `Keine Sitzung unter ~/.opelapi/session.json` | Einmalige Anmeldung fehlt |
| `Anmeldung abgelaufen (AuthenticationError)` | Refresh-Token verfallen - neu anmelden |
| `Fernbefehle nicht freigeschaltet` | `py -m opelapi.cli enable-remote` fehlt |
| `Fahrzeug antwortet nicht - evtl. Tiefschlaf` | Erst `wakeup`, dann den Befehl wiederholen |
| `Mehrere Fahrzeuge im Konto` | `vin` in `config.json` setzen |
| Status bleibt leer (`{}`) | Das Auto hat seit der letzten Fahrt nichts gemeldet |

Ausfuehrliche Protokolle: `py -m opelbridge -v`

## Rechtliches, kurz

Nutzung mit dem eigenen Konto fuer das eigene Fahrzeug. Die
Nutzungsbedingungen von Opel Connect sehen automatisierte Zugriffe nicht
ausdruecklich vor; ein sparsames Intervall ist also nicht nur technisch
vernuenftig. Zugangsdaten gehoeren ausschliesslich in die lokale
`config.json` bzw. in die App - nie in ein Repository.
