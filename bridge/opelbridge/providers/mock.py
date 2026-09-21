"""Mock-Provider: simuliert ein Fahrzeug, damit Uhr und UI ohne echten
Opel-Connect-Zugang getestet werden koennen.

Das simulierte Auto laedt, faehrt los und kuehlt ab - alles zeitabhaengig,
damit man Aenderungen auf der Uhr wirklich sieht.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict

from ..model import Climate, Doors, Energy, Position, VehicleState
from .base import Provider


class MockProvider(Provider):
    name = "mock"
    supports_commands = ["wakeup", "preconditioning", "charge_now", "lock", "unlock"]

    def __init__(self, cfg: Dict[str, Any], vin: str = ""):
        super().__init__(cfg, vin)
        self._start = time.time()
        self._climate_until = 0.0
        self._locked = True

    def fetch(self) -> VehicleState:
        cfg = self.cfg
        now = time.time()
        t = now - self._start
        etype = cfg.get("energy_type", "electric")

        # Ladezyklus: 40 % -> 80 % in 20 Minuten, dann Pause, dann von vorn
        cycle = 1800.0
        phase = (t % cycle) / cycle
        charging = phase < 0.66 and cfg.get("charging", True)
        base_level = float(cfg.get("level", 42))
        level = base_level + (80.0 - base_level) * min(1.0, phase / 0.66) if charging else 80.0
        level = max(3.0, min(100.0, level))
        rng_full = float(cfg.get("range_full_km", 337))
        range_km = rng_full * level / 100.0

        eta = None
        kw = None
        if charging:
            kw = round(7.4 + 0.6 * math.sin(t / 60.0), 1)
            eta = int(max(1, (80.0 - level) / 40.0 * 20.0))

        state = VehicleState(
            vin=self.vin or cfg.get("vin", "W0VZZZMOCK0000001"),
            name=cfg.get("name", "Corsa-e"),
            brand=cfg.get("brand", "Opel"),
            source="mock",
            odometer_km=int(cfg.get("odometer_km", 24310) + t / 600.0),
            updated=int(now - 30),
            energy=Energy(
                type=etype,
                level=round(level),
                range_km=int(range_km),
                charging=charging,
                plugged=charging or phase < 0.75,
                charge_kw=kw,
                charge_remaining_min=eta,
                charge_mode="immediate" if charging else "delayed",
                target_level=80,
                secondary_level=round(62 - (t / 3600.0) % 50, 0) if etype == "hybrid" else None,
                secondary_range_km=int(430 * 0.62) if etype == "hybrid" else None,
            ),
            doors=Doors(
                locked=self._locked,
                open=[] if self._locked else ["front_left"],
            ),
            climate=Climate(
                active=now < self._climate_until,
                cabin_c=round(18.0 + 4.0 * math.sin(t / 300.0), 1),
                outside_c=round(11.5 + 3.0 * math.sin(t / 900.0), 1),
            ),
            position=Position(
                lat=round(51.2277 + 0.004 * math.sin(t / 700.0), 5),
                lon=round(6.7735 + 0.004 * math.cos(t / 700.0), 5),
                heading=int((t / 4) % 360),
                updated=int(now - 60),
            ),
            alerts=(["Reifendruck vorne links niedrig"] if cfg.get("alert") else []),
        )
        return state

    def command(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name == "preconditioning":
            minutes = int(args.get("minutes", 10))
            self._climate_until = time.time() + minutes * 60
            return {"ok": True, "message": "Vorklimatisierung fuer %d min gestartet" % minutes}
        if name == "lock":
            self._locked = True
            return {"ok": True, "message": "Verriegelt"}
        if name == "unlock":
            self._locked = False
            return {"ok": True, "message": "Entriegelt"}
        if name in ("wakeup", "charge_now"):
            return {"ok": True, "message": "%s ausgefuehrt" % name}
        return super().command(name, args)
