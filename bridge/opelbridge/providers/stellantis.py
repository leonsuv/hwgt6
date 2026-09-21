"""Direkter Zugriff auf die Stellantis-/Opel-Connect-Fahrzeug-API.

WICHTIG - Zugangsdaten
----------------------
Opel Connect hat keine offene, dokumentierte Endkunden-API. Dieser Provider
enthaelt daher bewusst KEINE eingebauten client_id/client_secret. Beides plus
ein refresh_token muss in der Konfiguration hinterlegt werden; wie man das
bekommt, steht in docs/OPEL-CONNECT-SETUP.md (in der Regel einmalig ueber
psa_car_controller, das den Login inkl. Captcha durchfuehrt).

Die Standard-URLs entsprechen der oeffentlich dokumentierten PSA-"Connected
Car"-v4-Schnittstelle und sind komplett ueberschreibbar, falls Stellantis sie
aendert.
"""
from __future__ import annotations

import base64
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .. import httpclient
from ..model import VehicleState
from .base import AuthError, Provider, ProviderError
from .psa_common import normalize_status, pick

DEFAULTS = {
    "token_url": "https://idpcvs.opel.com/am/oauth2/access_token",
    "api_base": "https://api.groupe-psa.com/connectedcar/v4/user",
    "realm": "clientsB2COpel",
    "scope": "openid profile",
}


