# Android-App: Bruecke auf dem Telefon

Damit braucht es keinen laufenden PC mehr. Die App meldet sich einmal bei
MyOpel an, erneuert die Tokens danach selbst und stellt die Fahrzeugdaten
lokal auf dem Telefon bereit - dort, wo die Uhr sie ohnehin abholt.

## Warum das funktioniert (und warum die Uhr kein WLAN braucht)

Die Watch GT6 hat fuer Apps **kein eigenes IP-Networking**. Ein
`@system.fetch` in der Uhr-App wird von Huawei Health durch das gekoppelte
Telefon geleitet und geht erst dort ins Netz. Die Anfrage entsteht also
effektiv auf dem Telefon:

```
  Uhr-App                Huawei Health                Android-App
  fetch(127.0.0.1:8787) --Bluetooth--> Telefon  --->  HTTP-Server :8787
                                                       |
                                                       v
                                            api.groupe-psa.com (HTTPS)
```

Deshalb genuegt `http://127.0.0.1:8787` in der `config.js` der Uhr: das
Telefon spricht mit sich selbst. Sollte Huawei Health die Loopback-Adresse
nicht durchreichen, steht in der App zusaetzlich die WLAN-Adresse des
Telefons (`http://192.168.x.y:8787`) - der Server lauscht auf allen
Schnittstellen und beide Wege funktionieren.

## Was die App kann - und was nicht

| | Android-App | Python-Bridge (Provider `opelapi`) |
| --- | --- | --- |
| Ladestand, Reichweite, Tueren, Klima, Position, km | ja | ja |
| Anmeldung mit Auto-Refresh | ja | ja |
| Laeuft ohne PC | **ja** | nein |
| Fernbefehle (Klima, Verriegeln, Wecken) | nein | ja |

Die Befehle fehlen bewusst: Stellantis verlangt dafuer eine MQTT-Verbindung
mit einem OTP-Geraeteschluessel (SMS-Code plus App-PIN, streng
rate-limitiert). Das steckt fertig in der Python-Bibliothek `opelapi`; es
nach Kotlin zu portieren waere viel Code fuer eine Funktion, die selten
gebraucht wird. Die Uhr zeigt bei einem Befehlsversuch eine klare Meldung
statt eines Fehlers.

## Bauen

Voraussetzung: Android Studio (Ladybug oder neuer) mit Android SDK 34.

1. Android Studio &rarr; *Open* &rarr; Ordner `androidapp` waehlen.
2. Gradle-Sync abwarten (laedt beim ersten Mal AGP und Kotlin-Plugin).
3. *Run 'app'* mit angestecktem Telefon, oder
   *Build &rarr; Build Bundle(s)/APK(s) &rarr; Build APK(s)* und die entstandene
   `app/build/outputs/apk/debug/app-debug.apk` aufs Telefon kopieren.

Die App hat bewusst **keine Fremdbibliotheken**: HTTP laeuft ueber
`HttpURLConnection`, JSON ueber `org.json` aus dem SDK. Damit gibt es beim
Bauen wenig, was schiefgehen kann, und die APK bleibt klein.

Sollte Android Studio neuere Plugin-Versionen erzwingen, die Vorschlaege
einfach uebernehmen - der Code benutzt nichts Versionsabhaengiges.

## Einrichten

1. **Land pruefen** (Standard `DE`) - es bestimmt `locale` und die
   Rueckleitungsadresse. Bekannt sind 39 Laender aus `assets/brands.json`.
2. **Bei Opel anmelden** antippen. Es oeffnet sich die echte Opel-Anmeldeseite
   im eingebetteten Browser.
   * **Normalfall:** Nach der Anmeldung leitet die Seite auf
     `mymopsdk://oauth2redirect/de?code=...`. Die App faengt das ab und loest
     den Code selbst ein - nichts abtippen, nichts aus den Entwicklertools
     kopieren.
   * **Wenn die Zustimmungsseite haengt** (kommt bei Opel oefter vor, die
     Seite hat einen JavaScript-Fehler): unten auf **Anmeldung abschliessen**
     tippen. Die App holt den Code dann ueber das Sitzungs-Cookie
     `iPlanetDirectoryPro`, das nach dem Login bereits im Browser liegt -
     derselbe Trick wie `--sso-token` in der Python-Bibliothek.
