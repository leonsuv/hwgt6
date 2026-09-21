import router from '@system.router';
import vibrator from '@system.vibrator';
import api from '../../common/api.js';
import util from '../../common/util.js';
import CONFIG from '../../common/config.js';

export default {
  data: {
    view: util.buildView(null, {}),
    page: 0,
    busy: false,
    bannerText: '',
    toastText: '',
    ageClass: 'age',
    lockClass: 'row-value',
    doorClass: 'row-value',
    tempsText: '--',
    alertText: '',
    sourceText: '',
    climateBtnText: 'Vorklimatisierung',
    showActions: CONFIG.SHOW_ACTIONS,
    timer: 0,
    toastTimer: 0,
    lastCharging: false
  },

  /* ------------------------------------------------------- Lebenszyklus */

  onInit: function () {
    var self = this;
    api.loadPrefs(function () {
      api.readCache(function (cached) {
        if (cached) {
          self.apply(cached, 'Zwischenspeicher');
        }
      });
    });
  },

  onShow: function () {
    this.refresh(false);
    this.startTimer();
  },

  onHide: function () {
    this.stopTimer();
  },

  onDestroy: function () {
    this.stopTimer();
  },

  startTimer: function () {
    var self = this;
    this.stopTimer();
    var seconds = api.getPrefs().refresh_s || CONFIG.REFRESH_S;
    if (this.lastCharging && CONFIG.REFRESH_CHARGING_S < seconds) {
      seconds = CONFIG.REFRESH_CHARGING_S;
    }
    this.timer = setInterval(function () {
      self.refresh(false);
    }, Math.max(15, seconds) * 1000);
  },

  stopTimer: function () {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = 0;
    }
  },

  /* ------------------------------------------------------------- Daten */

  refresh: function (force) {
    var self = this;
    if (this.busy) {
      return;
    }
    this.busy = true;
    if (force) {
      this.bannerText = 'aktualisiere ...';
    }
    api.getState({
      force: force,
      success: function (data) {
        self.busy = false;
        self.apply(data, '');
      },
      fail: function (message, cached) {
        self.busy = false;
        if (cached) {
          self.apply(cached, message);
        } else {
          self.bannerText = message;
          self.view = util.buildView(null, { error: message });
        }
      }
    });
  },

  /* Rohdaten -> Anzeige */
  apply: function (data, warning) {
    var prefs = api.getPrefs();
    var view = util.buildView(data, {
      metric: prefs.metric,
      lowLevel: CONFIG.LOW_LEVEL,
      staleMin: CONFIG.STALE_MIN,
      error: warning || ''
    });

    /* Zusammengesetzte Texte hier bauen - die HML-Bindung bleibt simpel. */
    view.statusFull = view.statusIcon ? view.statusIcon + ' ' + view.statusLine : view.statusLine;

    this.view = view;
    this.ageClass = view.stale ? 'age-stale' : 'age';
    this.lockClass = view.lockOk ? 'row-value-ok' : (view.ready ? 'row-value-warn' : 'row-value');
    this.doorClass = view.doorsOpen ? 'row-value-warn' : 'row-value';
    this.tempsText = view.tempInText + '  /  ' + view.tempOutText;
    this.alertText = view.alerts.length ? view.alerts[0] : '';
    this.sourceText = view.source ? 'Quelle: ' + view.source : '';
    this.climateBtnText = view.climateOn ? 'Klima stoppen' : 'Vorklimatisierung';
    this.bannerText = warning ? warning : '';

    /* Beim Ladeende einmal vibrieren, solange die App offen ist. */
    if (this.lastCharging && !view.charging && view.ready) {
      this.buzz();
      this.toast('Ladevorgang beendet');
    }
    if (this.lastCharging !== view.charging) {
      this.lastCharging = view.charging;
      this.startTimer();
    }
  },

  /* ----------------------------------------------------------- Aktionen */

  forceRefresh: function () {
    this.buzz();
    this.toast('Fahrzeug wird abgefragt ...');
    this.refresh(true);
  },

  precondition: function () {
    var self = this;
    var activate = this.view.climateOn ? 0 : 1;
    this.buzz();
    this.toast(activate ? 'Klima startet ...' : 'Klima stoppt ...');
    api.command('preconditioning', { activate: activate, minutes: 10 }, function (ok, message) {
      self.toast(message);
      self.refresh(true);
    });
  },

  wakeup: function () {
    var self = this;
    this.buzz();
    this.toast('Weckruf ...');
    api.command('wakeup', {}, function (ok, message) {
      self.toast(message);
      self.refresh(true);
    });
  },

  /* --------------------------------------------------------- Navigation */

  onSwipe: function (event) {
    this.page = event.index;
  },

  goDetail: function () {
    router.push({ uri: 'pages/detail/detail' });
  },

  goSettings: function () {
    router.push({ uri: 'pages/settings/settings' });
  },

  /* ------------------------------------------------------------ Helfer */

  toast: function (message) {
    var self = this;
    this.toastText = message;
    if (this.toastTimer) {
      clearTimeout(this.toastTimer);
    }
    this.toastTimer = setTimeout(function () {
      self.toastText = '';
      self.toastTimer = 0;
    }, 2500);
  },

  buzz: function () {
    if (api.getPrefs().haptics) {
      try {
        vibrator.vibrate({ mode: 'short' });
      } catch (e) {
        /* Geraet ohne Vibrationsmotor - ignorieren */
      }
    }
  }
};
