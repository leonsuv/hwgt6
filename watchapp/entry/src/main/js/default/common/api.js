/*
 * Daten- und Cache-Schicht der Uhr-App.
 *
 * Die Daten kommen nicht per HTTP, sondern per Wear Engine von der
 * Handy-App (siehe p2p.js). Anfrage und Antwort sind kleine JSON-Texte:
 *   Uhr  -> Handy: {"cmd":"state","force":1}  |  {"cmd":"info"}
 *                  {"cmd":"command","name":"wakeup","params":{...}}
 *   Handy -> Uhr : dieselbe Nutzlast wie GET /api/v1/watch, ergaenzt um
 *                  "rt":"state"|"info"|"command"|"error"
 *
 * Bewusst in ES5 geschrieben (var / function / keine Promises), weil die
 * JS-Engine der Lite-Wearable-Laufzeit nur einen kleinen ES6-Teil kann.
 */
import storage from '@system.storage';
import CONFIG from './config.js';
import p2p from './p2p.js';
import util from './util.js';

/* Diagnose ans Handy schicken (Gadgetbridge schreibt sie ins Log). */
function remoteLog(msg) {
  try {
    p2p.send(JSON.stringify({ cmd: 'log', msg: String(msg).substring(0, 150) }), function () {});
  } catch (e) {
    /* ignorieren */
  }
}
util.setReporter(remoteLog);

var CACHE_KEY = 'opel_state_v1';
var PREF_KEY = 'opel_prefs_v1';

/* Laufzeit-Einstellungen, die die Settings-Seite veraendern darf. */
var prefs = {
  refresh_s: CONFIG.REFRESH_S,
  metric: CONFIG.METRIC,
  haptics: CONFIG.HAPTICS
};

function clone(obj) {
  var out = {};
  for (var key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      out[key] = obj[key];
    }
  }
  return out;
}

function parse(text) {
  if (!text) {
    return null;
  }
  if (typeof text === 'object') {
    return text;
  }
  try {
    return JSON.parse(text);
  } catch (e) {
    return null;
  }
}

/* ------------------------------------------------------- Wear Engine */

var pending = {};       /* rt -> { done: function(reply), timer: id } */
var linked = false;
var pushCb = null;      /* Empfaengt jede vom Handy gepushte Statusnachricht. */

/* Die Handy-App darf Daten auch unaufgefordert schicken (Push-Modell).
   onPush(cb) laesst die Uhr solche Nachrichten sofort anzeigen. */
function onPush(cb) {
  pushCb = cb;
  ensureLink();
}

function ensureLink() {
  if (linked) {
    return;
  }
  linked = true;
  p2p.init(CONFIG.PHONE_PACKAGE, CONFIG.PHONE_FINGERPRINT);
  p2p.subscribe(function (text) {
    var reply = parse(text);
    if (!reply) {
      remoteLog('unlesbar typ=' + (typeof text) + ' len=' + (text ? String(text).length : 0) +
        ' anfang=' + String(text).substring(0, 60));
      return;
    }
    var rt = reply.rt || 'state';
    var waiting = pending[rt];
    if (waiting) {
      delete pending[rt];
      clearTimeout(waiting.timer);
      waiting.done(reply);
    }
    /* Jede Statusnachricht (auch unaufgefordert) an die Anzeige geben. */
    if (rt === 'state' && pushCb) {
      reply.recv = Date.now();
      writeCache(reply);
      pushCb(reply);
    }
  });
}

/*
 * Anfrage an die Handy-App. done(reply) mit reply.rt === 'error' bei
 * Fehler (reply.msg enthaelt den Text).
 */
function request(cmd, extra, timeoutMs, done) {
  ensureLink();
  var body = { cmd: cmd };
  for (var key in extra) {
    if (Object.prototype.hasOwnProperty.call(extra, key)) {
      body[key] = extra[key];
    }
  }
  if (pending[cmd]) {
    clearTimeout(pending[cmd].timer);
  }
  pending[cmd] = {
    done: done,
    timer: setTimeout(function () {
      delete pending[cmd];
      done({ rt: 'error', msg: 'Keine Antwort vom Handy' });
    }, timeoutMs)
  };
  p2p.send(JSON.stringify(body), function (ok, detail) {
    if (!ok && pending[cmd]) {
      clearTimeout(pending[cmd].timer);
      delete pending[cmd];
      done({ rt: 'error', msg: detail || 'Handy nicht erreichbar' });
    }
  });
}

