/*

 * Reine Formatierlogik - kein Zugriff auf System-APIs.

 * Diese Datei wird auch vom Browser-Simulator (tools/preview.html) geladen,

 * damit Uhr und Vorschau garantiert identisch rechnen.

 */



var DOOR_NAMES = {

  fl: 'vorne links',

  fr: 'vorne rechts',

  rl: 'hinten links',

  rr: 'hinten rechts',

  trunk: 'Kofferraum',

  hood: 'Motorhaube',

  roof: 'Dach',

  rear: 'Heckscheibe'

};



var COLORS = {

  ok: '#f5a623',        /* Opel-Gelb - Normalzustand      */

  charge: '#3ddc84',    /* Gruen - laedt                  */

  low: '#ff5252',       /* Rot - kritischer Ladestand     */

  idle: '#5a5a5a',      /* Grau - Hintergrundring         */

  text: '#ffffff',

  dim: '#8c8c8c'

};



function pad2(value) {

  return value < 10 ? '0' + value : '' + value;

}



/* 24310 -> "24.310" */

function groupThousands(value) {

  var text = '' + Math.abs(Math.round(value));

  var out = '';

  var count = 0;

  for (var i = text.length - 1; i >= 0; i--) {

    out = text.charAt(i) + out;

    count++;

    if (count % 3 === 0 && i > 0) {

      out = '.' + out;

    }

  }

  return (value < 0 ? '-' : '') + out;

}



/* 7.4 -> "7,4" (deutsches Dezimalkomma) */

function decimal(value, digits) {

  if (value === null || value === undefined) {

    return '--';

  }

  var factor = Math.pow(10, digits === undefined ? 1 : digits);

  var rounded = Math.round(value * factor) / factor;

  var text = '' + rounded;

  if (text.indexOf('.') < 0 && digits > 0) {

    text += '.0';

  }

  /* Kein String.replace: die GT6-Laufzeit wirft dort TypeError (kein RegExp). */
  var dot = text.indexOf('.');
  return dot < 0 ? text : text.substring(0, dot) + ',' + text.substring(dot + 1);

}



function isNum(value) {

  return value !== null && value !== undefined && !isNaN(value);

}



/* Sekunden -> "gerade eben" / "vor 4 Min" / "vor 2 Std" / "vor 3 Tg" */

function ago(seconds) {

  if (!isNum(seconds) || seconds < 0) {

    return '--';

  }

  if (seconds < 90) {

    return 'gerade eben';

  }

  var minutes = Math.round(seconds / 60);

  if (minutes < 60) {

    return 'vor ' + minutes + ' Min';

  }

  var hours = Math.round(minutes / 60);

  if (hours < 24) {

    return 'vor ' + hours + ' Std';

  }

  return 'vor ' + Math.round(hours / 24) + ' Tg';

}



/* Minuten -> "1:25 h" oder "18 min" */

function duration(minutes) {

  if (!isNum(minutes) || minutes <= 0) {

    return '--';

  }

  if (minutes < 60) {

    return Math.round(minutes) + ' min';

  }

  var hours = Math.floor(minutes / 60);

  return hours + ':' + pad2(Math.round(minutes % 60)) + ' h';

}



function kmOrMiles(km, metric) {

  if (!isNum(km)) {

    return '--';

  }

  if (metric === false) {

    return groupThousands(km * 0.621371) + ' mi';

  }

  return groupThousands(km) + ' km';

}



function temp(celsius, metric) {

  if (!isNum(celsius)) {

    return '--';

  }

  if (metric === false) {

    return Math.round(celsius * 9 / 5 + 32) + ' \u00b0F';

  }

  /* Ganze Grad ohne ",0" - die API liefert meist ganze Zahlen */
  var tenths = Math.round(celsius * 10);
  return (tenths % 10 === 0 ? '' + tenths / 10 : decimal(celsius, 1)) + ' \u00b0C';

}



function doorList(codes) {

  if (!codes || !codes.length) {

    return '';

  }

  var parts = [];

  for (var i = 0; i < codes.length; i++) {

    parts.push(DOOR_NAMES[codes[i]] || codes[i]);

  }

  return parts.join(', ');

}



/*

 * Baut aus der kompakten Bridge-Antwort alle Anzeigewerte.

 *   data  : JSON von /api/v1/watch  (oder null)

 *   opts  : { metric: bool, lowLevel: int, staleMin: int, error: string }

 */

