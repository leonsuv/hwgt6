# Kontext für KI-Assistenten

Kurzbriefing für ein Modell, das dieses Repo zum ersten Mal sieht. Lies das
zuerst, dann [README.md](README.md) für die Nutzersicht.

## Was das ist

Fahrzeugdaten aus **Opel Connect** (Stellantis, ex-PSA) auf einer **Huawei
Watch GT6** anzeigen. Drei eigenständige Teile, ein gemeinsames Datenformat.

| Verzeichnis | Sprache | Läuft auf | Zustand |
| --- | --- | --- | --- |
| `watchapp/` | JS (HarmonyOS Lite Wearable) | Watch GT6 | UI visuell abgenommen, statisch geprüft, **nie auf echter Uhr gelaufen** |
| `androidapp/` | Kotlin | Android-Telefon | **nie kompiliert** (kein JDK/SDK auf dem Entwicklungsrechner) |
| `bridge/` | Python 3.8+, nur stdlib | PC / NAS / Pi | 36 Tests grün, real gegen Mock gelaufen |

## Die eine Sache, die man verstanden haben muss

**Die Watch GT6 hat für Apps kein eigenes IP-Networking.** Ein
`@system.fetch` in der Uhr-App wird von Huawei Health per Bluetooth zum
gekoppelten Telefon getunnelt und geht *dort* ins Netz.

Folgen daraus:

* Die Uhr kann `http://127.0.0.1:8787` aufrufen — das ist dann **das
  Telefon**, nicht die Uhr. Genau deshalb funktioniert die Android-App.
* Bei der PC-Bridge muss **das Telefon** den Server erreichen, nicht der PC.
  Häufigster Supportfall: „geht nicht" = Telefon im Mobilfunk statt WLAN.
* Es gibt keine dauerhafte Hintergrund-Aktualisierung auf der Uhr. Die App
  aktualisiert nur, solange sie offen ist.

## Datenvertrag (nicht einseitig ändern!)

Alle Quellen liefern dieselbe kompakte Nutzlast an `GET /api/v1/watch`,
26 Felder, < 700 Byte, kurze Schlüssel (`lvl`, `rng`, `chg`, `kmh`, `lck` …).

Drei Stellen implementieren dasselbe Schema:

1. `bridge/opelbridge/model.py` → `VehicleState.to_watch()` (**Referenz**)
2. `androidapp/.../Normalize.kt` → `toWatchPayload()`
3. `watchapp/.../common/util.js` → `buildView()` liest es

`bridge/tests/test_android_consistency.py` vergleicht die Schlüsselmengen per
Textanalyse und schlägt fehl, sobald eine Seite abweicht. **Nach jeder
Schema-Änderung alle drei Stellen anfassen und die Tests laufen lassen.**
Feldbedeutungen: [docs/API.md](docs/API.md).

## Harte Regeln der Watch-App

Die Lite-Wearable-Laufzeit (JerryScript) ist kein moderner Browser:

* **Nur ES5**: kein `let`/`const`, keine Arrow-Funktionen, keine Template-
  Strings, keine Klassen, keine Promises. `import`/`export` sind erlaubt
  (werden beim Bauen aufgelöst).
* **Nur ASCII im JS**: Sonderzeichen als `\uXXXX` escapen (`°` für °).
  Die alte Toolchain ist bei UTF-8-Quelltext unzuverlässig.
* **Kein `position: absolute` fürs Layout**: Überlagerungen über `<stack>`,
  Listen über `<list>`/`<list-item>`.
* **CSS-Selektoren nur als einzelne Klassen** — keine Verschachtelung, kein
  `@media`. Dynamische Klassen komplett in JS berechnen
  (`class="{{ageClass}}"`), nicht `class="age {{x}}"` mischen.
* Bildschirm ist **466 × 466 px rund**, Hintergrund schwarz (AMOLED).

`py tools/check_watchapp.py` (macOS: `python3 tools/check_watchapp.py`)
prüft all das automatisch — inklusive ES5, ASCII, HML-Wohlgeformtheit, JSON
und ob jede in `config.json` gelistete Seite ihre `.hml/.css/.js` hat.

## Erkenntnisse über die Opel-/Stellantis-API

Teuer erkauft, nicht wieder verlieren:

* Die Statusantwort nutzt **`energies`** (Plural) mit verschachteltem
  `extension.electric.charging.{plugged,status,remainingTime,chargingRate}`.
  Ältere Beschreibungen zeigen ein flaches `energy[].charging` — der
  Normalisierer akzeptiert beides.
* **`chargingRate` ist km/h Reichweitenzuwachs, nicht kW.** Die API liefert
  keine Ladeleistung. Feld `kmh` transportiert das; `kw` bleibt `null`, außer
  eine Quelle kennt Spannung × Strom. Keine kW-Schätzung einbauen — die
  Restzeit bezieht sich je nach Auto aufs Ladeziel statt auf 100 %.
