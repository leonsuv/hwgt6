"""Statische Pruefung der Watch-App vor dem Bauen in DevEco Studio.

Prueft:
  1. JS-Syntax aller Dateien (benoetigt das Paket 'esprima', optional)
  2. ES5-Konformitaet - die Lite-Wearable-Engine kann kein let/const,
     keine Arrow-Funktionen, keine Template-Strings, keine Klassen
  3. HML-Dateien auf XML-Wohlgeformtheit
  4. JSON-Dateien (config.json, i18n, Ressourcen)
  5. config.js auf noch nicht eingetragene Platzhalter

Aufruf:  py tools/check_watchapp.py
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WATCH = ROOT / "watchapp"

VERBOTEN = {
    "ArrowFunctionExpression": "Arrow-Funktion (=>)",
    "TemplateLiteral": "Template-String (Backticks)",
    "ClassDeclaration": "class",
    "ClassExpression": "class",
    "SpreadElement": "Spread-Operator (...)",
    "RestElement": "Rest-Parameter (...)",
    "ForOfStatement": "for..of",
}

problems: list[str] = []
checked = 0


def note_ok(text: str) -> None:
    print("  ok    %s" % text)


def note_bad(text: str) -> None:
    problems.append(text)
    print("  FEHLER %s" % text)


def walk(node, callback) -> None:
    if isinstance(node, list):
        for item in node:
            walk(item, callback)
        return
    if not hasattr(node, "type"):
        return
    callback(node)
    for key in dir(node):
        if key.startswith("_") or key == "type":
            continue
        walk(getattr(node, key), callback)


def check_js() -> None:
    global checked
    print("JavaScript")
    try:
        import esprima                                   # type: ignore
    except ImportError:
        print("  uebersprungen - 'py -m pip install esprima' fuer die Syntaxpruefung")
        return
    for path in sorted(WATCH.rglob("*.js")):
        checked += 1
        source = path.read_text(encoding="utf-8")
        try:
            tree = esprima.parseModule(source)
        except Exception as exc:                          # noqa: BLE001
            note_bad("%s: %s" % (path.relative_to(ROOT), exc))
            continue
        found: list[str] = []

        def collect(node, found=found):
            if node.type in VERBOTEN:
                found.append(VERBOTEN[node.type])
            if node.type == "VariableDeclaration" and node.kind in ("let", "const"):
                found.append(node.kind)

        if any(ord(ch) > 127 for ch in source):
            # Umlaute/Symbole als Unicode-Escape schreiben - die alte
            # Lite-Wearable-Toolchain ist bei UTF-8-Quelltext unzuverlaessig.
            found.append("Sonderzeichen (als " + chr(92) + "uXXXX escapen)")
        walk(tree.body, collect)
        if found:
            note_bad("%s: nicht ES5 -> %s" % (path.relative_to(ROOT), ", ".join(sorted(set(found)))))
        else:
            note_ok(str(path.relative_to(ROOT)))


def check_hml() -> None:
    global checked
    print("HML")
    for path in sorted(WATCH.rglob("*.hml")):
        checked += 1
        try:
            ET.fromstring(path.read_text(encoding="utf-8"))
            note_ok(str(path.relative_to(ROOT)))
        except ET.ParseError as exc:
            note_bad("%s: %s" % (path.relative_to(ROOT), exc))


def check_json() -> None:
    global checked
    print("JSON")
    for path in sorted(WATCH.rglob("*.json")):
        checked += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
            note_ok(str(path.relative_to(ROOT)))
        except ValueError as exc:
            note_bad("%s: %s" % (path.relative_to(ROOT), exc))


def check_config() -> None:
    print("Konfiguration")
    path = WATCH / "entry/src/main/js/default/common/config.js"
    if not path.exists():
        note_bad("config.js fehlt")
        return
    source = path.read_text(encoding="utf-8")
    # Die Uhr spricht nur per Bluetooth-P2P mit dem Handy - dafuer zaehlen
    # Paketname und Fingerabdruck der Gegenstelle. TOKEN/BASE_URL sind nur
    # noch fuer die HTTP-Testschnittstelle der Android-App.
    for key in ("PHONE_PACKAGE", "PHONE_FINGERPRINT"):
        m = re.search(key + r":\s*'([^']*)'", source)
        if not m or not m.group(1):
            note_bad("config.js: %s fehlt oder ist leer" % key)
        else:
            note_ok("%s gesetzt" % key)
    if "HIER_TOKEN_EINTRAGEN" in source:
        print("  hinweis TOKEN ist der Platzhalter (nur fuer den HTTP-Test der Android-App)")
    match = re.search(r"BASE_URL:\s*'([^']*)'", source)
    base = match.group(1) if match else ""
    if not base.startswith("http"):
        note_bad("config.js: BASE_URL ist keine URL")
    elif base.endswith("/"):
        note_bad("config.js: BASE_URL darf nicht auf / enden")
    elif base == "http://192.168.1.50:8787":
        print("  hinweis BASE_URL ist noch die Beispieladresse")
        note_ok("BASE_URL formal gueltig")
    else:
        note_ok("BASE_URL = %s" % base)


def check_pages() -> None:
    """Jede in config.json gelistete Seite muss hml/css/js haben."""
    print("Seiten")
    cfg_path = WATCH / "entry/src/main/config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        pages = cfg["module"]["js"][0]["pages"]
    except (OSError, ValueError, KeyError, IndexError) as exc:
        note_bad("config.json unlesbar: %s" % exc)
        return
    base = WATCH / "entry/src/main/js/default"
    for page in pages:
        missing = [
            suffix
            for suffix in (".hml", ".css", ".js")
            if not (base / (page + suffix)).exists()
        ]
        if missing:
            note_bad("%s: fehlt %s" % (page, ", ".join(missing)))
        else:
            note_ok(page)


def main() -> int:
    print("Pruefe Watch-App in %s\n" % WATCH)
    check_js()
    print()
    check_hml()
    print()
    check_json()
    print()
    check_pages()
    print()
    check_config()
    print("\n" + "-" * 60)
    if problems:
        print("%d Problem(e):" % len(problems))
        for item in problems:
            print("  - %s" % item)
        return 1
    print("Alles in Ordnung (%d Dateien geprueft)." % checked)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
