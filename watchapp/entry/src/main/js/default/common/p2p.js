/*
 * Nachrichtenkanal Uhr <-> Handy-App ueber Wear Engine.
 *
 * Die GT-Serie hat fuer Apps keinen eigenen Netzzugang. Der einzige Weg zu
 * Daten ist die gekoppelte Handy-App, die per Wear Engine (Bluetooth-P2P)
 * Nachrichten mit der Uhr-App austauscht. Auf der Uhr stehen dafuer das
 * Modul @system.wearengine (Gegenstelle festlegen) und die globalen
 * FeatureAbility-Funktionen sendMsg / subscribeMsg / detect bereit.
 *
 * Voraussetzungen (Wear Engine prueft beides):
 *   - Paketname der Handy-App (PHONE_PACKAGE)
 *   - SHA-256 ihres Signaturzertifikats (PHONE_FINGERPRINT), Hex ohne ':'
 */
import wearengine from '@system.wearengine';

var peerPkg = '';
var peerFp = '';
var version = 0;
var configured = false;
var listener = null;

function log(text) {
  console.info('OpelWatch p2p: ' + text);
}

/* Gegenstelle bei Wear Engine hinterlegen (bei jedem Start noetig). */
function applyPeer() {
  try {
    wearengine.setPackageName({
      appName: peerPkg,
      complete: function () { log('peer package gesetzt'); },
      fail: function () { log('peer package FEHLER'); }
    });
    wearengine.setFingerprint({
      appName: peerPkg,
      appCert: peerFp,
      complete: function () { log('peer fingerprint gesetzt'); },
      fail: function () { log('peer fingerprint FEHLER'); }
    });
    configured = true;
  } catch (e) {
    log('setPeer Ausnahme: ' + e);
  }
}

function init(pkg, fingerprint) {
  peerPkg = pkg;
  peerFp = fingerprint;
  try {
    wearengine.getWearEngineVersion({
      sdkVersion: '3',
      complete: function (data) {
        if (data) {
          var parts = String(data).split('.');
          version = parseInt(parts[parts.length - 1], 10) || 0;
        }
        log('service version ' + data);
        applyPeer();
      }
    });
  } catch (e) {
    log('getWearEngineVersion Ausnahme: ' + e);
    applyPeer();
  }
}

/*
 * Nachrichten der Handy-App empfangen. onMessage(text) bekommt den
 * Nachrichtentext (Datei-Nachrichten werden nicht benutzt).
 */
function subscribe(onMessage) {
  listener = onMessage;
  if (!configured) {
    applyPeer();
  }
  try {
    FeatureAbility.subscribeMsg({
      success: function (data) {
        if (!data) {
          return;
        }
        if (data.isRegister) {
          log('Empfaenger registriert');
          return;
        }
        if (data.isFileType) {
          log('Datei-Nachricht ignoriert');
          return;
        }
        /* Probe/Diagnose: JEDE empfangene Nachricht sichtbar machen. */
        log('empfangen: ' + data.message);
        if (listener) {
          listener(data.message);
        }
      },
      fail: function (data, code) {
        log('subscribe FEHLER ' + code + ' ' + data);
      }
    });
  } catch (e) {
    log('subscribeMsg Ausnahme: ' + e);
  }
}

function unsubscribe() {
  listener = null;
  try {
    FeatureAbility.unsubscribeMsg();
  } catch (e) {
    /* nicht registriert */
  }
}

/* Text an die Handy-App schicken. done(ok, detail). */
function send(text, done) {
  var cb = done || function () {};
  if (!configured) {
    applyPeer();
  }
  try {
    FeatureAbility.sendMsg({
      deviceId: 'remote',
      bundleName: peerPkg,
      abilityName: '',
      message: text,
      success: function () { cb(true, ''); },
      fail: function (data, code) {
        log('send FEHLER ' + code + ' ' + data);
        cb(false, 'Senden fehlgeschlagen (' + code + ')');
      }
    });
  } catch (e) {
    log('sendMsg Ausnahme: ' + e);
    cb(false, 'Wear Engine nicht verfuegbar');
  }
}

/* Ist die Handy-App installiert und laeuft sie? done(code): 200-205 */
function ping(done) {
  try {
    FeatureAbility.detect({
      bundleName: peerPkg,
      success: function (data) { done(data && data.code !== undefined ? data.code : data); },
      fail: function (data, code) { done(code || -1); }
    });
  } catch (e) {
    done(-1);
  }
}

export default {
  init: init,
  subscribe: subscribe,
  unsubscribe: unsubscribe,
  send: send,
  ping: ping
};
