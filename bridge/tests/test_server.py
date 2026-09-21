"""End-to-End-Tests des Bridge-Servers (echter Socket, echter HTTP-Verkehr)."""
import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opelbridge.config import Config                      # noqa: E402
from opelbridge.server import Handler, VehicleService     # noqa: E402

TOKEN = "geheim-test-token"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def bridge(tmp_path_factory):
    cfg = Config()
    cfg.provider = "mock"
    cfg.token = TOKEN
    cfg.allow_commands = True
    cfg.cache_ttl_s = 0
    cfg.port = free_port()
    cfg._path = tmp_path_factory.mktemp("cfg") / "config.json"

    service = VehicleService(cfg)
    service.cache._path = tmp_path_factory.mktemp("state") / "state.json"
    handler = type("TestHandler", (Handler,), {"service": service, "config": cfg})
    httpd = ThreadingHTTPServer(("127.0.0.1", cfg.port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    yield "http://127.0.0.1:%d" % cfg.port
    httpd.shutdown()
    httpd.server_close()
    service.stop()


def get(url, token=TOKEN, method="GET"):
    request = urllib.request.Request(url, method=method)
    if token:
        request.add_header("X-Token", token)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_health_braucht_kein_token(bridge):
    status, body = get(bridge + "/health", token=None)
    assert status == 200 and body["ok"] is True


def test_watch_liefert_kompaktes_json(bridge):
    status, body = get(bridge + "/api/v1/watch")
    assert status == 200
    for key in ("v", "ts", "nm", "lvl", "rng", "chg", "lck", "odo", "src"):
        assert key in body, "Feld %s fehlt" % key
    assert body["src"] == "mock"
    assert 0 <= body["lvl"] <= 100
    # Uhrnutzlast muss klein bleiben - die Uhr parst das auf einem Mikrocontroller
    assert len(json.dumps(body)) < 700


def test_state_liefert_volles_schema(bridge):
    _status, body = get(bridge + "/api/v1/state")
    assert body["v"] == 1
    assert body["vehicle"]["brand"] == "Opel"
    assert "energy" in body and "doors" in body and "position" in body


def test_falsches_token_wird_abgelehnt(bridge):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(bridge + "/api/v1/watch", token="falsch")
    assert exc.value.code == 401


def test_fehlendes_token_wird_abgelehnt(bridge):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(bridge + "/api/v1/watch", token=None)
    assert exc.value.code == 401


def test_token_auch_als_query_parameter(bridge):
    status, _body = get(bridge + "/api/v1/watch?t=" + TOKEN, token=None)
    assert status == 200


def test_unbekannte_route_gibt_404(bridge):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(bridge + "/api/v1/gibtsnicht")
    assert exc.value.code == 404


def test_befehl_schaltet_klima(bridge):
    _status, before = get(bridge + "/api/v1/watch?force=1")
    assert before["clm"] == 0
    _status, result = get(
        bridge + "/api/v1/command/preconditioning?minutes=5", method="POST"
    )
    assert result["ok"] is True
    _status, after = get(bridge + "/api/v1/watch?force=1")
    assert after["clm"] == 1


def test_unbekannter_befehl_gibt_501(bridge):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(bridge + "/api/v1/command/selbstzerstoerung", method="POST")
    assert exc.value.code == 501


def test_info_verraet_kein_token(bridge):
    _status, body = get(bridge + "/api/v1/info")
    assert TOKEN not in json.dumps(body)
    assert body["config"]["provider"] == "mock"


def test_preview_util_wird_ausgeliefert(bridge):
    with urllib.request.urlopen(bridge + "/preview/util.js", timeout=10) as response:
        source = response.read().decode("utf-8")
    assert "buildView" in source
    assert "export default" not in source          # Browser kann kein ES-Modul-Export
    assert "window.UTIL" in source