3. Danach startet die Bruecke von selbst. Die Benachrichtigung zeigt den
   aktuellen Ladestand.
4. **Fuer config.js kopieren** antippen und die zwei Zeilen in
   `watchapp/entry/src/main/js/default/common/config.js` einsetzen:

```js
BASE_URL: 'http://127.0.0.1:8787',
TOKEN: 'xxxxxxxxxxxxxxxxxxxxxxxx',
```

5. Uhr-App neu bauen und installieren ([INSTALL-WATCH.md](INSTALL-WATCH.md)).

## Test ohne Uhr

Im Browser des Telefons aufrufen:

```
http://127.0.0.1:8787/api/v1/watch?t=<Token>
```

Kommt JSON zurueck, ist alles richtig. Vom PC aus geht dieselbe Abfrage mit
der WLAN-Adresse des Telefons.

## Dauerbetrieb

Die Bruecke laeuft als Vordergrunddienst mit fester Benachrichtigung - anders
erlaubt Android keinen dauerhaft lauschenden Socket. Zwei Dinge sind trotzdem
noetig:

* **Akkuoptimierung ausschalten**: Einstellungen &rarr; Apps &rarr; Opel Bridge &rarr;
  Akku &rarr; *Nicht optimiert* / *Uneingeschraenkt*. Huawei-, Samsung- und
  Xiaomi-Systeme beenden Hintergrunddienste sonst nach einigen Stunden.
* **Abfrageintervall**: Standard sind 300 Sekunden. Kuerzer bringt nichts -
  ein parkendes Auto meldet ohnehin nur alle paar Stunden neue Werte, und
  haeufige Abfragen wecken das Fahrzeugmodem.

## Sicherheit

* Tokens liegen in den privaten App-Daten (`MODE_PRIVATE`), fuer andere Apps
  ohne Root nicht lesbar. Sie werden nie protokolliert und nie ueber die
  Schnittstelle ausgegeben.
* Der Uhr-Server verlangt bei jeder Anfrage das beim ersten Start gewuerfelte
  Token (24 Zeichen, zeitkonstanter Vergleich).
* Der Server lauscht auf allen Schnittstellen. Im heimischen WLAN ist das in
  Ordnung; in einem oeffentlichen WLAN die Bruecke besser stoppen, denn dort
  koennte jemand im selben Netz zumindest das Token raten wollen.
* **Abmelden** loescht Tokens, Fahrzeugdaten und den Zwischenspeicher.

## Aufbau des Codes

| Datei | Aufgabe |
| --- | --- |
| `Brands.kt` | Endpunkte und Laenderdaten aus `assets/brands.json` |
| `Store.kt` | Tokens, Einstellungen, Zwischenspeicher |
| `OpelApi.kt` | OAuth-Login, Token-Erneuerung, Fahrzeuge und Status |
| `Normalize.kt` | Rohantwort &rarr; kompaktes Uhr-JSON (gleiches Schema wie die Bridge) |
| `WatchServer.kt` | HTTP-Server fuer die Uhr, Token-Pruefung |
| `BridgeService.kt` | Vordergrunddienst: Abfrageschleife und Server |
| `LoginActivity.kt` | Anmeldung im WebView, beide Wege |
| `MainActivity.kt` | Statusanzeige, Start/Stop, Adresse fuer die Uhr |

Die Protokoll-Logik in `OpelApi.kt` ist eins zu eins aus der funktionierenden
Python-Bibliothek `opelapi` uebernommen - inklusive der beiden Eigenheiten,
die sonst Stunden kosten:

* Die Query-Parameter von `authorize` und `access_token` werden **nicht**
  prozentkodiert gesendet (`scope=openid%20profile%20email` bleibt so stehen,
  `redirect_uri` ungekodiert). Die ForgeRock-Endpunkte weisen kodierte Werte ab.
* Der Token-Tausch nutzt HTTP-Basic aus `client_id:client_secret`, die
  Parameter stehen in der URL, der Rumpf bleibt leer.

Dass beide Seiten dasselbe Datenformat liefern, prueft
`bridge/tests/test_android_consistency.py` automatisch - dafuer muss Android
nicht gebaut werden.