class StellantisProvider(Provider):
    name = "stellantis"
    supports_commands: List[str] = []          # Remote-Befehle brauchen MQTT+Zertifikat

    def __init__(
        self,
        cfg: Dict[str, Any],
        vin: str = "",
        on_tokens: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        super().__init__(cfg, vin)
        self.token_url = str(cfg.get("token_url") or DEFAULTS["token_url"])
        self.api_base = str(cfg.get("api_base") or DEFAULTS["api_base"]).rstrip("/")
        self.realm = str(cfg.get("realm") or DEFAULTS["realm"])
        self.scope = str(cfg.get("scope") or DEFAULTS["scope"])
        self.client_id = str(cfg.get("client_id") or "")
        self.client_secret = str(cfg.get("client_secret") or "")
        self.refresh_token = str(cfg.get("refresh_token") or "")
        self.timeout = float(cfg.get("timeout_s", 25))
        self._access_token: str = str(cfg.get("access_token") or "")
        self._expires_at: float = float(cfg.get("expires_at") or 0)
        self._vehicle_id: str = str(cfg.get("vehicle_id") or "")
        self._label: str = str(cfg.get("name") or "")
        self._lock = threading.RLock()
        self._on_tokens = on_tokens

        if not self.client_id or not self.client_secret:
            raise ProviderError(
                "stellantis.client_id / client_secret fehlen in der Konfiguration - "
                "siehe docs/OPEL-CONNECT-SETUP.md"
            )
        if not self.refresh_token:
            raise ProviderError(
                "stellantis.refresh_token fehlt - einmalige Anmeldung noetig, "
                "siehe docs/OPEL-CONNECT-SETUP.md"
            )

    # ---------------------------------------------------------------- Token
    def _basic_auth(self) -> str:
        raw = ("%s:%s" % (self.client_id, self.client_secret)).encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _ensure_token(self) -> str:
        with self._lock:
            if self._access_token and time.time() < self._expires_at - 60:
                return self._access_token
            return self._refresh()

    def _refresh(self) -> str:
        form = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "scope": self.scope,
        }
        url = self.token_url
        if self.realm and "realm=" not in url:
            url = url + ("&" if "?" in url else "?") + "realm=" + self.realm
        try:
            data = httpclient.post_json(
                url,
                headers={
                    "Authorization": self._basic_auth(),
                    "Accept": "application/json",
                },
                form=form,
                timeout=self.timeout,
                retries=1,
            )
        except httpclient.HttpError as exc:
            if exc.status in (400, 401, 403):
                raise AuthError(
                    "Token-Erneuerung abgelehnt (%s). refresh_token vermutlich "
                    "abgelaufen - neu anmelden. Antwort: %s" % (exc.status, exc.body[:200])
                ) from exc
            raise ProviderError(str(exc)) from exc
        except RuntimeError as exc:
            raise ProviderError("Token-Endpunkt nicht erreichbar: %s" % exc) from exc

        if not isinstance(data, dict) or not data.get("access_token"):
            raise AuthError("Token-Antwort ohne access_token: %r" % (data,))

        self._access_token = str(data["access_token"])
        self._expires_at = time.time() + float(data.get("expires_in", 3600))
        new_refresh = data.get("refresh_token")
        if new_refresh and new_refresh != self.refresh_token:
            self.refresh_token = str(new_refresh)
            if self._on_tokens:
                self._on_tokens(
                    {
                        "refresh_token": self.refresh_token,
                        "access_token": self._access_token,
                        "expires_at": self._expires_at,
                    }
                )
        return self._access_token

    # ------------------------------------------------------------------ API
    def _api(self, path: str, params: Optional[Dict[str, Any]] = None, retry_auth: bool = True) -> Any:
        token = self._ensure_token()
        query = {"client_id": self.client_id}
        query.update(params or {})
        try:
            return httpclient.get_json(
                self.api_base + path,
                headers={
                    "Authorization": "Bearer " + token,
                    "x-introspect-realm": self.realm,
                    "Accept": "application/hal+json",
                },
                params=query,
                timeout=self.timeout,
            )
        except httpclient.HttpError as exc:
            if exc.status in (401, 403) and retry_auth:
                with self._lock:
                    self._access_token = ""
                    self._expires_at = 0
                return self._api(path, params, retry_auth=False)
            if exc.status in (401, 403):
                raise AuthError("Zugriff verweigert (%s): %s" % (exc.status, exc.body[:200]))
            raise ProviderError(str(exc)) from exc
        except RuntimeError as exc:
            raise ProviderError("Stellantis-API nicht erreichbar: %s" % exc) from exc

    def _vehicles(self) -> List[Dict[str, Any]]:
        data = self._api("/vehicles")
        if isinstance(data, dict):
            embedded = data.get("_embedded") or {}
            vehicles = embedded.get("vehicles")
            if isinstance(vehicles, list):
                return vehicles
            if isinstance(data.get("vehicles"), list):
                return data["vehicles"]
        return data if isinstance(data, list) else []

    def _resolve_vehicle(self) -> str:
        if self._vehicle_id:
            return self._vehicle_id
        vehicles = self._vehicles()
        if not vehicles:
            raise ProviderError("Keine Fahrzeuge im Opel-Connect-Konto gefunden")
        chosen = None
        if self.vin:
            for vehicle in vehicles:
                if str(pick(vehicle, "vin", default="")).upper() == self.vin.upper():
                    chosen = vehicle
                    break
        chosen = chosen or vehicles[0]
        self._vehicle_id = str(pick(chosen, "id", "vehicle_id", default=""))
        self.vin = str(pick(chosen, "vin", default=self.vin))
        if not self._label:
            self._label = str(
                pick(chosen, "label", "short_label", "shortLabel", "model", default="Opel")
            )
        if not self._vehicle_id:
            raise ProviderError("Fahrzeug ohne id in der API-Antwort")
        return self._vehicle_id

    # -------------------------------------------------------------- Provider
    def fetch(self) -> VehicleState:
        vehicle_id = self._resolve_vehicle()
        raw = self._api("/vehicles/%s/status" % vehicle_id)
        if not isinstance(raw, dict):
            raise ProviderError("Unerwartete Status-Antwort der Stellantis-API")
        return normalize_status(
            raw,
            vin=self.vin,
            name=self._label or "Opel",
            brand=str(self.cfg.get("brand", "Opel")),
            source="stellantis",
        )
