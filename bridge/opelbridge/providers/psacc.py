"""Provider fuer psa_car_controller (flobz/psa_car_controller).

Empfohlener Weg: psa_car_controller erledigt Login, Captcha, Token-Erneuerung
und MQTT-Push. Diese Bridge liest dessen lokale REST-Schnittstelle und
normalisiert die Daten fuer die Uhr.

Erwartete Endpunkte von psa_car_controller:
    GET  /get_vehicles
    GET  /get_vehicleinfo/<vin>?from_cache=1
    GET  /wakeup/<vin>
    GET  /preconditioning/<vin>/<0|1>
    GET  /charge_now/<vin>/<hour>/<minute>
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from .. import httpclient
from ..model import VehicleState
from .base import AuthError, Provider, ProviderError
from .psa_common import normalize_status, pick


class PsaccProvider(Provider):
    name = "psacc"
    supports_commands = ["wakeup", "preconditioning", "charge_now"]

    def __init__(self, cfg: Dict[str, Any], vin: str = ""):
        super().__init__(cfg, vin)
        self.base = str(cfg.get("base_url", "http://127.0.0.1:5000")).rstrip("/")
        self.timeout = float(cfg.get("timeout_s", 15))
        self.from_cache = bool(cfg.get("from_cache", True))
        self.verify = bool(cfg.get("verify_tls", True))
        self._label: Optional[str] = None

    # ------------------------------------------------------------- intern
    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        user = self.cfg.get("user")
        password = self.cfg.get("password")
        if user:
            raw = ("%s:%s" % (user, password or "")).encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return headers

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self.base + path
        try:
            return httpclient.get_json(
                url,
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
                verify=self.verify,
            )
        except httpclient.HttpError as exc:
            if exc.status in (401, 403):
                raise AuthError("psa_car_controller verweigert den Zugriff (%s)" % exc.status)
            raise ProviderError(str(exc)) from exc
        except RuntimeError as exc:
            raise ProviderError(
                "psa_car_controller unter %s nicht erreichbar: %s" % (self.base, exc)
            ) from exc

    def _vehicles(self) -> List[Dict[str, Any]]:
        data = self._get("/get_vehicles")
        if isinstance(data, dict):
            for key in ("vehicles", "cars", "result", "data"):
                if isinstance(data.get(key), list):
                    return data[key]
            embedded = data.get("_embedded") or {}
            if isinstance(embedded.get("vehicles"), list):
                return embedded["vehicles"]
            return []
        return data if isinstance(data, list) else []

    def _resolve_vin(self) -> str:
        if self.vin:
            return self.vin
        vehicles = self._vehicles()
        if not vehicles:
            raise ProviderError("psa_car_controller meldet kein Fahrzeug")
        first = vehicles[0]
        vin = str(pick(first, "vin", "id", default="") or "")
        self._label = pick(first, "label", "name", "model")
        if not vin:
            raise ProviderError("Fahrzeug ohne VIN in der Antwort von psa_car_controller")
        self.vin = vin
        return vin

    def _label_for(self, vin: str) -> str:
        if self._label:
            return str(self._label)
        try:
            for vehicle in self._vehicles():
                if str(pick(vehicle, "vin", "id", default="")) == vin:
                    self._label = pick(vehicle, "label", "name", "model") or "Opel"
                    return str(self._label)
        except ProviderError:
            pass
        return "Opel"

    # -------------------------------------------------------------- public
    def fetch(self) -> VehicleState:
        vin = self._resolve_vin()
        raw = self._get(
            "/get_vehicleinfo/" + vin,
            params={"from_cache": 1 if self.from_cache else 0},
        )
        if not isinstance(raw, dict):
            raise ProviderError("Unerwartete Antwort von /get_vehicleinfo")
        # psacc verpackt den Status je nach Version unterschiedlich
        status = raw
        for key in ("status", "last_status", "info", "result"):
            inner = raw.get(key)
            if isinstance(inner, dict) and (
                "energy" in inner or "lastPosition" in inner or "last_position" in inner
            ):
                status = inner
                break
        return normalize_status(
            status,
            vin=vin,
            name=str(self.cfg.get("name") or self._label_for(vin)),
            brand=str(self.cfg.get("brand", "Opel")),
            source="psacc",
        )

    def command(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        vin = self._resolve_vin()
        if name == "wakeup":
            self._get("/wakeup/" + vin)
            return {"ok": True, "message": "Weckruf gesendet"}
        if name == "preconditioning":
            activate = 1 if str(args.get("activate", "1")) in ("1", "true", "on") else 0
            self._get("/preconditioning/%s/%d" % (vin, activate))
            return {
                "ok": True,
                "message": "Vorklimatisierung %s" % ("gestartet" if activate else "gestoppt"),
            }
        if name == "charge_now":
            hour = int(args.get("hour", -1))
            minute = int(args.get("minute", 0))
            self._get("/charge_now/%s/%d/%d" % (vin, hour, minute))
            return {"ok": True, "message": "Ladebefehl gesendet"}
        return super().command(name, args)
