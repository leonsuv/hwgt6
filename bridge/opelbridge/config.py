"""Konfiguration der Bridge (JSON-Datei + Umgebungsvariablen)."""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG_NAME = "config.json"


@dataclass
class Config:
    provider: str = "mock"                     # mock | psacc | stellantis
    host: str = "0.0.0.0"
    port: int = 8787
    token: str = ""                            # Shared Secret fuer die Uhr
    poll_interval_s: int = 300                 # Hintergrund-Abfrage der Opel-API
    cache_ttl_s: int = 120                     # Mindestalter vor Neuabfrage
    vin: str = ""                              # leer = erstes Fahrzeug
    units: str = "metric"
    log_level: str = "info"
    allow_commands: bool = False               # Remote-Befehle (Vorklima, Wakeup)
    tls_cert: str = ""
    tls_key: str = ""
    opelapi: Dict[str, Any] = field(default_factory=dict)
    psacc: Dict[str, Any] = field(default_factory=dict)
    stellantis: Dict[str, Any] = field(default_factory=dict)
    mock: Dict[str, Any] = field(default_factory=dict)
    _path: Optional[Path] = None

    # ---------------------------------------------------------------- laden
    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        cfg = cls()
        p = Path(path) if path else Path(__file__).resolve().parent.parent / DEFAULT_CONFIG_NAME
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            cfg.apply(raw)
        cfg._path = p
        cfg.apply_env()
        if not cfg.token:
            cfg.token = secrets.token_urlsafe(18)
            cfg.save()
        return cfg

    def apply(self, raw: Dict[str, Any]) -> None:
        for key, value in raw.items():
            if key.startswith("_") or key.startswith("//"):
                continue
            if hasattr(self, key):
                setattr(self, key, value)

    def apply_env(self) -> None:
        mapping = {
            "OPELBRIDGE_PROVIDER": ("provider", str),
            "OPELBRIDGE_HOST": ("host", str),
            "OPELBRIDGE_PORT": ("port", int),
            "OPELBRIDGE_TOKEN": ("token", str),
            "OPELBRIDGE_VIN": ("vin", str),
            "OPELBRIDGE_POLL": ("poll_interval_s", int),
            "OPELBRIDGE_CACHE_TTL": ("cache_ttl_s", int),
            "OPELBRIDGE_LOG": ("log_level", str),
        }
        for env, (attr, cast) in mapping.items():
            value = os.environ.get(env)
            if value:
                try:
                    setattr(self, attr, cast(value))
                except ValueError:
                    pass
        if os.environ.get("OPELBRIDGE_ALLOW_COMMANDS", "").lower() in ("1", "true", "yes"):
            self.allow_commands = True

    # -------------------------------------------------------------- sichern
    def save(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def public(self) -> Dict[str, Any]:
        """Konfiguration ohne Geheimnisse - fuer /api/v1/info."""
        return {
            "provider": self.provider,
            "poll_interval_s": self.poll_interval_s,
            "cache_ttl_s": self.cache_ttl_s,
            "units": self.units,
            "vin": (self.vin[-6:] if self.vin else ""),
            "allow_commands": self.allow_commands,
        }
