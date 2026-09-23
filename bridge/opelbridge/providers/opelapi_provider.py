"""Provider auf Basis der Bibliothek 'opelapi' (eigenes, funktionierendes Repo).

Das ist der genaueste Weg: opelapi spricht dieselbe Schnittstelle wie die
MyOpel-App, erneuert das Access-Token selbsttaetig (siehe OpelAuth.access_token)
und kann ueber MQTT auch Befehle senden.

Installation:
    py -m pip install -e C:\\Pfad\\zu\\opelapi-main
    py -m opelapi.cli login --country DE     (einmalig)
    py -m opelapi.cli enable-remote          (optional, fuer Befehle)

Konfiguration in bridge/config.json:
    "provider": "opelapi",
    "opelapi": { "session_path": "", "vin": "", "command_timeout_s": 45 }
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from ..model import Climate, Doors, Energy, Position, VehicleState
from .base import AuthError, Provider, ProviderError
from .psa_common import parse_iso

_DOOR_MAP = {
    "driver": "fl",
    "frontleft": "fl",
    "passenger": "fr",
    "frontright": "fr",
    "rearleft": "rl",
    "rearright": "rr",
    "trunk": "trunk",
    "boot": "trunk",
    "hood": "hood",
    "bonnet": "hood",
    "sunroof": "roof",
    "rearwindow": "rear",
}


def _norm_door(name: Any) -> str:
    key = str(name).strip().lower().replace("_", "").replace(" ", "")
    return _DOOR_MAP.get(key, key[:8])


class OpelApiProvider(Provider):
    name = "opelapi"
    supports_commands = [
        "wakeup",
        "preconditioning",
        "lock",
        "unlock",
        "horn",
        "lights",
        "charge_now",
        "stop_charge",
    ]

    def __init__(self, cfg: Dict[str, Any], vin: str = ""):
        super().__init__(cfg, vin)
        self._client = None
        self._lock = threading.RLock()
        self._label: Optional[str] = None

    # ----------------------------------------------------------- Client
    def _load_client(self):
        """Client erst bei Bedarf bauen - der Import zieht requests/paho nach."""
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                from opelapi import OpelClient                      # type: ignore
                from opelapi.session import DEFAULT_SESSION_PATH    # type: ignore
            except ImportError as exc:
                raise ProviderError(
                    "Die Bibliothek 'opelapi' ist nicht installiert. "
                    "py -m pip install -e <Pfad zu opelapi-main>  (%s)" % exc
                ) from exc

            path = str(self.cfg.get("session_path") or DEFAULT_SESSION_PATH)
            try:
                self._client = OpelClient.load(path)
            except FileNotFoundError as exc:
                raise AuthError(
                    "Keine Sitzung unter %s. Einmalig anmelden: "
                    "py -m opelapi.cli login --country DE" % path
                ) from exc
            except Exception as exc:                                # noqa: BLE001
                raise ProviderError("opelapi-Sitzung nicht ladbar: %s" % exc) from exc
            return self._client

    def _vehicle(self):
        client = self._load_client()
        vin = self.vin or str(self.cfg.get("vin") or "")
        try:
            car = client.vehicle(vin or None)
        except Exception as exc:                                    # noqa: BLE001
            message = str(exc)
            if "vehicles" in message and "pass a vin" in message:
                raise ProviderError(
                    "Mehrere Fahrzeuge im Konto - 'vin' in config.json setzen. %s" % message
                ) from exc
            raise ProviderError("Fahrzeug nicht bestimmbar: %s" % message) from exc
        self.vin = car.vin
        self._label = car.label or "Opel"
        return car

    # -------------------------------------------------------------- Lesen
    def fetch(self) -> VehicleState:
        client = self._load_client()
        car = self._vehicle()
        try:
            status = client.status(car)
        except Exception as exc:                                    # noqa: BLE001
            self._raise_mapped(exc)
        return self._to_state(status, car)

    def _raise_mapped(self, exc: Exception) -> None:
        """opelapi-Fehler auf die Bridge-Fehlerarten abbilden."""
        name = type(exc).__name__
        if name in ("AuthenticationError", "OtpError"):
            raise AuthError(
                "Anmeldung abgelaufen (%s). Neu anmelden: "
                "py -m opelapi.cli login --country DE. Ursache: %s" % (name, exc)
            ) from exc
        raise ProviderError("%s: %s" % (name, exc)) from exc

    def _to_state(self, status, car) -> VehicleState:
        raw = getattr(status, "raw", {}) or {}
        battery = status.battery_level
        fuel = status.fuel_level

        if battery is not None and fuel:
            etype = "hybrid"
        elif battery is not None:
            etype = "electric"
        elif fuel is not None:
            etype = "fuel"
        else:
            etype = "unknown"

        remaining = status.charging_remaining
        remaining_min = int(remaining.total_seconds() // 60) if remaining else None

        energy = Energy(
            type=etype,
            level=battery if battery is not None else fuel,
            range_km=status.range_km if battery is not None else status.fuel_range_km,
            charging=bool(status.charging),
            # "plugged" bleibt oft true, obwohl der Status "Disconnected" meldet
            plugged=bool(status.plugged) and (status.charging_status or "").lower() != "disconnected",
            charge_rate_kmh=status.charging_rate_kmh,
            charge_remaining_min=remaining_min,
            charge_mode=(status.charging_mode or "").lower() or None,
        )
        # Bewusst kein kW-Wert: die API liefert nur chargingRate in km/h.
        # Aus Kapazitaet und Restzeit liesse sich etwas schaetzen, aber die
        # Restzeit bezieht sich je nach Fahrzeug auf das Ladeziel statt auf
        # 100 %, und eine falsche kW-Zahl ist schlechter als gar keine.
        if etype == "hybrid":
            energy.secondary_level = fuel
            energy.secondary_range_km = status.fuel_range_km

        doors_raw = raw.get("doorsState") or {}
        opened = doors_raw.get("opened") or []
        doors = Doors(
            locked=status.locked,
            open=[d for d in (_norm_door(x) for x in opened) if d and d != "none"],
        )

        air = ((raw.get("environment") or {}).get("air") or {})
        climate = Climate(
            active=bool(status.preconditioning),
            cabin_c=air.get("cabinTemp"),
            outside_c=air.get("temp"),
        )

        position = Position()
        coords = status.position
        if coords:
            position = Position(
                lat=coords[0],
                lon=coords[1],
                heading=status.heading,
                updated=int(status.position_updated_at.timestamp())
                if status.position_updated_at
                else None,
            )

        alerts: List[str] = []
        if status.privacy_mode:
            alerts.append("Privatmodus aktiv - keine Position")
        if status.moving:
            alerts.append("Fahrzeug fährt")
        health = status.battery_health_capacity
        if health is not None and health < 80:
            alerts.append("Batteriegesundheit %d %%" % round(health))

        return VehicleState(
            vin=car.vin,
            name=self._label or car.label or "Opel",
            brand="Opel",
            source="opelapi",
            energy=energy,
            doors=doors,
            climate=climate,
            position=position,
            odometer_km=status.odometer_km,
            alerts=alerts,
            updated=int(status.updated_at.timestamp())
            if status.updated_at
            else parse_iso(raw.get("createdAt")),
        )

    # ------------------------------------------------------------ Befehle
    def command(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        client = self._load_client()
        car = self._vehicle()
        timeout = int(self.cfg.get("command_timeout_s", 45))
        actions = {
            "wakeup": lambda: client.wake_up(car, timeout=timeout),
            "lock": lambda: client.lock(car, timeout=timeout),
            "unlock": lambda: client.unlock(car, timeout=timeout),
            "horn": lambda: client.horn(car, timeout=timeout),
            "lights": lambda: client.lights(car, timeout=timeout),
            "charge_now": lambda: client.start_charge(car, timeout=timeout),
            "stop_charge": lambda: client.stop_charge(car, timeout=timeout),
        }
        if name == "preconditioning":
            activate = str(args.get("activate", "1")) in ("1", "true", "on", "yes")
            actions["preconditioning"] = (
                (lambda: client.start_preconditioning(car, timeout=timeout))
                if activate
                else (lambda: client.stop_preconditioning(car, timeout=timeout))
            )

        action = actions.get(name)
        if action is None:
            return super().command(name, args)

        try:
            result = action()
        except Exception as exc:                                    # noqa: BLE001
            kind = type(exc).__name__
            if kind == "CommandTimeout":
                return {
                    "ok": False,
                    "message": "Fahrzeug antwortet nicht - evtl. Tiefschlaf. Erst wecken.",
                }
            if kind in ("AuthenticationError", "OtpError"):
                return {
                    "ok": False,
                    "message": "Fernbefehle nicht freigeschaltet: py -m opelapi.cli enable-remote",
                }
            return {"ok": False, "message": "%s: %s" % (kind, exc)}

        message = getattr(result, "message", None) or str(result or "ausgefuehrt")
        return {"ok": True, "message": message[:120]}

    def describe(self) -> Dict[str, Any]:
        info = super().describe()
        info["vin"] = self.vin[-6:] if self.vin else ""
        return info
