"""Gemeinsame Normalisierung fuer PSA/Stellantis-Statusdaten.

Die Rohdaten kommen je nach Quelle in camelCase (direkte Stellantis-API) oder
snake_case (psa_car_controller / generierter OpenAPI-Client). Beide Varianten
werden hier toleriert, fehlende Felder fuehren nie zu einer Exception.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from ..model import Climate, Doors, Energy, Position, VehicleState

_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>[\d.]+)S)?)?$"
)

# Tuernamen aus der PSA-API -> kurze, uhrentaugliche Bezeichner
_DOOR_MAP = {
    "driver": "fl",
    "frontleft": "fl",
    "front_left": "fl",
    "passenger": "fr",
    "frontright": "fr",
    "front_right": "fr",
    "rearleft": "rl",
    "rear_left": "rl",
    "rearright": "rr",
    "rear_right": "rr",
    "trunk": "trunk",
    "boot": "trunk",
    "hatch": "trunk",
    "rearwindow": "rear",
    "hood": "hood",
    "bonnet": "hood",
    "sunroof": "roof",
}


def pick(data: Any, *names: str, default: Any = None) -> Any:
    """Ersten vorhandenen Schluessel liefern (camelCase oder snake_case)."""
    if not isinstance(data, dict):
        return default
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        if snake in data and data[snake] is not None:
            return data[snake]
        camel = re.sub(r"_([a-z])", lambda m: m.group(1).upper(), name)
        if camel in data and data[camel] is not None:
            return data[camel]
    return default


def parse_iso(value: Any) -> Optional[int]:
    """ISO-8601-Zeitstempel -> Unix-Sekunden."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, datetime):
        return int(value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp())
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    text = re.sub(r"\.(\d{3})\d+", r".\1", text)          # Mikrosekunden kuerzen
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def parse_duration_min(value: Any) -> Optional[int]:
    """ISO-8601-Dauer ('PT1H30M') -> Minuten. Zahlen gelten als Minuten."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().upper()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    match = _DURATION_RE.match(text)
    if not match:
        return None
    parts = {k: float(v) for k, v in match.groupdict(default="0").items()}
    total = parts["days"] * 1440 + parts["hours"] * 60 + parts["minutes"] + parts["seconds"] / 60
    return int(round(total))


def _norm_door(name: str) -> str:
    key = str(name).strip().lower().replace(" ", "")
    return _DOOR_MAP.get(key, key[:8] or "?")


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _energy_entries(raw: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for entry in _as_list(pick(raw, "energy", "energies", default=[])):
        if isinstance(entry, dict):
            yield entry


def _charge_power_kw(raw: Dict[str, Any]) -> Optional[float]:
    """Ladeleistung aus Spannung x Strom der Traktionsbatterie.

    Die PSA-API liefert KEINE Ladeleistung: 'chargingRate' ist der
    Reichweitenzuwachs in km/h und wird separat als charge_rate_kmh gefuehrt.
    """
    battery = pick(raw, "battery", default={}) or {}
    voltage = pick(battery, "voltage")
    current = pick(battery, "current")
    try:
        if voltage is not None and current is not None:
            kw = abs(float(voltage) * float(current)) / 1000.0
            if 0.3 <= kw <= 400.0:
                return round(kw, 1)
    except (TypeError, ValueError):
        pass
    return None


def _charging_block(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Ladeinformationen liegen je nach Antwortform an zwei Stellen.

    Flach:        energy[].charging
    Verschachtelt: energies[].extension.electric.charging   (aktuelle API)
    """
    flat = pick(entry, "charging", default=None)
    if isinstance(flat, dict) and flat:
        return flat
    extension = pick(entry, "extension", default={}) or {}
    electric = pick(extension, "electric", default={}) or {}
    nested = pick(electric, "charging", default={}) or {}
    return nested if isinstance(nested, dict) else {}


