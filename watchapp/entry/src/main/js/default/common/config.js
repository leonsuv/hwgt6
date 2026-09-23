/*
 * ===========================================================================
 *  HIER ANPASSEN - das ist die einzige Datei, die vor dem Bauen geaendert
 *  werden muss.
 * ===========================================================================
 *
 *  Die GT-Uhr hat fuer Apps keinen eigenen Netzzugang. Die Daten kommen per
 *  Wear Engine (Bluetooth) von der Android-App "Opel Bridge" auf dem
 *  gekoppelten Handy. Damit Wear Engine die Verbindung erlaubt, muss die
 *  Uhr die Handy-App eindeutig kennen:
 *
 *  PHONE_PACKAGE     : Paketname der Android-App (androidapp/app/build.gradle,
 *                      applicationId)
 *  PHONE_FINGERPRINT : SHA-256 des Zertifikats, mit dem die APK signiert
 *                      ist - Hex, Grossbuchstaben, ohne Doppelpunkte.
 *                      Debug-Keystore:  keytool -list -v -alias androiddebugkey
 *                        -keystore ~/.android/debug.keystore -storepass android
 *
 *  BASE_URL / TOKEN  : nur noch fuer die HTTP-Schnittstelle der Handy-App
 *                      (Browser-Test, Vorschau); die Uhr benutzt sie nicht.
 */
var CONFIG = {
  PHONE_PACKAGE: 'de.saigak.opelbridge',
  PHONE_FINGERPRINT: 'UniteDeviceManagement',

  BASE_URL: 'http://127.0.0.1:8787',
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
  HAPTICS: true
};

export default CONFIG;
