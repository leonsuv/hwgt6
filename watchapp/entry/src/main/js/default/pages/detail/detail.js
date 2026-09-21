import router from '@system.router';
import api from '../../common/api.js';
import util from '../../common/util.js';
import CONFIG from '../../common/config.js';

export default {
  data: {
    name: 'Fahrzeug',
    rows: [],
    hasAlerts: false,
    alertText: ''
  },

  onInit: function () {
    var self = this;
    /* Detailseite arbeitet bewusst nur mit dem Zwischenspeicher - kein
       zweiter Netzabruf, wenn die Uhr gerade erst geladen hat. */
    api.readCache(function (cached) {
      self.render(cached);
    });
  },

  onShow: function () {
    var self = this;
    api.getState({
      force: false,
      success: function (data) {
        self.render(data);
      },
      fail: function () {
        /* stiller Fehler - die Karten aus dem Cache bleiben stehen */
      }
    });
  },

  render: function (data) {
    if (!data) {
      this.rows = [{ label: 'Status', value: 'keine Daten' }];
      return;
    }
    var prefs = api.getPrefs();
    var view = util.buildView(data, {
      metric: prefs.metric,
      lowLevel: CONFIG.LOW_LEVEL,
      staleMin: CONFIG.STALE_MIN
    });

    var rows = [];
    rows.push({ label: 'Ladestand', value: view.levelText + ' %' });
    rows.push({ label: 'Reichweite', value: view.rangeText });
    if (view.hasSecondary) {
      rows.push({ label: 'Zweitenergie', value: view.secondaryText });
    }
    rows.push({ label: 'Laden', value: view.charging ? 'aktiv' : (view.plugged ? 'Stecker' : 'nein') });
    if (view.etaText) {
      rows.push({ label: 'Restzeit', value: view.etaText });
    }
    if (view.targetText) {
      rows.push({ label: 'Ladeziel', value: view.targetText });
    }
    rows.push({ label: 'Kilometer', value: view.odoText });
    rows.push({ label: 'Verriegelt', value: view.lockText });
    rows.push({ label: 'Tueren', value: view.doorsText });
    rows.push({ label: 'Klima', value: view.climateText });
    rows.push({ label: 'Innen', value: view.tempInText });
    rows.push({ label: 'Aussen', value: view.tempOutText });
    if (view.hasPos) {
      rows.push({ label: 'Position', value: view.posText });
    }
    rows.push({ label: 'Stand', value: view.ageText });
    if (view.source) {
      rows.push({ label: 'Quelle', value: view.source });
    }

    this.name = view.name;
    this.rows = rows;
    this.hasAlerts = view.hasAlerts;
    this.alertText = view.alerts.join(' / ');
  },

  back: function () {
    router.back();
  }
};
