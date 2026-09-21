# AGENTS.md

Das Briefing für KI-Assistenten steht in **[CLAUDE.md](CLAUDE.md)** — dort
komplett lesen, bevor irgendetwas geändert wird.

Die drei Punkte, die man sonst garantiert falsch macht:

1. **Die Watch GT6 hat für Apps kein eigenes IP-Networking.** Ihre Anfragen
   laufen durch das gekoppelte Telefon (Huawei Health). `127.0.0.1` aus Sicht
   der Uhr ist das Telefon.
2. **Die Uhr-App muss ES5 und reines ASCII sein** (JerryScript). Kein `let`,
   keine Arrow-Funktionen, Sonderzeichen als `\uXXXX`.
   Prüfen mit `python3 tools/check_watchapp.py`.
3. **Das JSON-Schema der Uhr ist an drei Stellen implementiert**
   (`bridge/opelbridge/model.py`, `androidapp/.../Normalize.kt`,
   `watchapp/.../util.js`). Immer alle drei ändern, dann
   `cd bridge && python3 -m pytest tests -q`.
