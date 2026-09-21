# Watch-App bauen und auf die GT6 bringen

Die Huawei Watch GT6 laeuft nicht mit dem grossen HarmonyOS der Mate-Telefone,
sondern mit der schlanken **Lite-Wearable**-Laufzeit. Apps dafuer sind
JS-Anwendungen (HML/CSS/JS), werden zu einer `.hap`-Datei gebaut, **muessen
signiert sein** und werden ueber DevEco Studio oder AppGallery Connect
verteilt. Ein Sideload wie eine APK auf Android gibt es nicht.

## Voraussetzungen

| Was | Warum |
| --- | --- |
| Windows- oder macOS-Rechner | DevEco Studio |
| [DevEco Studio](https://developer.huawei.com/consumer/en/deveco-studio/) | Baut und signiert das Projekt |
| Huawei-ID mit Entwicklerstatus (kostenlos, Identitaetspruefung noetig) | Ohne Signatur laeuft nichts auf der Uhr |
| Die GT6, gekoppelt mit Huawei Health | Zielgeraet und Netzzugang der Uhr |

> Beim Einrichten von DevEco Studio die **Lite-Wearable-/JS-SDKs (API 6)**
> mitinstallieren. Wenn eine sehr neue DevEco-Version keine Lite-Wearable-Vorlage
> mehr anbietet, hilft DevEco Studio 3.1 aus dem Archiv &ndash; das Projektformat in
> `watchapp/` entspricht dieser Generation.

## 1. Bridge-Adresse eintragen

`watchapp/entry/src/main/js/default/common/config.js`:

```js
var CONFIG = {
  BASE_URL: 'http://192.168.1.50:8787',   // ohne / am Ende
  TOKEN: 'AbCdEf...',                     // aus bridge/config.json
  ...
};
```

Die Adresse muss **vom Telefon aus** erreichbar sein, nicht vom PC &ndash; die Uhr
tunnelt ihre Anfragen durch Huawei Health. Schneller Test: die URL

```
http://192.168.1.50:8787/api/v1/watch?t=DEIN_TOKEN
```

im Browser des Telefons oeffnen. Kommt JSON zurueck, wird es auch auf der Uhr
funktionieren. Kommt nichts, liegt es am Netz (WLAN, Firewall), nicht an der App.

Danach pruefen:

```bat
py tools\check_watchapp.py
```

Das Werkzeug meldet Syntaxfehler, versehentliches ES6 (die Uhr kann kein
`let`/`const`/Arrow-Funktionen), kaputte HML-Dateien und einen vergessenen
Platzhalter im Token.

## 2. Projekt oeffnen und bauen

1. DevEco Studio starten &rarr; *File &rarr; Open* &rarr; Ordner `watchapp` waehlen.
2. Gradle laeuft durch (beim ersten Mal einige Minuten).
3. *Build &rarr; Build Hap(s)/APP(s) &rarr; Build Hap(s)*.
4. Ergebnis: `watchapp/entry/build/outputs/hap/debug/entry-debug-unsigned.hap`
   (bzw. `release`).

Erscheint ein Fehler zu `compileSdkVersion 6`: im SDK-Manager die API-6-Pakete
fuer Lite Wearable nachinstallieren oder die Versionen in `build.gradle` an das
lokal vorhandene SDK anpassen.

## 3. Signieren

Ohne gueltige Signatur verweigert die Uhr die Installation.

1. In [AppGallery Connect](https://developer.huawei.com/consumer/en/service/josp/agc/index.html)
   ein Projekt und eine **HarmonyOS-App** (Geraetetyp: Wearable) anlegen. Die
   `bundleName` muss zu `watchapp/entry/src/main/config.json` passen
   (`de.saigak.opelwatch`) &ndash; oder dort auf den eigenen Namen aendern.
2. DevEco Studio: *File &rarr; Project Structure &rarr; Signing Configs* &rarr;
   *Automatically generate signature* (empfohlen). DevEco erzeugt Schluessel,
   Zertifikat und Profil und laedt sie in AGC hoch.
3. Manuell geht es ueber *Build &rarr; Generate Key and CSR*, in AGC ein
   Debug-Zertifikat (`.cer`) und ein Debug-Profil (`.p7b`) erzeugen und beides
   in den Signing Configs hinterlegen.

Wichtig fuer den Debug-Weg: die Uhr muss in AGC als **Testgeraet** registriert
sein. Die dafuer noetige Geraete-ID (UDID) zeigt DevEco beim Verbinden an, auf
der Uhr steht sie unter *Einstellungen &rarr; System &rarr; Info &rarr; (mehrfach tippen)*.
Ein Debug-Profil gilt fuer maximal 100 registrierte Geraete und laeuft nach
einem Jahr ab.

## 4. Auf die Uhr uebertragen

**Weg A &ndash; direkt aus DevEco Studio (fuer die eigene Uhr der uebliche Weg):**

1. Uhr per USB-Ladeschale mit dem Rechner verbinden.
2. Auf der Uhr *Einstellungen &rarr; System &rarr; Entwickleroptionen &rarr; ADB-Debugging*
   aktivieren (Entwickleroptionen erscheinen nach mehrfachem Tippen auf die
   Versionsnummer unter *Info*).
3. In DevEco Studio das Geraet in der Geraeteliste waehlen und *Run 'entry'*
   druecken. Die App wird installiert und gestartet.

**Weg B &ndash; ueber AppGallery Connect:** signiertes Release-`.hap` hochladen und
als geschlossenen Test (bis zu 1000 Tester) verteilen. Die Installation laeuft
dann ueber *Huawei Health &rarr; Geraet &rarr; App-Galerie der Uhr*. Dieser Weg braucht
eine Pruefung durch Huawei, dauert also laenger, haelt aber dauerhaft.

## 5. Erster Start

Nach dem Start zeigt die App:

* **Zahlen erscheinen** &ndash; alles richtig.
* **"Bridge nicht konfiguriert"** &ndash; `config.js` wurde nicht angepasst oder
  nicht neu gebaut.
* **"Token abgelehnt (401)"** &ndash; Token in `config.js` und `bridge/config.json`
  stimmen nicht ueberein.
* **"Kein Kontakt zur Bridge"** &ndash; Telefon erreicht den Bridge-Rechner nicht:
  anderes WLAN, Firewall, Rechner im Ruhezustand oder falsche IP. IP-Adressen
  aus DHCP aendern sich &ndash; feste Adresse vergeben oder DynDNS benutzen.
* **Uhrzeitangabe "vor 4 Std"** &ndash; kein Fehler: so alt ist die letzte Meldung
  des Fahrzeugs. Karte 3 &rarr; *Jetzt aktualisieren* erzwingt eine frische Abfrage.

Auf Karte 3 &rarr; *Einstellungen &rarr; Verbindung testen* prueft die Uhr die Bridge und
zeigt den aktiven Provider an.

## Was auf der Uhr absichtlich anders ist

* **ES5 statt moderner Syntax**: Die JS-Engine der Lite-Wearable-Laufzeit
  (JerryScript) kennt kein `let`, `const`, keine Arrow-Funktionen und keine
  Promises. Der gesamte App-Code haelt sich daran; `check_watchapp.py` wacht
  darueber.
* **Kein `position: absolute` fuer Layout**: Ueberlagerungen laufen ueber
  `<stack>`, Listen ueber `<list>`/`<list-item>`.
* **Kleines JSON**: Die Bridge liefert der Uhr kurze Schluessel
  (`lvl`, `rng`, `chg`, ...) statt des vollen Modells &ndash; unter 700 Byte pro
  Abruf, was Bluetooth-Latenz und Akku schont.
* **Schwarzer Hintergrund**: AMOLED verbraucht fuer schwarze Pixel nahezu
  keinen Strom.
