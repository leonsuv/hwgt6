# Uhr-App bauen, signieren und installieren

Die Huawei Watch GT6 läuft mit der schlanken **Lite-Wearable**-Laufzeit von
HarmonyOS. Apps dafür sind JS-Anwendungen (HML/CSS/JS), werden zu einem
signierten Paket gebaut und hier über **Gadgetbridge (opel)** auf die Uhr
gebracht – ohne Huawei Health, ohne AppGallery.

## Voraussetzungen

| Was | Wofür |
| --- | --- |
| macOS (Windows geht mit DevEco ebenso, die Skripte sind für macOS/Linux) | Bauen |
| [DevEco Studio](https://developer.huawei.com/consumer/en/deveco-studio/) 6.x | liefert hvigor, Node, Lite-SDK und Signaturwerkzeug |
| Huawei-ID mit Zugang zu AppGallery Connect | Debug-Zertifikat und -Profil (kein Wear-Engine-Antrag, keine Identitätsprüfung nötig) |
| Gadgetbridge (opel), mit der Uhr gekoppelt | Installation, siehe [GADGETBRIDGE.md](GADGETBRIDGE.md) |

Die Skripte erwarten DevEco unter `/Applications/DevEco-Studio.app`; sonst
`DEVECO_HOME=/pfad/zu/DevEco-Studio.app/Contents` setzen.

## 1. Prüfen

```bash
python3 tools/check_watchapp.py
```

Das prüft alles, was die Uhr-Laufzeit übel nimmt: ES6-Syntax (nur ES5 erlaubt),
Nicht-ASCII-Zeichen im JS, kaputte HML/JSON-Dateien, fehlende Seiten.

## 2. Bauen

```bash
cd watchapp
./build-watch.sh
```

Das nutzt hvigor und Node aus DevEco Studio; die IDE muss dafür nicht laufen.
Alternativ in DevEco: *File → Open → `watchapp`* → *Build → Build Hap(s)*.

## 3. Signieren – einmalig einrichten

Die Uhr installiert nur signierte Pakete. Einmalig in `watchapp/signing/`
ablegen (der Ordner steht in `.gitignore`):

| Datei | Herkunft |
| --- | --- |
| `opelwatch.p12`, `opelwatch.csr` | DevEco: *Build → Generate Key and CSR* (Alias `opelwatch`) |
| `keystore-password.txt` | das dabei gewählte Passwort, eine Zeile |
| `opelwatch-debug.cer` | AppGallery Connect → *Zertifikate* → Debug-Zertifikat aus der CSR |
| `opelwatch-debug.p7b` | AppGallery Connect → *HAP Provision Profile* → Debug-Profil |

In AppGallery Connect dafür:

1. Ein Projekt und eine **HarmonyOS-App** (Gerätetyp *Wearable*) mit dem
   Paketnamen **`de.saigak.opelwatch`** anlegen (oder in
   `watchapp/entry/src/main/config.json` den eigenen eintragen – dann auch
   `WATCH_PKG` im Gadgetbridge-Patch anpassen).
2. Die Uhr als **Testgerät** registrieren. Die UDID zeigt DevEco an, wenn die
   Uhr über WLAN-Debugging verbunden ist.
3. Debug-Zertifikat aus der CSR erzeugen, dann das Debug-Profil mit
   Zertifikat und Testgerät.

> Debug-Profile laufen ab. Danach ein neues Profil erzeugen, neu signieren
> und neu installieren. Der Gadgetbridge-Dienst muss dafür **nicht** angepasst
> werden: Der Fingerabdruck der Uhr-App hängt am Schlüssel, nicht am Zertifikat.

## 4. Signieren

```bash
./sign-watch.sh 6
```

Das Skript schreibt die `config.json` in das klassische Format um, das die
GT-Uhren verlangen (neuere DevEco-Builds bricht die Uhr sonst mit
*Error 40* ab), baut das Binärpaket und signiert es. Ergebnis:

* `dist/OpelWatch.fw` – **das hier installieren**
* `dist/OpelWatch-signed.hap` – dasselbe als HAP (für DevEco/Huawei-Werkzeuge)

## 5. Installieren

```bash
adb push dist/OpelWatch.fw /sdcard/Download/
```

Dann auf dem Telefon:

**Gadgetbridge (opel) → ⋮ beim Gerät → Datei-Installer → `OpelWatch.fw` → Installieren**

Kurz darauf steht **Opel Watch** in der App-Liste der Uhr.
Eine neue Version wird genauso drüber installiert.

## 6. Erster Start

Die App öffnen – der Ring zieht sich auf den Ladestand auf. Wenn nicht:

| Anzeige | Ursache |
| --- | --- |
| rot **„Keine Antwort vom Handy“** | Gadgetbridge (opel) nicht verbunden oder der Opel-Dienst nicht registriert – in Gadgetbridge verbinden, Protokoll prüfen ([GADGETBRIDGE.md](GADGETBRIDGE.md#fehlersuche)) |
| überall **„--“**, aber keine rote Meldung | Verbindung steht, die Opel Bridge hat keine Daten – öffnen und prüfen, ob sie bei Opel angemeldet ist ([ANDROID-APP.md](ANDROID-APP.md)) |
| Zahlen da, aber **„Auto meldete vor 3 Std“** | kein Fehler: so alt ist die letzte Meldung des Autos |

**Menü → Einstellungen → Verbindung testen** muss **„OK - Opel“** zeigen.

## Regeln der Lite-Laufzeit

Wer an der Uhr-App arbeitet, stößt auf diese Eigenheiten der GT6:

* **Nur ES5** (JerryScript): kein `let`/`const`, keine Arrow-Funktionen,
  keine Promises. `import`/`export` gehen, sie werden beim Bauen aufgelöst.
* **Nur ASCII im JS**, Umlaute als `\u00e4` usw.
* **Kein RegExp:** `String.replace` wirft einen `TypeError` – mit
  `indexOf`/`substring` arbeiten.
* **Elemente wachsen nicht mit dem Inhalt.** Jeder Text und jeder Container
  braucht eine feste Breite und Höhe, sonst wird er abgeschnitten oder bleibt
  unsichtbar. Breiten nicht per `style` binden, sondern feste Klassen wählen.
* **`class="{{x}}"` ist verboten** (Compilerfehler), mehrere Klassen pro
  Element besser vermeiden – dynamische Optik über `style="color: {{x}}"` oder `if`.
* **Nur `router.replace`** – `push` und `back` gibt es nicht.
* **Animationen:** `@keyframes` kennt nur `from`/`to`. Der Ladering zählt
  deshalb per `setInterval` hoch, Puls und Drehung laufen über `@keyframes`.
* 466 × 466 px, rund, schwarzer Hintergrund (AMOLED).
