/*
 * ===========================================================================
 *  HIER ANPASSEN - das ist die einzige Datei, die vor dem Bauen geaendert
 *  werden muss.
 * ===========================================================================
 *
 *  BASE_URL : Adresse der Opel-Bridge, erreichbar vom GEKOPPELTEN HANDY.
 *             Die Uhr hat kein eigenes WLAN-Routing - jeder Request laeuft
 *             ueber Huawei Health auf dem Telefon. Das Telefon muss die
 *             Bridge also erreichen (gleiches WLAN, VPN oder DynDNS).
 *
 *             Beispiele:
 *               'http://192.168.1.50:8787'      LAN
 *               'https://opel.meinserver.de'    ueber Internet (empfohlen)
 *
 *  TOKEN    : Shared Secret aus bridge/config.json (Feld "token").
 *             Die Bridge zeigt es beim Start an:
 *               py -m opelbridge --print-url
 *
 *  Kein abschliessender Schraegstrich bei BASE_URL!
 */
var CONFIG = {
  BASE_URL: 'http://192.168.1.50:8787',
  TOKEN: 'HIER_TOKEN_EINTRAGEN',

  /* Automatische Aktualisierung, waehrend die App offen ist (Sekunden).
     Kleiner Wert = aktueller, aber mehr Akkuverbrauch auf Uhr und Handy. */
  REFRESH_S: 60,

  /* Waehrend des Ladevorgangs schneller aktualisieren (Sekunden). */
  REFRESH_CHARGING_S: 30,

  /* Netzwerk-Timeout in Millisekunden. */
  TIMEOUT_MS: 12000,

  /* Daten gelten nach so vielen Minuten als veraltet -> Warnhinweis. */
  STALE_MIN: 30,

  /* Ladestand, ab dem die Anzeige rot wird (Prozent). */
  LOW_LEVEL: 20,

  /* true = km/Celsius, false = Meilen/Fahrenheit */
  METRIC: true,

  /* Vibrieren, wenn eine Aktion ausgefuehrt wurde. */
  HAPTICS: true,

  /* Remote-Befehle anzeigen (Bridge braucht allow_commands=true). */
  SHOW_ACTIONS: true
};

export default CONFIG;
