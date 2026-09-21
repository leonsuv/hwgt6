import api from './common/api.js';

export default {
  /* Global erreichbar ueber this.$app.$def */
  lastData: null,
  lastError: '',

  onCreate: function () {
    console.info('OpelWatch: gestartet');
    api.loadPrefs(function () {
      console.info('OpelWatch: Einstellungen geladen');
    });
  },

  onDestroy: function () {
    console.info('OpelWatch: beendet');
  },

  setData: function (data) {
    this.lastData = data;
    this.lastError = '';
  },

  setError: function (message) {
    this.lastError = message || '';
  }
};
