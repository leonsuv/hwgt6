"""Testet den psacc-Provider gegen einen nachgebauten psa_car_controller."""
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opelbridge.providers.psacc import PsaccProvider     # noqa: E402
from opelbridge.providers.base import ProviderError      # noqa: E402

VEHICLES = [{"vin": "VR3TESTVIN000001", "id": "1234567890", "label": "Corsa-e"}]

STATUS = {
    "energy": [
        {
            "type": "Electric",
            "level": 77,
            "autonomy": 260,
            "updated_at": "2026-03-01T07:00:00Z",
            "charging": {
                "plugged": True,
                "status": "InProgress",
                "remaining_time": "PT0H35M",
                "charging_rate": 11,
                "charging_mode": "Quick",
            },
        }
    ],
    "timed_odometer": {"mileage": 18422.0},
    "doors_state": {"locked_states": ["Locked"], "opened": []},
    "environment": {"air": {"temp": 6.5}},
    "last_position": {
        "geometry": {"coordinates": [8.6821, 50.1109]},
        "properties": {"updated_at": "2026-03-01T06:55:00Z", "heading": 12},
    },
    "created_at": "2026-03-01T07:00:00Z",
}

CALLS = []


class StubHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        CALLS.append(self.path)
        if self.path.startswith("/get_vehicles"):
            body = json.dumps({"success": True, "vehicles": VEHICLES})
        elif self.path.startswith("/get_vehicleinfo/"):
            body = json.dumps(STATUS)
        elif self.path.startswith("/preconditioning/") or self.path.startswith("/wakeup/"):
            body = json.dumps({"success": True})
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture(scope="module")
def stub():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    httpd = ThreadingHTTPServer(("127.0.0.1", port), StubHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.15)
    yield "http://127.0.0.1:%d" % port
    httpd.shutdown()
    httpd.server_close()


def test_fetch_normalisiert_psacc_daten(stub):
    provider = PsaccProvider({"base_url": stub})
    state = provider.fetch()
    assert state.vin == "VR3TESTVIN000001"
    assert state.name == "Corsa-e"
    assert state.source == "psacc"
    assert state.energy.level == 77
    assert state.energy.range_km == 260
    assert state.energy.charging is True
    assert state.energy.charge_remaining_min == 35
    assert state.energy.charge_rate_kmh == 11.0    # chargingRate = km/h Reichweitenzuwachs
    assert state.energy.charge_kw is None          # kW liefert die API nicht
    assert state.odometer_km == 18422.0
    assert state.doors.locked is True
    assert round(state.position.lon, 4) == 8.6821


def test_watch_json_ist_klein_und_vollstaendig(stub):
    state = PsaccProvider({"base_url": stub}).fetch()
    payload = state.to_watch()
    assert payload["lvl"] == 77 and payload["chg"] == 1 and payload["lck"] == 1
    assert len(json.dumps(payload)) < 500


def test_fahrzeugliste_wird_nur_einmal_geholt(stub):
    """Pro Poll-Zyklus soll genau ein Statusabruf laufen, nicht zwei Requests."""
    CALLS.clear()
    provider = PsaccProvider({"base_url": stub}, vin="VR3TESTVIN000001")
    provider.fetch()
    provider.fetch()
    provider.fetch()
    listen = [call for call in CALLS if call.startswith("/get_vehicles")]
    status = [call for call in CALLS if call.startswith("/get_vehicleinfo/")]
    assert len(listen) <= 1, "Fahrzeugliste wird bei jedem Abruf neu geholt"
    assert len(status) == 3


def test_vorgegebener_name_spart_die_fahrzeugliste(stub):
    CALLS.clear()
    provider = PsaccProvider({"base_url": stub, "name": "Mein Corsa"}, vin="VR3TESTVIN000001")
    state = provider.fetch()
    assert state.name == "Mein Corsa"
    assert not any(call.startswith("/get_vehicles") for call in CALLS)


def test_befehl_wird_abgesetzt(stub):
    provider = PsaccProvider({"base_url": stub}, vin="VR3TESTVIN000001")
    result = provider.command("preconditioning", {"activate": 1})
    assert result["ok"] is True
    assert any(call.startswith("/preconditioning/VR3TESTVIN000001/1") for call in CALLS)


def test_server_nicht_erreichbar_gibt_klaren_fehler():
    provider = PsaccProvider({"base_url": "http://127.0.0.1:1", "timeout_s": 1})
    with pytest.raises(ProviderError) as exc:
        provider.fetch()
    assert "nicht erreichbar" in str(exc.value)
