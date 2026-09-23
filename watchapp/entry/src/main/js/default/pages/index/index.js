import router from '@system.router';
import vibrator from '@system.vibrator';
import api from '../../common/api.js';
import util from '../../common/util.js';
import CONFIG from '../../common/config.js';

var IMG = '/common/images/';
var DOT_ON = '#f5a623';
var DOT_OFF = '#3a3a3a';

/* Anzahl Stellen -> passende feste Breitenklasse (1..3) */
function digits(text) {
  var n = String(text).length;
  return n <= 1 ? 1 : (n >= 3 ? 3 : 2);
}

export default {
  data: {
    view: util.guard('data.view', function () { return util.buildView(null, {}); }),
    page: 0,
    startPage: '',
    busy: false,
    notBusy: true,
    toastText: '',

    /* Karte 1 - Ring und Zahl werden animiert hochgezaehlt */
    ringNow: 0,
    levelNow: '--',
    levelD1: false,
    levelD2: true,
    levelD3: false,
    hasLevel: false,
    hasRange: false,
    rangeNum: '--',
    rangeUnit: '',
    rangeD1: false,
    rangeD2: true,
    rangeD3: false,
    ageLine: '',
    ageColor: '#6e6e6e',
    odoLine: '',
    isCharging: false,
    notCharging: true,
    plugIconS: IMG + 'plug_off_s.png',

    /* Karte 2 */
    plugIconL: IMG + 'plug_off_l.png',
    plugColor: '#8c8c8c',
    chargeHero: '--',
    statA: '--',
    statALabel: '',
    statB: '--',
    statBLabel: '',

    /* Karte 3 */
    nameUpper: 'OPEL',
    lockIcon: IMG + 'lock_unknown.png',
    lockText: '--',
    lockColor: '#8c8c8c',
    outsideShort: '--',
    doorsShort: '--',
    doorColor: '#ffffff',
    climateRow: '--',
    alertText: '',

    /* Karte 4 */
    ageFoot: '',

    /* Seitenpunkte */
    dot0: DOT_ON,
    dot1: DOT_OFF,
    dot2: DOT_OFF,
    dot3: DOT_OFF,

    /* Beschriftungen hier, damit Umlaute als \u-Escape im JS bleiben */
    L: {
      charge: 'LADEN',
      doors: 'T\u00fcren',
      outside: 'Au\u00dfen',
      climate: 'Klima',
      refresh: 'Aktualisieren'
    },

    timer: 0,
    toastTimer: 0,
    animTimer: 0,
    shownLevel: -1,
    lastCharging: false
  },

  /* ------------------------------------------------------- Lebenszyklus */

  onInit: function () {
    var that = this;
    return util.guard('onInit', function () {
      var self = that;
      /* Rueckweg von Detail/Einstellungen: gewuenschte Karte per params */
      if (that.startPage !== undefined && that.startPage !== null && that.startPage !== '') {
        that.page = parseInt(that.startPage, 10) || 0;
      }
      that.markDots(that.page);
      api.loadPrefs(function () {
        api.readCache(function (cached) {
          if (cached) {
            self.apply(cached, '');
          }
        });
      });
    });
  },

  onShow: function () {
    var that = this;
    return util.guard('onShow', function () {
      /* Vom Handy gepushte Daten sofort anzeigen (Push-Modell). */
      api.onPush(function (data) {
        that.apply(data, '');
      });
      that.refresh(false);
      that.startTimer();
    });
  },

  onHide: function () {
    this.stopTimer();
    this.stopAnim();
  },

  onDestroy: function () {
    this.stopTimer();
    this.stopAnim();
  },

  startTimer: function () {
    var that = this;
    return util.guard('startTimer', function () {
      var self = that;
      that.stopTimer();
      var seconds = api.getPrefs().refresh_s || CONFIG.REFRESH_S;
      if (that.lastCharging && CONFIG.REFRESH_CHARGING_S < seconds) {
        seconds = CONFIG.REFRESH_CHARGING_S;
      }
      that.timer = setInterval(function () {
        self.refresh(false);
      }, Math.max(15, seconds) * 1000);
    });
  },

  stopTimer: function () {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = 0;
    }
  },

  /* ------------------------------------------------------------- Daten */

  setBusy: function (busy) {
    this.busy = busy;
    this.notBusy = !busy;
  },

  refresh: function (force) {
    var that = this;
    return util.guard('refresh', function () {
      var self = that;
      if (that.busy) {
        return;
      }
      that.setBusy(true);
      api.getState({
        force: force,
        success: function (data) {
          self.setBusy(false);
          self.apply(data, '');
        },
        fail: function (message, cached) {
          self.setBusy(false);
          if (cached) {
            self.apply(cached, message);
          } else {
            self.apply(null, message);
          }
        }
      });
    });
  },

  /* Rohdaten -> Anzeige */
  apply: function (data, warning) {
    var that = this;
    return util.guard('apply', function () {
      var prefs = api.getPrefs();
      var metric = prefs.metric !== false;
      var view = util.buildView(data, {
        metric: prefs.metric,
        lowLevel: CONFIG.LOW_LEVEL,
        staleMin: CONFIG.STALE_MIN,
        error: warning || ''
      });
      var d = data || {};
      that.view = view;

      /* ---- Karte 1: Uebersicht */
      that.animateLevel(view.ready && view.levelText !== '--' ? Math.round(view.level) : -1);

      if (view.rangeText !== '--') {
        var space = view.rangeText.lastIndexOf(' ');
        that.rangeNum = view.rangeText.substring(0, space);
        that.rangeUnit = view.rangeText.substring(space + 1);
      } else {
        that.rangeNum = '--';
        that.rangeUnit = '';
      }
      that.hasRange = that.rangeNum !== '--';
      var rd = digits(that.rangeNum);
      that.rangeD1 = rd === 1;
      that.rangeD2 = rd === 2;
      that.rangeD3 = rd === 3;

      /* Alter der letzten Meldung des Autos (nicht des Abrufs) */
      if (warning) {
        that.ageLine = warning;
        that.ageFoot = warning;
        that.ageColor = '#ff5252';
      } else {
        /* Wie die Opel-App: Zeit seit dem Abruf bei Opel ("aktualisiert").
           Wann das Auto selbst zuletzt gesendet hat, steht im Menue-Fuss. */
        var fetched = util.isNum(d.recv) ? Math.max(0, (Date.now() - d.recv) / 1000) : null;
        var fetchedText = fetched === null ? '' : (fetched < 90 ? 'gerade aktualisiert' : 'aktualisiert ' + util.ago(fetched));
        that.ageLine = view.ready ? fetchedText : '';
        that.ageFoot = view.ready ? 'Auto meldete ' + view.ageText : '';
        that.ageColor = '#6e6e6e';
      }
      that.odoLine = view.ready && view.odoText !== '--' ? view.odoText : '';

      /* ---- Stecker / Laden (Karte 1 und 2) */
      var state = view.charging ? 'chg' : (view.plugged ? 'on' : 'off');
      that.isCharging = view.charging;
      that.notCharging = !view.charging;
      that.plugIconS = IMG + 'plug_' + state + '_s.png';
      that.plugIconL = IMG + 'plug_' + state + '_l.png';
      that.plugColor = view.charging ? '#3ddc84' : (view.plugged ? '#f5a623' : '#8c8c8c');

      var kmh = util.isNum(d.kmh) && d.kmh > 0 ? d.kmh : null;
      var gain = kmh === null ? '--'
        : (metric ? '+' + Math.round(kmh) + ' km/h' : '+' + Math.round(kmh * 0.621371) + ' mi/h');
      var target = util.isNum(d.tgt) && d.tgt > 0 ? Math.round(d.tgt) + '%' : '--';

      if (!view.ready) {
        that.chargeHero = '--';
        that.statA = '--';
        that.statALabel = '';
        that.statB = '--';
        that.statBLabel = '';
      } else if (view.charging) {
        that.chargeHero = view.etaText ? 'noch ' + view.etaText : 'L\u00e4dt';
        that.statA = gain;
        that.statALabel = 'Zuwachs';
        that.statB = target;
        that.statBLabel = 'Ladeziel';
      } else {
        that.chargeHero = view.plugged ? 'Angesteckt' : 'Nicht verbunden';
        that.statA = view.levelText === '--' ? '--' : view.levelText + '%';
        that.statALabel = 'Akku';
        that.statB = view.rangeText;
        that.statBLabel = 'Reichweite';
      }

      /* ---- Karte 3: Fahrzeug */
      that.nameUpper = String(view.name || 'Opel').toUpperCase();
      if (d.lck === 1) {
        that.lockIcon = IMG + 'lock_closed.png';
        that.lockColor = '#3ddc84';
        that.lockText = 'Verriegelt';
      } else if (d.lck === 0) {
        that.lockIcon = IMG + 'lock_open.png';
        that.lockColor = '#ff5252';
        that.lockText = 'Offen';
      } else {
        that.lockIcon = IMG + 'lock_unknown.png';
        that.lockColor = '#8c8c8c';
        that.lockText = view.ready ? 'Unbekannt' : '--';
      }
      var open = util.isNum(d.opn) ? d.opn : 0;
      if (!view.ready || d.lck === -1) {
        that.doorsShort = '--';
      } else if (open === 0) {
        that.doorsShort = 'zu';
      } else {
        that.doorsShort = open + ' offen';
      }
      that.doorColor = view.doorsOpen ? '#ff5252' : '#ffffff';
      that.outsideShort = view.tempOutText;
      that.climateRow = view.ready ? (view.climateOn ? 'an' : 'aus') : '--';
      that.alertText = view.alerts.length ? view.alerts[0] : '';

      /* Beim Ladeende einmal vibrieren, solange die App offen ist. */
      if (that.lastCharging && !view.charging && view.ready) {
        that.buzz();
        that.toast('Ladevorgang beendet');
      }
      if (that.lastCharging !== view.charging) {
        that.lastCharging = view.charging;
        that.startTimer();
      }
    });
  },

  /*
   * Ring und Zahl vom angezeigten Wert zum Ziel hochzaehlen (~0,6 s).
   * Beim Start kommen oft zwei Anzeigen kurz hintereinander (Zwischenspeicher,
   * dann frisch vom Handy) - dasselbe Ziel darf die laufende Animation nicht
   * abbrechen, sonst bleibt "--" stehen.
   */
  animateLevel: function (target) {
    var that = this;
    return util.guard('animateLevel', function () {
      var self = that;
      if (target === that.shownLevel) {
        return;
      }
      that.stopAnim();
      that.shownLevel = target;
      if (target < 0) {
        that.ringNow = 0;
        that.setLevelText('--');
        return;
      }
      var from = util.isNum(that.ringNow) ? that.ringNow : 0;
      var steps = 18;
      var step = 0;
      that.animTimer = setInterval(function () {
        step++;
        /* weich auslaufen: 1 - (1 - t)^2; nie ueber das Ziel hinaus */
        var t = Math.min(1, step / steps);
        var eased = 1 - (1 - t) * (1 - t);
        var value = Math.round(from + (target - from) * eased);
        self.ringNow = Math.max(0, Math.min(100, value));
        self.setLevelText('' + value);
        if (step >= steps) {
          self.stopAnim();
        }
      }, 33);
      /* Sicherheitsnetz: Endwert steht spaetestens nach 1,5 s */
      setTimeout(function () {
        if (self.shownLevel === target) {
          self.stopAnim();
          self.ringNow = Math.max(0, Math.min(100, target));
          self.setLevelText('' + target);
        }
      }, 1500);
    });
  },

  stopAnim: function () {
    if (this.animTimer) {
      clearInterval(this.animTimer);
      this.animTimer = 0;
    }
  },

  setLevelText: function (text) {
    var n = digits(text);
    this.levelNow = text;
    this.hasLevel = text !== '--';
    this.levelD1 = n === 1;
    this.levelD2 = n === 2;
    this.levelD3 = n === 3;
  },

  /* ----------------------------------------------------------- Aktionen */

  forceRefresh: function () {
    var that = this;
    return util.guard('forceRefresh', function () {
      that.buzz();
      that.ageLine = 'aktualisiere ...';
      that.refresh(true);
    });
  },

  /* --------------------------------------------------------- Navigation */

  onSwipe: function (event) {
    this.page = event.index;
    this.markDots(event.index);
  },

  markDots: function (index) {
    this.dot0 = index === 0 ? DOT_ON : DOT_OFF;
    this.dot1 = index === 1 ? DOT_ON : DOT_OFF;
    this.dot2 = index === 2 ? DOT_ON : DOT_OFF;
    this.dot3 = index === 3 ? DOT_ON : DOT_OFF;
  },

  goDetail: function () {
    return util.guard('goDetail', function () {
      /* Lite-Wearables kennen nur router.replace - kein push, kein back. */
      router.replace({ uri: 'pages/detail/detail', params: {} });
    });
  },

  goSettings: function () {
    return util.guard('goSettings', function () {
      router.replace({ uri: 'pages/settings/settings', params: {} });
    });
  },

  /* ------------------------------------------------------------ Helfer */

  toast: function (message) {
    var that = this;
    return util.guard('toast', function () {
      var self = that;
      that.toastText = message;
      if (that.toastTimer) {
        clearTimeout(that.toastTimer);
      }
      that.toastTimer = setTimeout(function () {
        self.toastText = '';
        self.toastTimer = 0;
      }, 2500);
    });
  },

  buzz: function () {
    return util.guard('buzz', function () {
      if (api.getPrefs().haptics) {
        try {
          vibrator.vibrate({ mode: 'short' });
        } catch (e) {
          /* Geraet ohne Vibrationsmotor - ignorieren */
        }
      }
    });
  }
};
