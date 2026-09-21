"""Haelt Android-Bruecke und Python-Bridge auf demselben Datenformat.

Die Uhr-App kennt nur ein Schema. Wenn die Android-App andere Schluessel
schreibt als die Bridge, zeigt die Uhr stillschweigend Luecken - genau das
faengt dieser Test ab, ohne dass dafuer Android gebaut werden muss.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opelbridge.model import VehicleState                    # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
NORMALIZE_KT = ROOT / "androidapp/app/src/main/java/de/saigak/opelbridge/Normalize.kt"
WATCH_SERVER_KT = ROOT / "androidapp/app/src/main/java/de/saigak/opelbridge/WatchServer.kt"
UTIL_JS = ROOT / "watchapp/entry/src/main/js/default/common/util.js"

pytestmark = pytest.mark.skipif(
    not NORMALIZE_KT.exists(), reason="androidapp/ nicht vorhanden"
)

# Schluessel, die nur die Bridge kennt bzw. nur situativ auftauchen
BRIDGE_ONLY = {"cache_s", "err"}
ANDROID_ONLY = {"cache_s", "err"}


def kotlin_keys() -> set:
    source = NORMALIZE_KT.read_text(encoding="utf-8")
    body = source.split("fun toWatchPayload", 1)[1]
    body = body.split("fun refreshAge", 1)[0]
    return set(re.findall(r'out\.put\("([a-z0-9_]+)"', body))


def python_keys() -> set:
    return set(VehicleState().to_watch().keys())


def test_android_liefert_alle_schluessel_der_bridge():
    missing = python_keys() - kotlin_keys() - BRIDGE_ONLY
    assert not missing, "Android-App schreibt diese Felder nicht: %s" % sorted(missing)


def test_android_erfindet_keine_schluessel():
    extra = kotlin_keys() - python_keys() - ANDROID_ONLY
    assert not extra, "Android-App schreibt unbekannte Felder: %s" % sorted(extra)


def test_uhr_liest_nur_bekannte_felder():
    """Jedes data.<feld> in util.js muss es im Schema wirklich geben."""
    source = UTIL_JS.read_text(encoding="utf-8")
    used = set(re.findall(r"\bdata\.([a-z0-9_]+)", source))
    known = python_keys() | BRIDGE_ONLY
    unknown = used - known
    assert not unknown, "util.js liest unbekannte Felder: %s" % sorted(unknown)


def test_android_server_bietet_dieselben_endpunkte():
    source = WATCH_SERVER_KT.read_text(encoding="utf-8")
    for endpoint in ("/api/v1/watch", "/api/v1/state", "/api/v1/info", "/health"):
        assert endpoint in source, "Android-Server kennt %s nicht" % endpoint
