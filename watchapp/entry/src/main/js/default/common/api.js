/*
 * Netzwerk- und Cache-Schicht der Uhr-App.
 *
 * Bewusst in ES5 geschrieben (var / function / keine Promises), weil die
 * JS-Engine der Lite-Wearable-Laufzeit nur einen kleinen ES6-Teil kann.
 */
import fetch from '@system.fetch';
import storage from '@system.storage';
import CONFIG from './config.js';

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

function url(path, extra) {
  var full = CONFIG.BASE_URL + path;
  full += (path.indexOf('?') >= 0 ? '&' : '?') + 't=' + CONFIG.TOKEN;
  if (extra) {
    full += extra;
  }
  return full;
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
    CONFIG.BASE_URL.indexOf('http') === 0 &&
    CONFIG.TOKEN !== 'HIER_TOKEN_EINTRAGEN' &&
    CONFIG.TOKEN.length > 0
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
    onFail('Bridge nicht konfiguriert - common/config.js anpassen', null);
    return;
  }

  var done = false;
  var timer = setTimeout(function () {
    if (!done) {
      done = true;
      readCache(function (cached) {
        onFail('Zeitueberschreitung', cached);
      });
    }
  }, CONFIG.TIMEOUT_MS);

  fetch.fetch({
    url: url('/api/v1/watch', options.force ? '&force=1' : ''),
    method: 'GET',
    responseType: 'text',
    header: {
      'X-Token': CONFIG.TOKEN,
      Accept: 'application/json'
    },
    success: function (response) {
      if (done) {
        return;
      }
      done = true;
      clearTimeout(timer);
      var code = response.code || 200;
      var data = parse(response.data);
      if (code === 401) {
        onFail('Token abgelehnt (401)', null);
        return;
      }
      if (code >= 400 || !data) {
        readCache(function (cached) {
          onFail('Bridge-Fehler ' + code, cached);
        });
        return;
      }
      data.recv = Date.now();
      writeCache(data);
      onSuccess(data, false);
    },
    fail: function (data, code) {
      if (done) {
        return;
      }
      done = true;
      clearTimeout(timer);
      readCache(function (cached) {
        onFail('Kein Kontakt zur Bridge (' + (code || '?') + ')', cached);
      });
    }
  });
}

/*
 * Sendet einen Remote-Befehl (wakeup / preconditioning / charge_now / lock).
 *   done(ok, message)
 */
function command(name, params, done) {
  var callback = done || function () {};
  if (!configured()) {
    callback(false, 'Bridge nicht konfiguriert');
    return;
  }
  var extra = '';
  if (params) {
    for (var key in params) {
      if (Object.prototype.hasOwnProperty.call(params, key)) {
        extra += '&' + key + '=' + encodeURIComponent(params[key]);
      }
    }
  }
  var finished = false;
  var timer = setTimeout(function () {
    if (!finished) {
      finished = true;
      callback(false, 'Zeitueberschreitung');
    }
  }, CONFIG.TIMEOUT_MS + 8000);

  fetch.fetch({
    url: url('/api/v1/command/' + name, extra),
    method: 'POST',
    responseType: 'text',
    header: {
      'X-Token': CONFIG.TOKEN,
      'Content-Type': 'application/json'
    },
    data: '{}',
    success: function (response) {
      if (finished) {
        return;
      }
      finished = true;
      clearTimeout(timer);
      var body = parse(response.data) || {};
      var ok = (response.code || 200) < 400 && body.ok !== false;
      callback(ok, body.message || body.error || (ok ? 'Gesendet' : 'Fehlgeschlagen'));
    },
    fail: function (data, code) {
      if (finished) {
        return;
      }
      finished = true;
      clearTimeout(timer);
      callback(false, 'Netzwerkfehler ' + (code || '?'));
    }
  });
}

/* Verbindungstest fuer die Einstellungsseite: done(ok, text) */
function ping(done) {
  if (!configured()) {
    done(false, 'config.js unvollstaendig');
    return;
  }
  fetch.fetch({
    url: url('/api/v1/info'),
    method: 'GET',
    responseType: 'text',
    header: { 'X-Token': CONFIG.TOKEN },
    success: function (response) {
      var body = parse(response.data) || {};
      if ((response.code || 200) === 401) {
        done(false, 'Token falsch');
        return;
      }
      if (body.config) {
        done(true, 'OK - ' + body.config.provider);
      } else {
        done(false, 'Antwort ungueltig');
      }
    },
    fail: function (data, code) {
      done(false, 'Offline (' + (code || '?') + ')');
    }
  });
}

export default {
  getState: getState,
  command: command,
  ping: ping,
  readCache: readCache,
  loadPrefs: loadPrefs,
  savePrefs: savePrefs,
  getPrefs: getPrefs,
  configured: configured
};
