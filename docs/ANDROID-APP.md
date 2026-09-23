# Opel Bridge: die Android-App auf dem Telefon

Die Opel Bridge meldet sich einmal bei MyOpel an, erneuert die Tokens danach
selbst und liefert die Fahrzeugdaten an **Gadgetbridge (opel)**, das sie per
Bluetooth an die Uhr weitergibt. Ein PC wird nicht gebraucht.

```
Uhr-App  <--Bluetooth-->  Gadgetbridge (opel)  --ContentProvider-->  Opel Bridge  --HTTPS-->  Opel Connect
```

## Was die App kann – und was nicht

| | Opel Bridge | PC-Bridge (Provider `opelapi`) |
| --- | --- | --- |
| Ladestand, Reichweite, Stecker, Türen, Klima, Position, km | ja | ja |
| Anmeldung mit automatischer Token-Erneuerung | ja | ja |
| Läuft ohne PC | **ja** | nein |
| Fernbefehle (Klima, Verriegeln, Wecken) | nein | ja |

Fernbefehle fehlen bewusst: Stellantis verlangt dafür eine MQTT-Verbindung
mit einem registrierten OTP-Gerät (SMS-Code plus PIN, streng
rate-limitiert). Jede zusätzliche Registrierung ist ein Risiko für das
Opel-Konto.

## Bauen

Voraussetzung: Android SDK 34 und JDK 17–21. Der Gradle-Wrapper liegt bei.

```bash
cd androidapp
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Oder in Android Studio: *Open → `androidapp`* → *Run 'app'*.

Die App hat **keine Fremdbibliotheken**: HTTP über `HttpURLConnection`, JSON
über `org.json` aus dem SDK.

## Einrichten

1. **Land prüfen** (Standard `DE`). Es bestimmt `locale` und die
   Rückleitungsadresse; 39 Länder stehen in `assets/brands.json`.
2. **Bei Opel anmelden** antippen. Es öffnet sich die echte Opel-Anmeldeseite.
   * **Normalfall:** Nach der Anmeldung leitet Opel auf
     `mymopsdk://oauth2redirect/de?code=…`. Die App fängt das ab und löst den
     Code selbst ein – nichts abtippen.
   * **Wenn die Zustimmungsseite hängt** (bei Opel häufig, die Seite hat einen
     JavaScript-Fehler): unten **Anmeldung abschließen** antippen. Die App holt
     den Code dann über das Sitzungs-Cookie `iPlanetDirectoryPro`.
3. **Akku-Ausnahme zulassen.** Die App fragt beim Öffnen danach. Ohne sie
   sperrt Android der App im Hintergrund das Netz, und die Uhr bekäme nur
   alte Daten (*„Unable to resolve host“*). Per adb:

   ```bash
   adb shell dumpsys deviceidle whitelist +de.saigak.opelbridge
   ```

4. Fertig. Die App muss danach **nicht geöffnet bleiben**: Gadgetbridge ruft
   sie über einen ContentProvider auf, und Android startet sie dafür bei
   Bedarf selbst – auch wenn der Akku-Manager sie vorher beendet hat.

Der Schalter **Brücke starten** ist optional. Er startet zusätzlich einen
Vordergrunddienst, der alle 5 Minuten abfragt und die HTTP-Schnittstelle zum
Testen bereitstellt.

## Wie oft wird abgefragt?

* Tippst du auf der Uhr **Aktualisieren**, fragt die Opel Bridge sofort frisch
  bei Opel an.
* Sonst beantwortet sie Anfragen aus dem Zwischenspeicher, solange er jünger
  als das Abfrageintervall ist (Standard 300 s).
* Häufiger bringt nichts: Ein parkendes Auto meldet ohnehin nur selten neue
  Werte, und Stellantis verlangt Abstand zwischen den Abfragen. Die Zeit
  **„Auto meldete vor …“** auf der Uhr ist die letzte Meldung des Autos selbst.

## Test ohne Uhr

Mit laufender Brücke im Browser des Telefons:

```
http://127.0.0.1:8787/api/v1/watch?t=<Uhr-Token>
```

Das Token steht in der App. Kommt JSON zurück, stimmt alles. Vom PC aus geht
dieselbe Abfrage mit der WLAN-Adresse des Telefons oder per
`adb forward tcp:8787 tcp:8787`.

## Sicherheit

* Tokens liegen in den privaten App-Daten, sind ohne Root für andere Apps
  nicht lesbar und werden nie protokolliert oder ausgegeben.
* Der ContentProvider antwortet nur Gadgetbridge – andere Apps bekommen eine
  `SecurityException`.
* Die HTTP-Schnittstelle verlangt das Uhr-Token (24 Zeichen, zeitkonstanter
  Vergleich). In öffentlichen WLANs die Brücke besser stoppen.
* **Abmelden** löscht Tokens, Fahrzeugdaten und Zwischenspeicher.

## Aufbau des Codes

| Datei | Aufgabe |
| --- | --- |
| `OpelApi.kt` | OAuth-Login, Token-Erneuerung, Fahrzeuge und Status |
| `Normalize.kt` | Opel-Antwort → kompaktes Uhr-JSON (gleiches Schema wie die PC-Bridge) |
| `VehicleData.kt` | Abruf und Zwischenspeicher, gemeinsam für Provider und Dienst |
| `WatchProvider.kt` | ContentProvider für Gadgetbridge (`watch`, `info`) |
| `BridgeService.kt` | optionaler Vordergrunddienst: Abfrageschleife und HTTP-Server |
| `WatchServer.kt` | HTTP-Schnittstelle zum Testen, Token-Prüfung |
| `WearLink.kt` | offizieller Weg über Huawei Health (braucht AGC-Freigabe, sonst „Code 12“) |
| `LoginActivity.kt` | Anmeldung im WebView, beide Wege |
| `MainActivity.kt` | Statusanzeige, Start/Stop, Akku-Ausnahme |
| `Store.kt`, `Brands.kt` | Tokens und Einstellungen, Endpunkte und Länderdaten |

Die Protokoll-Logik in `OpelApi.kt` stammt aus der funktionierenden
Python-Bibliothek `opelapi` – inklusive der beiden Eigenheiten, die sonst
Stunden kosten:

* Die Query-Parameter von `authorize` und `access_token` werden **nicht**
  prozentkodiert (`scope=openid%20profile%20email` bleibt wörtlich stehen).
* Der Token-Tausch nutzt HTTP-Basic aus `client_id:client_secret`, die
  Parameter stehen in der URL, der Rumpf bleibt leer.

Und eine Eigenheit der Statusantwort: `charging.plugged` bleibt oft `true`,
obwohl `status` schon `Disconnected` meldet. Dann gilt der Status – sonst
zeigt die Uhr „Angesteckt“, obwohl kein Kabel steckt.

Dass Opel Bridge und PC-Bridge dasselbe Datenformat liefern, prüft
`bridge/tests/test_android_consistency.py` automatisch.
