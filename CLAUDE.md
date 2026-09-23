# Kontext für KI-Assistenten

Kurzbriefing für ein Modell, das dieses Repo zum ersten Mal sieht. Lies das
zuerst, dann [README.md](README.md) für die Nutzersicht.

## Was das ist

Fahrzeugdaten aus **Opel Connect** (Stellantis, ex-PSA) auf einer **Huawei
Watch GT6** anzeigen. Vier Teile, ein gemeinsames Datenformat.

| Verzeichnis | Sprache | Läuft auf | Zustand |
| --- | --- | --- | --- |
| `watchapp/` | JS (HarmonyOS Lite Wearable) | Watch GT6 | **läuft auf der echten GT6 mit echten Opel-Daten** (vier Karten, animiert) |
| `gadgetbridge/` | Java (Patch) | Android-Telefon | Patch auf Gadgetbridge-master `e2ef406c`; Opel-Dienst für den P2P-Kanal, auf der GT6 verifiziert |
| `androidapp/` | Kotlin | Android-Telefon | „Opel Bridge“, auf Honor Magic 7 Pro mit echtem Opel-Konto verifiziert |
| `bridge/` | Python 3.8+, nur stdlib | PC / NAS / Pi | 36 Tests grün, real gegen Mock gelaufen |

## Die eine Sache, die man verstanden haben muss

**Die Watch GT6 hat für Apps gar keinen Netzzugang — auch nicht über das
Handy.** `@system.fetch` aus einer Lite-Wearable-App liefert auf der GT-Serie
immer `conect socket fail` (Code -6). Das wurde am 2026-09-21 auf einer
echten GT6 verifiziert; die frühere Annahme „Fetch wird durch Huawei Health
getunnelt" war falsch.

Der einzige Datenweg in eine Uhr-App ist Huaweis **Bluetooth-P2P-Kanal**
(Wear Engine, Dienst `0x34`). Offiziell läuft er über Huawei Health und
verlangt eine Wear-Engine-Freigabe der Android-App in AppGallery Connect
(Identitätsprüfung – vom Nutzer abgelehnt). **Tatsächlich genutzt wird
Gadgetbridge:** Es spricht das Huawei-Protokoll selbst, die Uhr prüft nur
Paketnamen und Fingerabdrücke als Text.

```
Uhr-App <-P2P-> Gadgetbridge (opel) <-ContentProvider-> Opel Bridge <-HTTPS-> Opel
```

Folgen daraus:

* Die Uhr-App (`watchapp/.../p2p.js`, `api.js`) schickt `{"cmd":"state"|"info"|"log"}`
  an `PHONE_PACKAGE`. Gadgetbridges `HuaweiP2POpelService` (aus
  `gadgetbridge/hwgt6-opel.patch`) holt die Antwort per ContentProvider
  `content://de.saigak.opelbridge.watch` bei der Opel Bridge, kompaktiert sie
  (P2P-Nachrichten an die Uhr werden ab ~200 Byte abgeschnitten) und schickt
  sie mit `"rt"` zurück.
* **Fingerabdrücke spiegeln:** Der Dienst verwendet exakt die Texte, die die
  Uhr selbst sendet (Telefon `UniteDeviceManagement`, Uhr
  `de.saigak.opelwatch_<Base64-Schlüssel>`). Andere Werte ⇒ Zustellcode 206.
* Die Uhr-App meldet eigene Ausnahmen als `{"cmd":"log"}`; Gadgetbridge
  schreibt sie nach `files/opelprobe.txt` (logcat ist auf Honor gesperrt):
  `adb shell run-as nodomain.freeyourgadget.gadgetbridge.opel cat files/opelprobe.txt`.
* Die Opel Bridge braucht eine **Akku-Ausnahme**, sonst sperrt Android ihr im
  Hintergrund das Netz (`blocked=APP_BACKGROUND`).
* `androidapp/.../WearLink.kt` ist der offizielle Weg über Huawei Health –
  ohne AGC-Freigabe „Code 12“, derzeit ungenutzt. Die PC-Bridge erreicht die
  Uhr nicht; sie bleibt für Vorschau, Tests und Fernbefehle.
* Es gibt keine Hintergrund-Aktualisierung auf der Uhr. Die App aktualisiert
  nur, solange sie offen ist.

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
  `@media`. **`class="{{x}}"` ist auf Lite nicht erlaubt** (Compiler-Fehler
  „class selector does not support data binding"). Dynamische Optik über
  `style="color: {{x}};"` oder `if`/`show` lösen.
* **Nur die Lite-CSS-Eigenschaften**: `border-width`/`border-color`/
  `border-radius` (keine Seiten-Varianten wie `border-bottom-width`), keine
  `indicator-*` am `swiper`, Winkel mit `deg`. Die vollständige Liste steht in
  `LITE_PROP_NAME_GROUPS` in DevEco:
  `sdk/default/openharmony/js/build-tools/ace-loader/lib/styler/lib/validator.js`.
* **Navigation nur mit `router.replace({ uri, params })`** — `router.push` und
  `router.back` existieren auf der GT6 nicht (`typeof router.push ===
  'undefined'`, verifiziert 2026-09-21). „Zurück" = `replace` zur Startseite
  mit `params: { startPage: n }`, die Startseite liest den Wert in `onInit`.
* **Kein RegExp:** `String.replace` wirft auf der GT6 `TypeError` – mit
  `indexOf`/`substring` arbeiten.
* **Elemente wachsen nicht mit dem Inhalt:** Texte und Container brauchen
  feste Breite und Höhe, sonst abgeschnitten oder unsichtbar. Keine Breiten
  per `style`-Bindung, stattdessen feste Klassen + `if`.
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

* **Eigene Zifferblätter (.hwt)** über Gadgetbridge: Upload wird von der GT6
  bestätigt, das Zifferblatt erscheint aber nie. Ausgeschlossen: Auflösung,
  Formatversion (Uhr: 2.1–2.12), nur `watchface.bin` vs. ganzes Paket,
  Version `1.0.0` vs. `2.1.1`. Nächster Schritt wäre ein HCI-Snoop von Huawei
  Health – verlangt Zurücksetzen der Uhr, vom Nutzer abgelehnt.
* **Fernbefehle** (Klima, Wecken) bewusst nicht: jede OTP-Registrierung
  riskiert das Opel-Konto. Die Python-Bridge kann sie.
* **GT-Uhren lehnen die config.json moderner DevEco-Builds ab** (Error 40).
  `watchapp/sign-watch.sh` schreibt sie ins klassische Format um (Ability
  und JS-Bundle heißen `default`, `icon.bin`/`icon_small.bin`, jede
  Berechtigung mit `reason` + `usedScene.when`), signiert mit
  `hap-sign-tool` und legt `dist/OpelWatch.fw` für den Datei-Installer von
  Gadgetbridge ab.

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
