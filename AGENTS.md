# AGENTS.md

Das Briefing für KI-Assistenten steht in **[CLAUDE.md](CLAUDE.md)** — dort
komplett lesen, bevor irgendetwas geändert wird.

Die drei Punkte, die man sonst garantiert falsch macht:

1. **Die Watch GT6 hat für Apps gar keinen Netzzugang.** `@system.fetch`
   scheitert immer. Daten kommen per Bluetooth-P2P von **Gadgetbridge (opel)**
   (`gadgetbridge/hwgt6-opel.patch`), das sie per ContentProvider bei der
   Opel Bridge (`androidapp/`) holt — siehe `watchapp/.../p2p.js`, `api.js`.
2. **Die Uhr-App muss ES5 und reines ASCII sein** (JerryScript). Kein `let`,
   keine Arrow-Funktionen, Sonderzeichen als `\uXXXX`.
   Prüfen mit `python3 tools/check_watchapp.py`.
3. **Das JSON-Schema der Uhr ist an drei Stellen implementiert**
   (`bridge/opelbridge/model.py`, `androidapp/.../Normalize.kt`,
   `watchapp/.../util.js`). Immer alle drei ändern, dann
   `cd bridge && python3 -m pytest tests -q`.