function buildView(data, opts) {

  var options = opts || {};

  var metric = options.metric !== false;

  var lowLevel = options.lowLevel || 20;

  var staleMin = options.staleMin || 30;



  var view = {

    ready: false,

    name: 'Opel',

    level: 0,

    levelText: '--',

    unit: '%',

    rangeText: '--',

    ring: 0,

    ringColor: COLORS.idle,

    accent: COLORS.ok,

    statusLine: 'Keine Daten',

    statusIcon: '',

    charging: false,

    plugged: false,

    ageText: '--',

    stale: true,

    offline: !!options.error,

    error: options.error || '',

    lockText: 'unbekannt',

    lockOk: false,

    doorsText: 'unbekannt',

    doorsOpen: false,

    climateText: 'aus',

    climateOn: false,

    tempInText: '--',

    tempOutText: '--',

    odoText: '--',

    etaText: '',

    targetText: '',

    posText: '--',

    hasPos: false,

    alerts: [],

    hasAlerts: false,

    secondaryText: '',

    hasSecondary: false,

    source: ''

  };



  if (!data) {

    return view;

  }



  view.ready = true;

  view.name = data.nm || 'Opel';

  view.source = data.src || '';

  view.charging = data.chg === 1;

  view.plugged = data.plg === 1;



  var level = isNum(data.lvl) ? data.lvl : null;

  if (level !== null) {

    view.level = level;

    view.levelText = '' + Math.round(level);

    view.ring = Math.max(0, Math.min(100, level));

  }



  view.rangeText = kmOrMiles(data.rng, metric);



  /* Farbe: laden schlaegt niedrigen Stand, niedrig schlaegt Normalzustand */

  if (view.charging) {

    view.accent = COLORS.charge;

  } else if (level !== null && level <= lowLevel) {

    view.accent = COLORS.low;

  } else {

    view.accent = COLORS.ok;

  }

  view.ringColor = view.accent;



  /* Statuszeile unter der grossen Zahl.

     Die PSA-Schnittstelle liefert keine Ladeleistung in kW, sondern den

     Reichweitenzuwachs in km/h - dann wird der angezeigt. */

  if (view.charging) {

    var parts = [];

    if (isNum(data.kw)) {

      parts.push(decimal(data.kw, 1) + ' kW');

    } else if (isNum(data.kmh) && data.kmh > 0) {

      parts.push(metric === false

        ? '+' + Math.round(data.kmh * 0.621371) + ' mi/h'

        : '+' + Math.round(data.kmh) + ' km/h');

    }

    if (isNum(data.eta) && data.eta > 0) {

      parts.push('noch ' + duration(data.eta));

    }

    view.statusLine = parts.length ? parts.join('  \u00b7  ') : 'l\u00e4dt';

    view.statusIcon = '\u26a1';

  } else if (view.plugged) {

    view.statusLine = 'Stecker verbunden';

    view.statusIcon = '\u26a1';

  } else if (data.et === 'fuel') {

    view.statusLine = 'Tankf\u00fcllung';

    view.statusIcon = '';

  } else {

    view.statusLine = 'nicht verbunden';

    view.statusIcon = '';

  }



  if (isNum(data.tgt) && data.tgt > 0 && data.tgt < 100) {

    view.targetText = 'Ziel ' + Math.round(data.tgt) + '%';

  }

  if (isNum(data.eta) && data.eta > 0) {

    view.etaText = duration(data.eta);

  }



  /* Hybrid: zweite Energiequelle */

  if (isNum(data.lvl2)) {

    view.hasSecondary = true;

    view.secondaryText =

      'Tank ' + Math.round(data.lvl2) + '%' +

      (isNum(data.rng2) ? '  \u00b7  ' + kmOrMiles(data.rng2, metric) : '');

  }



  var age = isNum(data.age) ? data.age : null;

  view.ageText = ago(age);

  view.stale = age === null || age > staleMin * 60;



  if (data.lck === 1) {

    view.lockText = 'verriegelt';

    view.lockOk = true;

  } else if (data.lck === 0) {

    view.lockText = 'NICHT verriegelt';

    view.lockOk = false;

  } else {

    view.lockText = 'unbekannt';

  }



  var openCount = isNum(data.opn) ? data.opn : 0;

  view.doorsOpen = openCount > 0;

  if (openCount > 0) {

    var names = doorList(data.opl);

    view.doorsText = names || (openCount + ' offen');

  } else if (data.lck === -1) {

    view.doorsText = 'unbekannt';

  } else {

    view.doorsText = 'alle geschlossen';

  }



  view.climateOn = data.clm === 1;

  view.climateText = view.climateOn ? 'l\u00e4uft' : 'aus';

  view.tempInText = temp(data.tin, metric);

  view.tempOutText = temp(data.tout, metric);

  view.odoText = kmOrMiles(data.odo, metric);



  if (isNum(data.lat) && isNum(data.lon)) {

    view.hasPos = true;

    view.posText = decimal(data.lat, 4) + ' / ' + decimal(data.lon, 4);

  }



  view.alerts = data.alt || [];

  view.hasAlerts = view.alerts.length > 0;



  if (data.err) {

    view.error = data.err;

    view.offline = true;

  }

  return view;

}



var UTIL = {

  COLORS: COLORS,

  DOOR_NAMES: DOOR_NAMES,

  buildView: buildView,

  ago: ago,

  duration: duration,

  decimal: decimal,

  groupThousands: groupThousands,

  kmOrMiles: kmOrMiles,

  temp: temp,

  doorList: doorList,

  isNum: isNum

};



/* Fuer die Fehlersuche auf der Uhr: Ausnahme mit Ort ins Log schreiben. */
function guard(tag, fn) {
  try {
    return fn();
  } catch (e) {
    var msg = 'OpelWatch ' + tag + ': ' + (e && e.message ? e.message : e);
    console.error(msg);
    report(msg);
    return undefined;
  }
}

/* Optionaler Rueckkanal fuer Diagnose ans Handy (setzt api.js). */
var reporter = null;

function setReporter(fn) {
  reporter = fn;
}

function report(msg) {
  if (reporter) {
    try {
      reporter(msg);
    } catch (e) {
      /* Diagnose darf nie selbst stoeren */
    }
  }
}

UTIL.guard = guard;
UTIL.setReporter = setReporter;
UTIL.report = report;
export default UTIL;

