"""HTTP-Bridge zwischen Opel Connect und der Huawei Watch GT6.

Nur Standardbibliothek - laeuft auf jedem Rechner mit Python 3.8+ ohne
pip-Installation.
"""
from __future__ import annotations

import hmac
import json
import logging
import ssl
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from .cache import StateCache
from .config import Config
from .model import VehicleState
from .providers import AuthError, Provider, ProviderError, available, build_provider

LOG = logging.getLogger("opelbridge")
API_PREFIX = "/api/v1"


class VehicleService:
    """Haelt den Provider, den Cache und den Hintergrund-Poller zusammen."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        state_file = Path(__file__).resolve().parent.parent / "state.json"
        self.cache = StateCache(state_file)
        self._fetch_lock = threading.Lock()
        self._stop = threading.Event()
        self._provider: Optional[Provider] = None
        self._provider_error: Optional[str] = None
        self._last_full: Optional[Dict[str, Any]] = None
        self._build_provider()

    # ------------------------------------------------------------- Provider
    def _persist_tokens(self, tokens: Dict[str, Any]) -> None:
        self.cfg.stellantis.update(tokens)
        self.cfg.save()
        LOG.info("Neues refresh_token gespeichert")

    def _build_provider(self) -> None:
        cfg = self.cfg
        provider_cfg = {
            "opelapi": cfg.opelapi,
            "mock": cfg.mock,
            "psacc": cfg.psacc,
            "stellantis": cfg.stellantis,
        }.get(cfg.provider.lower(), {})
        try:
            self._provider = build_provider(
                cfg.provider, provider_cfg or {}, cfg.vin, on_tokens=self._persist_tokens
            )
            self._provider_error = None
            LOG.info("Provider '%s' aktiv", cfg.provider)
        except ProviderError as exc:
            self._provider = None
            self._provider_error = str(exc)
            LOG.error("Provider '%s' nicht startbar: %s", cfg.provider, exc)

    # ---------------------------------------------------------------- Daten
    def refresh(self, force: bool = False) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Holt Daten, wenn der Cache zu alt ist. Gibt (state, fehler) zurueck."""
        if not force and self.cache.age < self.cfg.cache_ttl_s:
            return self.cache.get(), self.cache.error

        if not self._fetch_lock.acquire(timeout=30):
            return self.cache.get(), "Abruf laeuft bereits"
        try:
            if not force and self.cache.age < self.cfg.cache_ttl_s:
                return self.cache.get(), self.cache.error
            if self._provider is None:
                self._build_provider()
            if self._provider is None:
                error = self._provider_error or "Kein Provider konfiguriert"
                self.cache.put_error(error)
                return self.cache.get(), error
            try:
                state: VehicleState = self._provider.fetch()
                full = state.to_json()
                self._last_full = full
                self.cache.put(state.to_watch())
                LOG.info(
                    "Daten aktualisiert: %s %s%% / %s km",
                    full["vehicle"]["name"],
                    full["energy"]["level"],
                    full["energy"]["range_km"],
                )
                return self.cache.get(), None
            except AuthError as exc:
                LOG.error("Anmeldung abgelaufen: %s", exc)
                self.cache.put_error("auth: %s" % exc)
                return self.cache.get(), "auth: %s" % exc
            except Exception as exc:                       # noqa: BLE001 - nie crashen
                LOG.warning("Abruf fehlgeschlagen: %s", exc)
                self.cache.put_error(str(exc))
                return self.cache.get(), str(exc)
        finally:
            self._fetch_lock.release()

    def full_state(self) -> Optional[Dict[str, Any]]:
        self.refresh()
        return self._last_full

    def command(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.cfg.allow_commands:
            raise ProviderError("Befehle sind deaktiviert (allow_commands=false)")
        if self._provider is None:
            raise ProviderError(self._provider_error or "Kein Provider konfiguriert")
        result = self._provider.command(name, args)
        self.refresh(force=True)
        return result

    def info(self) -> Dict[str, Any]:
        provider_info: Dict[str, Any] = {"error": self._provider_error}
        if self._provider is not None:
            provider_info.update(self._provider.describe())
        return {
            "ok": self._provider_error is None,
            "config": self.cfg.public(),
            "provider": provider_info,
            "cache": self.cache.stats(),
            "providers_available": available(),
            "server_time": int(time.time()),
        }

    # --------------------------------------------------------------- Poller
    def start_poller(self) -> None:
        def loop() -> None:
            # Erster Abruf sofort, danach im Intervall
            while not self._stop.is_set():
                try:
                    self.refresh(force=True)
                except Exception as exc:                    # noqa: BLE001
                    LOG.warning("Poller-Fehler: %s", exc)
                self._stop.wait(max(30, self.cfg.poll_interval_s))

        thread = threading.Thread(target=loop, name="opel-poller", daemon=True)
        thread.start()

    def stop(self) -> None:
        self._stop.set()


class Handler(BaseHTTPRequestHandler):
    server_version = "OpelBridge/1.0"
    service: VehicleService                     # wird in serve() gesetzt
    config: Config

    # ------------------------------------------------------------- Helfer
    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: int, payload: Any, content_type: str = "application/json") -> None:
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        elif isinstance(payload, bytes):
            body = payload
        else:
            body = str(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-Token, Authorization, Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _query(self) -> Dict[str, str]:
        parsed = urllib.parse.urlparse(self.path)
        return {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

    def _authorized(self, query: Dict[str, str]) -> bool:
        expected = self.config.token
        if not expected:
            return True
        supplied = (
            self.headers.get("X-Token")
            or query.get("t")
            or query.get("token")
            or ""
        )
        auth = self.headers.get("Authorization", "")
        if not supplied and auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
        return hmac.compare_digest(str(supplied), str(expected))

    def _is_local(self) -> bool:
        return self.client_address[0] in ("127.0.0.1", "::1", "localhost")

    # ------------------------------------------------------------- Routing
    def do_OPTIONS(self) -> None:                                   # noqa: N802
        self._send(204, b"")

    def do_HEAD(self) -> None:                                      # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:                                      # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:                                       # noqa: N802
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        query = self._query()

        if path in ("/health", API_PREFIX + "/health"):
            self._send(200, {"ok": True, "t": int(time.time())})
            return

        if path == "/":
            self._send(200, self._index_html(), "text/html")
            return

        if path == "/preview":
            self._send_preview()
            return

        if path == "/preview/util.js":
            self._send_watch_util()
            return

        if not path.startswith(API_PREFIX):
            self._send(404, {"error": "not_found", "path": path})
            return

        if not self._authorized(query):
            self._send(401, {"error": "unauthorized", "hint": "X-Token Header oder ?t=<token>"})
            return

        route = path[len(API_PREFIX):] or "/"
        force = query.get("force") in ("1", "true", "yes")

        if route == "/watch":
            data, error = self.service.refresh(force=force)
            if data is None:
                self._send(503, {"error": "no_data", "detail": error or "noch keine Daten"})
                return
            payload = dict(data)
            now = int(time.time())
            payload["age"] = payload.get("age", 0) + max(0, now - int(payload.get("ts", now)))
            payload["ts"] = now
            payload["cache_s"] = int(self.service.cache.age)
            if error:
                payload["err"] = error[:120]
            self._send(200, payload)
            return

        if route == "/state":
            data = self.service.full_state()
            if data is None:
                self._send(503, {"error": "no_data", "detail": self.service.cache.error})
                return
            self._send(200, data)
            return

        if route == "/refresh":
            data, error = self.service.refresh(force=True)
            self._send(200 if data else 503, {"ok": error is None, "error": error, "data": data})
            return

        if route == "/info":
            self._send(200, self.service.info())
            return

        if route.startswith("/command/"):
            name = route[len("/command/"):]
            args = dict(query)
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                raw = self.rfile.read(length).decode("utf-8", "replace")
                try:
                    body = json.loads(raw)
                    if isinstance(body, dict):
                        args.update(body)
                except json.JSONDecodeError:
                    args.update({k: v[0] for k, v in urllib.parse.parse_qs(raw).items()})
            try:
                self._send(200, self.service.command(name, args))
            except ProviderError as exc:
                self._send(501, {"ok": False, "error": str(exc)})
            except Exception as exc:                                # noqa: BLE001
                self._send(500, {"ok": False, "error": str(exc)})
            return

        self._send(404, {"error": "not_found", "path": path})

    # -------------------------------------------------------------- Seiten
    def _send_preview(self) -> None:
        preview = Path(__file__).resolve().parent.parent.parent / "tools" / "preview.html"
        if not preview.exists():
            self._send(404, {"error": "preview.html fehlt"})
            return
        self._send(200, preview.read_bytes(), "text/html")

    def _send_watch_util(self) -> None:
        """Liefert die Formatierlogik der Uhr an die Browser-Vorschau.

        Damit rechnen Uhr und Vorschau garantiert mit demselben Code; das
        ES-Modul-Schlusswort wird fuer den Browser entfernt.
        """
        root = Path(__file__).resolve().parent.parent.parent
        util = root / "watchapp" / "entry" / "src" / "main" / "js" / "default" / "common" / "util.js"
        if not util.exists():
            self._send(404, {"error": "util.js nicht gefunden", "pfad": str(util)})
            return
        source = util.read_text(encoding="utf-8").replace("export default UTIL;", "")
        source += "\nwindow.UTIL = UTIL;\n"
        self._send(200, source.encode("utf-8"), "application/javascript")

    def _index_html(self) -> str:
        info = self.service.info()
        token_line = (
            "<p><b>Token:</b> <code>%s</code></p>" % self.config.token
            if self._is_local()
            else "<p><b>Token:</b> nur lokal sichtbar</p>"
        )
        cache = info["cache"]
        return """<!doctype html><html lang="de"><meta charset="utf-8">
<title>Opel Bridge</title>
<style>
 body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:2rem;line-height:1.6}
 code{background:#222;padding:.15rem .4rem;border-radius:4px}
 a{color:#f5a623} .ok{color:#3ddc84} .bad{color:#ff6b6b}
 table{border-collapse:collapse;margin:1rem 0} td{padding:.2rem .8rem .2rem 0;vertical-align:top}
</style>
<h1>Opel Bridge <span class="%s">%s</span></h1>
<p>Datenquelle fuer die Huawei Watch GT6.</p>
%s
<table>
<tr><td>Provider</td><td><code>%s</code></td></tr>
<tr><td>Cache-Alter</td><td>%s s</td></tr>
<tr><td>Letzter Fehler</td><td>%s</td></tr>
<tr><td>Befehle</td><td>%s</td></tr>
</table>
<p>Endpunkte:
<a href="/api/v1/watch?t=%s">/api/v1/watch</a> &middot;
<a href="/api/v1/state?t=%s">/api/v1/state</a> &middot;
<a href="/api/v1/info?t=%s">/api/v1/info</a> &middot;
<a href="/preview?t=%s">UI-Vorschau</a></p>
""" % (
            "ok" if info["ok"] else "bad",
            "bereit" if info["ok"] else "Fehler",
            token_line,
            self.config.provider,
            cache.get("age_s"),
            cache.get("last_error") or "-",
            "aktiv" if self.config.allow_commands else "deaktiviert",
            self.config.token if self._is_local() else "",
            self.config.token if self._is_local() else "",
            self.config.token if self._is_local() else "",
            self.config.token if self._is_local() else "",
        )


def serve(cfg: Config) -> None:
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    service = VehicleService(cfg)
    service.start_poller()

    handler: Callable[..., BaseHTTPRequestHandler] = type(
        "BoundHandler", (Handler,), {"service": service, "config": cfg}
    )
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), handler)

    scheme = "http"
    if cfg.tls_cert and cfg.tls_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cfg.tls_cert, cfg.tls_key)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"

    LOG.info("Bridge laeuft auf %s://%s:%d  (Provider: %s)", scheme, cfg.host, cfg.port, cfg.provider)
    LOG.info("Uhr-Endpunkt: %s://<IP>:%d%s/watch?t=%s", scheme, cfg.port, API_PREFIX, cfg.token)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Beende Bridge")
    finally:
        service.stop()
        httpd.server_close()