/* ------------------------------------------------------------ Praeferenzen */

function loadPrefs(done) {
  storage.get({
    key: PREF_KEY,
    default: '',
    success: function (value) {
      var stored = parse(value);
      if (stored) {
        if (stored.refresh_s) {
          prefs.refresh_s = stored.refresh_s;
        }
        if (typeof stored.metric === 'boolean') {
          prefs.metric = stored.metric;
        }
        if (typeof stored.haptics === 'boolean') {
          prefs.haptics = stored.haptics;
        }
      }
      if (done) {
        done(clone(prefs));
      }
    },
    fail: function () {
      if (done) {
        done(clone(prefs));
      }
    }
  });
}

function savePrefs(next, done) {
  for (var key in next) {
    if (Object.prototype.hasOwnProperty.call(next, key)) {
      prefs[key] = next[key];
    }
  }
  storage.set({
    key: PREF_KEY,
    value: JSON.stringify(prefs),
    success: function () {
      if (done) {
        done(clone(prefs));
      }
    },
    fail: function () {
      if (done) {
        done(clone(prefs));
      }
    }
  });
}

function getPrefs() {
  return clone(prefs);
}

/* ------------------------------------------------------------------ Cache */

function readCache(done) {
  storage.get({
    key: CACHE_KEY,
    default: '',
    success: function (value) {
      done(parse(value));
    },
    fail: function () {
      done(null);
    }
  });
}

function writeCache(data) {
  storage.set({
    key: CACHE_KEY,
    value: JSON.stringify(data),
    success: function () {},
    fail: function () {}
  });
}

/* -------------------------------------------------------------- Netzwerk */

function configured() {
  return (
    typeof CONFIG.PHONE_PACKAGE === 'string' && CONFIG.PHONE_PACKAGE.length > 0 &&
    typeof CONFIG.PHONE_FINGERPRINT === 'string' && CONFIG.PHONE_FINGERPRINT.length > 0
  );
}

/*
 * Holt den Fahrzeugzustand.
 *   opts.force   true -> Bridge fragt das Fahrzeug frisch ab
 *   opts.success function(data, fromCache)
 *   opts.fail    function(message, cachedDataOrNull)
 */
function getState(opts) {
  var options = opts || {};
  var onSuccess = options.success || function () {};
  var onFail = options.fail || function () {};

  if (!configured()) {
    onFail('Handy-App nicht konfiguriert - common/config.js anpassen', null);
    return;
  }

  request('state', { force: options.force ? 1 : 0 }, CONFIG.TIMEOUT_MS, function (reply) {
    if (reply.rt === 'error') {
      readCache(function (cached) {
        onFail(reply.msg || 'Handy nicht erreichbar', cached);
      });
      return;
    }
    reply.recv = Date.now();
    writeCache(reply);
    onSuccess(reply, false);
  });
}

/*
 * Sendet einen Remote-Befehl (wakeup / preconditioning / charge_now / lock).
 *   done(ok, message)
 */
function command(name, params, done) {
  var callback = done || function () {};
  if (!configured()) {
    callback(false, 'Handy-App nicht konfiguriert');
    return;
  }
  request('command', { name: name, params: params || {} }, CONFIG.TIMEOUT_MS + 8000, function (reply) {
    if (reply.rt === 'error') {
      callback(false, reply.msg || 'Fehlgeschlagen');
      return;
    }
    var ok = reply.ok !== false;
    callback(ok, reply.msg || reply.message || reply.error || (ok ? 'Gesendet' : 'Fehlgeschlagen'));
  });
}

/* Verbindungstest fuer die Einstellungsseite: done(ok, text) */
function ping(done) {
  if (!configured()) {
    done(false, 'config.js unvollstaendig');
    return;
  }
  request('info', {}, CONFIG.TIMEOUT_MS, function (reply) {
    if (reply.rt === 'error') {
      done(false, reply.msg || 'Offline');
      return;
    }
    if (reply.ok === false && reply.last_error) {
      done(false, String(reply.last_error).substring(0, 40));
      return;
    }
    done(true, 'OK - ' + (reply.vehicle || reply.provider || 'Handy'));
  });
}

export default {
  getState: getState,
  onPush: onPush,
  command: command,
  ping: ping,
  readCache: readCache,
  loadPrefs: loadPrefs,
  savePrefs: savePrefs,
  getPrefs: getPrefs,
  configured: configured
};
