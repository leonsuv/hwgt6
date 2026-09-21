"""Normalisiertes Fahrzeugmodell.

Alle Provider (Mock, psacc, Stellantis) liefern dieses Format. Die Uhr kennt
ausschliesslich dieses Schema - Aenderungen an der Opel-API werden im Provider
abgefangen, nicht in der Watch-App.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1


def _round(value: Optional[float], digits: int = 1) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _int(value: Optional[float]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


@dataclass
class Energy:
    """Energiestand. type: electric | fuel | hybrid."""
    type: str = "unknown"
    level: Optional[float] = None            # % (Akku) bzw. % (Tank)
    range_km: Optional[int] = None
    charging: bool = False
    plugged: bool = False
    charge_kw: Optional[float] = None
    charge_rate_kmh: Optional[float] = None   # PSA liefert die Laderate in km/h
    charge_remaining_min: Optional[int] = None
    charge_mode: Optional[str] = None        # immediate | delayed | no
    target_level: Optional[int] = None
    # Zweitenergie bei Hybrid (z.B. Tank in %, Reichweite km)
    secondary_level: Optional[float] = None
    secondary_range_km: Optional[int] = None

    def clean(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "level": _int(self.level),
            "range_km": _int(self.range_km),
            "charging": bool(self.charging),
            "plugged": bool(self.plugged),
            "charge_kw": _round(self.charge_kw, 1),
            "charge_rate_kmh": _round(self.charge_rate_kmh, 0),
            "charge_remaining_min": _int(self.charge_remaining_min),
            "charge_mode": self.charge_mode,
            "target_level": _int(self.target_level),
            "secondary_level": _int(self.secondary_level),
            "secondary_range_km": _int(self.secondary_range_km),
        }


@dataclass
class Doors:
    locked: Optional[bool] = None
    open: List[str] = field(default_factory=list)   # z.B. ["front_left", "trunk"]

    def clean(self) -> Dict[str, Any]:
        return {"locked": self.locked, "open": list(self.open)}


@dataclass
class Climate:
    active: bool = False
    cabin_c: Optional[float] = None
    outside_c: Optional[float] = None

    def clean(self) -> Dict[str, Any]:
        return {
            "active": bool(self.active),
            "cabin_c": _round(self.cabin_c, 1),
            "outside_c": _round(self.outside_c, 1),
        }


@dataclass
class Position:
    lat: Optional[float] = None
    lon: Optional[float] = None
    heading: Optional[int] = None
    updated: Optional[int] = None            # Unix-Sekunden

    def clean(self) -> Dict[str, Any]:
        return {
            "lat": _round(self.lat, 5),
            "lon": _round(self.lon, 5),
            "heading": _int(self.heading),
            "updated": _int(self.updated),
        }


@dataclass
class VehicleState:
    vin: str = ""
    name: str = "Opel"
    brand: str = "Opel"
    energy: Energy = field(default_factory=Energy)
    doors: Doors = field(default_factory=Doors)
    climate: Climate = field(default_factory=Climate)
    position: Position = field(default_factory=Position)
    odometer_km: Optional[int] = None
    alerts: List[str] = field(default_factory=list)
    updated: Optional[int] = None            # Zeitpunkt der Fahrzeugmessung
    source: str = "unknown"

    def to_json(self, now: Optional[int] = None) -> Dict[str, Any]:
        now = int(now if now is not None else time.time())
        updated = _int(self.updated) or now
        return {
            "v": SCHEMA_VERSION,
            "ts": now,
            "updated": updated,
            "age_s": max(0, now - updated),
            "source": self.source,
            "vehicle": {"vin": self.vin, "name": self.name, "brand": self.brand},
            "energy": self.energy.clean(),
            "doors": self.doors.clean(),
            "climate": self.climate.clean(),
            "position": self.position.clean(),
            "odometer_km": _int(self.odometer_km),
            "alerts": list(self.alerts),
        }

    def to_watch(self, now: Optional[int] = None) -> Dict[str, Any]:
        """Kompakte Variante fuer die Uhr - flach, kurze Schluessel, kleines JSON."""
        full = self.to_json(now)
        e = full["energy"]
        d = full["doors"]
        c = full["climate"]
        return {
            "v": SCHEMA_VERSION,
            "ts": full["ts"],
            "age": full["age_s"],
            "nm": full["vehicle"]["name"],
            "et": e["type"],
            "lvl": e["level"],
            "rng": e["range_km"],
            "chg": 1 if e["charging"] else 0,
            "plg": 1 if e["plugged"] else 0,
            "kw": e["charge_kw"],
            "kmh": e["charge_rate_kmh"],
            "eta": e["charge_remaining_min"],
            "tgt": e["target_level"],
            "lvl2": e["secondary_level"],
            "rng2": e["secondary_range_km"],
            "odo": full["odometer_km"],
            "lck": (1 if d["locked"] else 0) if d["locked"] is not None else -1,
            "opn": len(d["open"]),
            "opl": d["open"][:4],
            "clm": 1 if c["active"] else 0,
            "tin": c["cabin_c"],
            "tout": c["outside_c"],
            "lat": full["position"]["lat"],
            "lon": full["position"]["lon"],
            "alt": full["alerts"][:3],
            "src": full["source"],
        }

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
