"""Provider-Registry."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .base import AuthError, Provider, ProviderError

__all__ = ["Provider", "ProviderError", "AuthError", "build_provider", "available"]


def available() -> Dict[str, str]:
    return {
        "opelapi": "Bibliothek 'opelapi' - eigener Login, Auto-Refresh, MQTT-Befehle (empfohlen)",
        "mock": "Simuliertes Fahrzeug - zum Testen ohne Opel-Konto",
        "psacc": "psa_car_controller (empfohlen) ueber dessen lokale REST-API",
        "stellantis": "Direkter Zugriff auf die Stellantis-/Opel-Connect-API",
    }


def build_provider(
    name: str,
    cfg: Dict[str, Any],
    vin: str = "",
    on_tokens: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Provider:
    key = (name or "mock").strip().lower()
    if key == "mock":
        from .mock import MockProvider

        return MockProvider(cfg, vin)
    if key in ("opelapi", "opel_api", "myopel"):
        from .opelapi_provider import OpelApiProvider

        return OpelApiProvider(cfg, vin)
    if key in ("psacc", "psa_car_controller", "psa"):
        from .psacc import PsaccProvider

        return PsaccProvider(cfg, vin)
    if key in ("stellantis", "opel", "psa_api"):
        from .stellantis import StellantisProvider

        return StellantisProvider(cfg, vin, on_tokens=on_tokens)
    raise ProviderError(
        "Unbekannter Provider '%s'. Verfuegbar: %s" % (name, ", ".join(available()))
    )