def normalize_status(
    raw: Dict[str, Any],
    *,
    vin: str = "",
    name: str = "Opel",
    brand: str = "Opel",
    source: str = "psa",
) -> VehicleState:
    raw = raw or {}
    state = VehicleState(vin=vin, name=name, brand=brand, source=source)

    # ------------------------------------------------------------- Energie
    electric: Optional[Dict[str, Any]] = None
    fuel: Optional[Dict[str, Any]] = None
    latest_energy_ts: Optional[int] = None
    for entry in _energy_entries(raw):
        etype = str(pick(entry, "type", default="")).lower()
        ts = parse_iso(pick(entry, "updated_at", "updatedAt", "created_at", "createdAt"))
        if ts:
            latest_energy_ts = max(latest_energy_ts or 0, ts)
        level = pick(entry, "level")
        if etype.startswith("electric"):
            # Eintraege mit level=None/0 und ohne Ladeinfo ignorieren
            if electric is None or (level or 0) > 0:
                electric = entry
        elif etype.startswith("fuel") or etype.startswith("petrol") or etype.startswith("diesel"):
            if fuel is None or (level or 0) > 0:
                fuel = entry

    if electric is not None:
        charging = _charging_block(electric)
        status = str(pick(charging, "status", default="")).lower()
        mode = pick(charging, "charging_mode", "chargingMode")
        rate = pick(charging, "charging_rate", "chargingRate")
        state.energy = Energy(
            type="hybrid" if fuel is not None and (pick(fuel, "level") or 0) > 0 else "electric",
            level=pick(electric, "level"),
            range_km=pick(electric, "autonomy", "range"),
            charging=status in ("inprogress", "in_progress", "charging"),
            plugged=bool(pick(charging, "plugged", default=status not in ("", "disconnected"))),
            charge_kw=_charge_power_kw(raw),
            charge_rate_kmh=rate,
            charge_remaining_min=parse_duration_min(
                pick(charging, "remaining_time", "remainingTime")
            ),
            charge_mode=str(mode).lower() if mode else None,
            target_level=pick(charging, "target_level", "targetLevel"),
        )
        if fuel is not None:
            state.energy.secondary_level = pick(fuel, "level")
            state.energy.secondary_range_km = pick(fuel, "autonomy", "range")
    elif fuel is not None:
        state.energy = Energy(
            type="fuel",
            level=pick(fuel, "level"),
            range_km=pick(fuel, "autonomy", "range"),
        )

    # ------------------------------------------------------------ Kilometer
    odo = pick(raw, "timed_odometer", "timedOdometer", "odometer", default={}) or {}
    state.odometer_km = pick(odo, "mileage", "value") if isinstance(odo, dict) else odo

    # ---------------------------------------------------------------- Tuer
    doors = pick(raw, "doors_state", "doorsState", "door_state", default={}) or {}
    locked_states = [
        str(s).lower() for s in _as_list(pick(doors, "locked_states", "lockedStates"))
    ]
    locked: Optional[bool] = None
    if locked_states:
        locked = "locked" in locked_states and "unlocked" not in locked_states
    opened = [_norm_door(d) for d in _as_list(pick(doors, "opened", "opened_states", default=[]))]
    state.doors = Doors(locked=locked, open=[d for d in opened if d and d != "none"])

    # ------------------------------------------------------------ Klima/Temp
    precond = pick(raw, "preconditionning", "preconditioning", default={}) or {}
    air = pick(precond, "air_conditioning", "airConditioning", default={}) or {}
    ac_status = str(pick(air, "status", default="")).lower()
    environment = pick(raw, "environment", default={}) or {}
    air_env = pick(environment, "air", default={}) or {}
    state.climate = Climate(
        active=ac_status in ("enabled", "inprogress", "in_progress", "active"),
        cabin_c=pick(air_env, "cabin_temp", "cabinTemp"),
        outside_c=pick(air_env, "temp", "temperature"),
    )

    # ------------------------------------------------------------- Position
    pos = pick(raw, "last_position", "lastPosition", default={}) or {}
    geometry = pick(pos, "geometry", default={}) or {}
    coords = _as_list(pick(geometry, "coordinates", default=[]))
    props = pick(pos, "properties", default={}) or {}
    if len(coords) >= 2:
        try:
            state.position = Position(
                lat=float(coords[1]),
                lon=float(coords[0]),
                heading=pick(props, "heading"),
                updated=parse_iso(
                    pick(props, "updated_at", "updatedAt", "created_at", "createdAt")
                ),
            )
        except (TypeError, ValueError):
            pass

    # ------------------------------------------------------------ Zeitstempel
    state.updated = (
        parse_iso(pick(raw, "updated_at", "updatedAt", "created_at", "createdAt"))
        or latest_energy_ts
        or state.position.updated
    )

    # ---------------------------------------------------------------- Alarme
    alerts: List[str] = []
    for alert in _as_list(pick(raw, "alerts", default=[])):
        if isinstance(alert, dict):
            label = pick(alert, "label", "type", "id")
            if label:
                alerts.append(str(label))
        elif alert:
            alerts.append(str(alert))
    battery = pick(raw, "battery", default={}) or {}
    try:
        voltage = float(pick(battery, "voltage", default=0) or 0)
        if 0 < voltage < 11.8:
            alerts.append("Starterbatterie schwach")
    except (TypeError, ValueError):
        pass
    state.alerts = alerts[:5]
    return state
