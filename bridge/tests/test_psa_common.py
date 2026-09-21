"""Tests der Normalisierung von PSA-/Stellantis-Statusdaten."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opelbridge.providers.psa_common import (          # noqa: E402
    normalize_status,
    parse_duration_min,
    parse_iso,
    pick,
)

# Realistische Antwort der Stellantis-API (camelCase) - Corsa-e am Lader
CAMEL = {
    "createdAt": "2026-03-01T08:30:00Z",
    "lastPosition": {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [6.7735, 51.2277, 38]},
        "properties": {"createdAt": "2026-03-01T08:25:00Z", "heading": 180, "type": "Acquire"},
    },
    "preconditionning": {
        "airConditioning": {"updatedAt": "2026-03-01T08:30:00Z", "status": "Disabled"}
    },
    "energy": [
        {"createdAt": "2026-03-01T08:30:00Z", "type": "Fuel", "level": 0},
        {
            "createdAt": "2026-03-01T08:30:00Z",
            "type": "Electric",
            "level": 62,
            "autonomy": 209,
            "charging": {
                "plugged": True,
                "status": "InProgress",
                "remainingTime": "PT1H25M",
                "chargingRate": 22,
                "chargingMode": "Slow",
                "nextDelayedTime": "PT22H0M",
            },
        },
    ],
    "battery": {"voltage": 398.0, "current": 18.6, "createdAt": "2026-03-01T08:30:00Z"},
    "odometer": {"createdAt": "2026-03-01T08:30:00Z", "mileage": 24310.7},
    "environment": {"air": {"createdAt": "2026-03-01T08:30:00Z", "temp": 11.5}},
    "doorsState": {
        "createdAt": "2026-03-01T08:30:00Z",
        "lockedStates": ["Locked"],
        "opened": [],
    },
}

# Gleiche Daten, wie psa_car_controller sie liefert (snake_case), Auto offen
SNAKE = {
    "created_at": "2026-03-01T08:30:00Z",
    "last_position": {
        "geometry": {"coordinates": [6.7735, 51.2277]},
        "properties": {"updated_at": "2026-03-01T08:25:00Z", "heading": 90},
    },
    "preconditionning": {"air_conditioning": {"status": "Enabled"}},
    "energy": [
        {
            "type": "Electric",
            "level": 18,
            "autonomy": 54,
            "updated_at": "2026-03-01T08:30:00Z",
            "charging": {"plugged": False, "status": "Disconnected", "charging_mode": "No"},
        }
    ],
    "timed_odometer": {"mileage": 24310.7},
    "environment": {"air": {"temp": -3.0}},
    "doors_state": {"locked_states": ["Unlocked"], "opened": ["FrontLeft", "Trunk"]},
}


def test_pick_findet_beide_schreibweisen():
    assert pick({"lockedStates": [1]}, "locked_states") == [1]
    assert pick({"locked_states": [1]}, "lockedStates") == [1]
    assert pick({}, "fehlt", default="x") == "x"


def test_parse_iso():
    expected = int(datetime(2026, 3, 1, 8, 30, tzinfo=timezone.utc).timestamp())
    assert parse_iso("2026-03-01T08:30:00Z") == expected
    assert parse_iso("2026-03-01T08:30:00.123456Z") == expected
    assert parse_iso("2026-03-01T09:30:00+01:00") == expected
    assert parse_iso("quatsch") is None
    assert parse_iso(None) is None


def test_parse_duration():
    assert parse_duration_min("PT1H25M") == 85
    assert parse_duration_min("PT0S") == 0
    assert parse_duration_min("PT45M") == 45
    assert parse_duration_min("P1DT2H") == 1560
    assert parse_duration_min(30) == 30
    assert parse_duration_min("keine") is None


def test_camel_laden():
    state = normalize_status(CAMEL, vin="VIN1", name="Corsa-e", source="stellantis")
    assert state.energy.type == "electric"
    assert state.energy.level == 62
    assert state.energy.range_km == 209
    assert state.energy.charging is True
    assert state.energy.plugged is True
    assert state.energy.charge_remaining_min == 85
    # 398 V * 18,6 A = 7,4 kW - hat Vorrang vor chargingRate (22 = km/h)
    assert state.energy.charge_kw == 7.4
    assert state.odometer_km == 24310.7
    assert state.doors.locked is True
    assert state.doors.open == []
    assert state.climate.active is False
    assert state.climate.outside_c == 11.5
    assert round(state.position.lat, 4) == 51.2277
    assert round(state.position.lon, 4) == 6.7735
    assert state.updated == parse_iso("2026-03-01T08:30:00Z")


def test_snake_offen_und_klima():
    state = normalize_status(SNAKE, vin="VIN2", name="Mokka-e", source="psacc")
    assert state.energy.level == 18
    assert state.energy.charging is False
    assert state.energy.plugged is False
    assert state.doors.locked is False
    assert sorted(state.doors.open) == ["fl", "trunk"]
    assert state.climate.active is True
    assert state.climate.outside_c == -3.0
    assert state.position.heading == 90


def test_hybrid_kombiniert_beide_energien():
    raw = {
        "energy": [
            {"type": "Fuel", "level": 55, "autonomy": 430},
            {
                "type": "Electric",
                "level": 40,
                "autonomy": 38,
                "charging": {"status": "Stopped", "plugged": True},
            },
        ]
    }
    state = normalize_status(raw)
    assert state.energy.type == "hybrid"
    assert state.energy.level == 40
    assert state.energy.secondary_level == 55
    assert state.energy.secondary_range_km == 430


def test_nur_verbrenner():
    state = normalize_status({"energy": [{"type": "Fuel", "level": 72, "autonomy": 610}]})
    assert state.energy.type == "fuel"
    assert state.energy.level == 72
    assert state.energy.range_km == 610
    assert state.energy.charging is False


def test_leere_und_kaputte_daten_werfen_nicht():
    for raw in ({}, {"energy": None}, {"energy": "kaputt"}, {"doorsState": 42}):
        state = normalize_status(raw)          # darf keine Exception werfen
        assert state.energy.level is None or isinstance(state.energy.level, (int, float))
        assert state.doors.locked is None


def test_schwache_starterbatterie_wird_gemeldet():
    state = normalize_status({"battery": {"voltage": 11.2, "current": 0}})
    assert "Starterbatterie schwach" in state.alerts
