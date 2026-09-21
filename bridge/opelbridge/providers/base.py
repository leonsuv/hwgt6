"""Provider-Basisklasse."""
from __future__ import annotations

from typing import Any, Dict, List

from ..model import VehicleState


class ProviderError(RuntimeError):
    """Fehler beim Abruf der Fahrzeugdaten."""


class AuthError(ProviderError):
    """Anmeldung / Token abgelaufen - Nutzer muss neu autorisieren."""


class Provider:
    name = "base"
    supports_commands: List[str] = []

    def __init__(self, cfg: Dict[str, Any], vin: str = ""):
        self.cfg = cfg or {}
        self.vin = vin

    def fetch(self) -> VehicleState:
        """Aktuellen Fahrzeugzustand holen (blockierend)."""
        raise NotImplementedError

    def command(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        raise ProviderError("Befehl '%s' wird von Provider '%s' nicht unterstuetzt"
                            % (name, self.name))

    def describe(self) -> Dict[str, Any]:
        return {"provider": self.name, "commands": list(self.supports_commands)}
