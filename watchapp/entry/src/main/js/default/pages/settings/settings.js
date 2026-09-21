import router from '@system.router';
import api from '../../common/api.js';
import CONFIG from '../../common/config.js';

var STEPS = [30, 60, 120, 300, 600];

export default {
  data: {
    refreshText: '60 s',
    unitText: 'km / \u00b0C',
    hapticText: 'an',
    hostText: '--',
    testText: 'noch nicht geprueft',
    testClass: 'result',
    versionText: 'OpelWatch 1.0.0'
  },

  onInit: function () {
    var self = this;
    this.hostText = this.shortHost();
    api.loadPrefs(function (prefs) {
      self.show(prefs);
    });
  },

  show: function (prefs) {
    this.refreshText = prefs.refresh_s + ' s';
    this.unitText = prefs.metric === false ? 'mi / \u00b0F' : 'km / \u00b0C';
    this.hapticText = prefs.haptics === false ? 'aus' : 'an';
  },

  /* Nur Host und Port anzeigen - das Token gehoert nicht auf den Bildschirm. */
  shortHost: function () {
    var url = CONFIG.BASE_URL || '';
    var text = url.replace('https://', '').replace('http://', '');
    if (text.length > 22) {
      text = text.substring(0, 21) + '\u2026';
    }
    return text || 'nicht gesetzt';
  },

  cycleRefresh: function () {
    var self = this;
    var current = api.getPrefs().refresh_s;
    var index = 0;
    for (var i = 0; i < STEPS.length; i++) {
      if (STEPS[i] === current) {
        index = i;
      }
    }
    var next = STEPS[(index + 1) % STEPS.length];
    api.savePrefs({ refresh_s: next }, function (prefs) {
      self.show(prefs);
    });
  },

  toggleUnits: function () {
    var self = this;
    var metric = api.getPrefs().metric === false;
    api.savePrefs({ metric: metric }, function (prefs) {
      self.show(prefs);
    });
  },

  toggleHaptics: function () {
    var self = this;
    var haptics = api.getPrefs().haptics === false;
    api.savePrefs({ haptics: haptics }, function (prefs) {
      self.show(prefs);
    });
  },

  test: function () {
    var self = this;
    this.testText = 'pruefe ...';
    this.testClass = 'result';
    api.ping(function (ok, message) {
      self.testText = message;
      self.testClass = ok ? 'result-ok' : 'result-bad';
    });
  },

  back: function () {
    router.back();
  }
};
