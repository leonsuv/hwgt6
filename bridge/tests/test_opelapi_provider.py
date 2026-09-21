"""Testet die Abbildung von opelapi.VehicleStatus auf das Bridge-Modell.

Laeuft nur, wenn die Bibliothek 'opelapi' importierbar ist (ohne sie faellt der
Test aus, statt rot zu werden). Bewusst wird das echte Modell der Bibliothek
benutzt und nicht nachgebaut - so faellt auf, wenn sich dort etwas aendert.

    py -m pip install -e <Pfad zu opelapi-main>
    py -m pytest tests/test_opelapi_provider.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

models = pytest.importorskip(
    "opelapi.models", reason="Bibliothek 'opelapi' nicht installiert"
)

from opelbridge.providers.opelapi_provider import OpelApiProvider    # noqa: E402

# Antwort von /connectedcar/v4/user/vehicles/{id}/status in der Form, die die
# App liefert: 'energies' mit verschachteltem extension.electric.charging.
STATUS_RAW = {
    "createdAt": "2026-03-01T08:30:00Z",
    "energies": [
        {"type": "Fuel", "level": 0, "updatedAt": "2026-03-01T08:30:00Z"},
        {
            "type": "Electric",
            "level": 62,
            "autonomy": 209,
            "updatedAt": "2026-03-01T08:30:00Z",
            "extension": {
                "electric": {
                    "battery": {
                        "load": {"capacity": 46000, "residual": 28500},
                        "health": {"capacity": 95, "resistance": 100},
                    },
                    "charging": {
                        "plugged": True,
                        "status": "InProgress",
                        "remainingTime": "PT1H25M",
                        "chargingRate": 38,
                        "chargingMode": "Slow",
                        "nextDelayedTime": "PT22H0M",
                    },
                }
            },
        },
    ],
    "odometer": {"createdAt": "2026-03-01T08:30:00Z", "mileage": 24310.7},
    "doorsState": {"lockedStates": ["Locked"], "opened": []},
    "preconditionning": {"airConditioning": {"status": "Disabled"}},
    "environment": {"air": {"temp": 11.5}, "luminosity": {"day": True}},
    "lastPosition": {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [6.7735, 51.2277, 38]},
        "properties": {"heading": 180, "updatedAt": "2026-03-01T08:25:00Z"},
    },
    "kinetic": {"moving": False, "speed": 0},
    "privacy": {"state": "None"},
    "ignition": {"type": "Stop"},
}


class FakeCar:
    vin = "W0VZZZ1234567890"
    label = "Corsa-e"
    id = "1234567890"


def build(raw):
    provider = OpelApiProvider({})
    provider._label = "Corsa-e"
    return provider._to_state(models.VehicleStatus(raw), FakeCar())


def test_laden_wird_vollstaendig_uebernommen():
    state = build(STATUS_RAW)
    assert state.source == "opelapi"
    assert state.vin == "W0VZZZ1234567890"
    assert state.name == "Corsa-e"
    assert state.energy.type == "electric"
    assert state.energy.level == 62
    assert state.energy.range_km == 209
    assert state.energy.charging is True
    assert state.energy.plugged is True
    assert state.energy.charge_remaining_min == 85
    assert state.energy.charge_rate_kmh == 38
    assert state.energy.charge_kw is None          # kW liefert die API nicht
    assert state.energy.charge_mode == "slow"
    assert state.odometer_km == 24310.7
    assert state.doors.locked is True
    assert state.climate.active is False
    assert state.climate.outside_c == 11.5
    assert round(state.position.lat, 4) == 51.2277
    assert round(state.position.lon, 4) == 6.7735
    assert state.position.heading == 180
    assert state.alerts == []


def test_uhr_nutzlast_bleibt_klein():
    import json

    payload = build(STATUS_RAW).to_watch()
    assert payload["lvl"] == 62 and payload["chg"] == 1 and payload["kmh"] == 38
    assert len(json.dumps(payload)) < 700


def test_offene_tueren_und_privatmodus():
    raw = dict(STATUS_RAW)
    raw["doorsState"] = {"lockedStates": ["Unlocked"], "opened": ["Driver", "Trunk"]}
    raw["privacy"] = {"state": "Full"}
    raw["kinetic"] = {"moving": True, "speed": 43}
    state = build(raw)
    assert state.doors.locked is False
    assert sorted(state.doors.open) == ["fl", "trunk"]
    assert "Privatmodus aktiv - keine Position" in state.alerts
    assert "Fahrzeug faehrt" in state.alerts


def test_hybrid_beide_energien():
    raw = dict(STATUS_RAW)
    raw["energies"] = [
        {"type": "Fuel", "level": 55, "autonomy": 430},
        {
            "type": "Electric",
            "level": 40,
            "autonomy": 38,
            "extension": {"electric": {"charging": {"status": "Stopped", "plugged": True}}},
        },
    ]
    state = build(raw)
    assert state.energy.type == "hybrid"
    assert state.energy.level == 40
    assert state.energy.secondary_level == 55
    assert state.energy.secondary_range_km == 430
    assert state.energy.charging is False


def test_leerer_status_wirft_nicht():
    """Die API antwortet mit {}, solange das Auto noch nichts gemeldet hat."""
    state = build({})
    assert state.energy.type == "unknown"
    assert state.energy.level is None
    assert state.doors.locked is None
    assert state.to_watch()["lvl"] is None


def test_schlechte_batteriegesundheit_wird_gemeldet():
    raw = dict(STATUS_RAW)
    energies = [dict(item) for item in STATUS_RAW["energies"]]
    energies[1] = dict(energies[1])
    energies[1]["extension"] = {
        "electric": {
            "battery": {"health": {"capacity": 74}},
            "charging": {"status": "Disconnected", "plugged": False},
        }
    }
    raw["energies"] = energies
    state = build(raw)
    assert any("Batteriegesundheit" in alert for alert in state.alerts)
