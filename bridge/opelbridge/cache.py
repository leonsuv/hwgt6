"""Thread-sicherer Zustands-Cache mit Persistenz auf Platte."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class StateCache:
    def __init__(self, path: Optional[Path] = None):
        self._lock = threading.RLock()
        self._data: Optional[Dict[str, Any]] = None
        self._at: float = 0.0
        self._error: Optional[str] = None
        self._error_at: float = 0.0
        self._path = path
        if path and path.exists():
            try:
                stored = json.loads(path.read_text(encoding="utf-8"))
                self._data = stored.get("data")
                self._at = float(stored.get("at", 0))
            except (OSError, ValueError):
                pass

    def put(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self._data = data
            self._at = time.time()
            self._error = None
            self._persist()

    def put_error(self, message: str) -> None:
        with self._lock:
            self._error = message
            self._error_at = time.time()

    def get(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._data

    @property
    def age(self) -> float:
        with self._lock:
            return time.time() - self._at if self._at else float("inf")

    @property
    def error(self) -> Optional[str]:
        with self._lock:
            return self._error

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "has_data": self._data is not None,
                "age_s": None if not self._at else round(time.time() - self._at, 1),
                "last_error": self._error,
                "last_error_age_s": (
                    None if not self._error_at else round(time.time() - self._error_at, 1)
                ),
            }

    def _persist(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"at": self._at, "data": self._data}, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except OSError:
            pass