* OAuth-Eigenheiten (sonst 400er): Query-Parameter von `authorize` und
  `access_token` werden **nicht prozentkodiert** gesendet
  (`scope=openid%20profile%20email` bleibt wörtlich stehen), Token-Tausch per
  HTTP-Basic aus `client_id:client_secret`, Parameter in der URL, Rumpf leer.
* Opels Zustimmungsseite (`id-dcr.opel.com/.../authorize-consentments`) hat
  oft einen JS-Fehler und erreicht die Rückleitung nie. Umweg: Cookie
  `iPlanetDirectoryPro` von `idpcvs.opel.com` nehmen und `authorize` direkt
  anfragen, zweiter Versuch mit `decision=allow&save_consent=on`.
* `status()` antwortet mit `{}`, wenn das Auto seit der letzten Fahrt nichts
  gemeldet hat. Das ist **kein Fehler** — als leer behandeln, nie raten.
* Ratenlimits: Abfragen ≥ 5 min (Fahrzeugmodem weckt sonst die
  Starterbatterie), `wake_up` ≈ 6/20 min, OTP-Codes ≈ 6/Tag.

## Externe Abhängigkeit: `opelapi`

Der beste Provider (`bridge/opelbridge/providers/opelapi_provider.py`) baut
auf einer **separaten, funktionierenden Python-Bibliothek des Nutzers** auf
(Repo `opelapi`, nicht Teil dieses Projekts). Sie erledigt Login,
Token-Erneuerung und Fernbefehle über MQTT + OTP.

```bash
pip install -e /pfad/zu/opelapi-main
python -m opelapi.cli login --country DE     # einmalig
python -m opelapi.cli enable-remote          # optional, für Befehle
```

Ohne sie werden 6 Tests übersprungen (30 statt 36) und der Provider meldet
eine klare Fehlermeldung. Ihr Datenmodell (`opelapi.models.VehicleStatus`)
ist die Referenz für die Abbildung — `bridge/tests/test_opelapi_provider.py`
testet gegen das echte Modell, nicht gegen einen Nachbau.

## Kommandos

macOS/Linux (der Nutzer arbeitet am MacBook):

```bash
cd bridge && ./start-bridge.sh          # Bridge, Standard: simuliertes Auto
python3 -m pytest tests -q              # 36 bzw. 30 Tests
python3 -m opelbridge --once            # einmal abfragen und ausgeben
python3 -m opelbridge --print-url       # fertige URL für die Uhr
cd .. && python3 tools/check_watchapp.py
```

Windows: `start-bridge.cmd`, sonst `py` statt `python3`.

Browser-Vorschau der Uhr (kein Gerät nötig, gleiche Formatierlogik):
Bridge starten, dann `http://127.0.0.1:8787/preview?t=<token>`. Hat Knöpfe
für Ladezustand, leerer Akku, offene Tür, offline, Hybrid.

## Was noch offen ist

* **Android-App kompilieren** — sie wurde nie durch einen Compiler geschickt.
  Erster Schritt am MacBook: Android Studio, `androidapp` öffnen, bauen.
  Bewusst ohne Fremdbibliotheken (`HttpURLConnection` + `org.json`), damit
  wenig schiefgehen kann.
* **Watch-App auf echter Hardware** — braucht Huawei-Entwicklerkonto,
  Signatur und in AppGallery Connect registriertes Testgerät. Kein Sideload
  wie bei Android. Siehe [docs/INSTALL-WATCH.md](docs/INSTALL-WATCH.md).
* **Fernbefehle in der Android-App** fehlen absichtlich (bräuchten MQTT+OTP
  in Kotlin). Der Server antwortet dort mit 501 und klarer Meldung; die
  Python-Bridge kann sie.
* DevEco Studio: sehr neue Versionen bieten teils keine
  Lite-Wearable-Vorlage mehr; das Projektformat entspricht DevEco 3.1 / API 6.

## Umgangston mit diesem Projekt

* **Nichts über die Opel-API raten.** Wenn ein Wert unklar ist, `null`
  liefern und die Uhr `--` anzeigen lassen. Erfundene Zahlen über dem
  Ladestand des eigenen Autos sind schlimmer als eine Lücke.
* **Provider kapseln die Instabilität.** Ändert Stellantis etwas, wird nur in
  `bridge/opelbridge/providers/` bzw. `OpelApi.kt` nachgezogen — Uhr-App und
  Schema bleiben unangetastet.
* **Geheimnisse:** `bridge/config.json`, `bridge/state.json` und die Tokens
  der Android-App enthalten Fahrzeugzugang. Alles in `.gitignore`, nie
  committen, nie loggen, nie über `/api/v1/info` ausgeben.
* Code-Kommentare und Nutzertexte sind auf **Deutsch**, Bezeichner auf
  Englisch. Umlaute in Python/Kotlin-Kommentaren als `ae/oe/ue`
  ausgeschrieben, in Markdown und Android-Strings normal.
