"""Einstiegspunkt:  py -m opelbridge  [--provider mock] [--port 8787]"""
from __future__ import annotations

import argparse
import json
import socket
import sys

from .config import Config
from .providers import available
from .server import VehicleService, serve


def local_ip() -> str:
    """IP-Adresse im LAN ermitteln (ohne Internetverkehr)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="opelbridge",
        description="Bridge zwischen Opel Connect und der Huawei Watch GT6",
    )
    parser.add_argument("-c", "--config", help="Pfad zur config.json")
    parser.add_argument("--provider", choices=sorted(available()), help="Datenquelle")
    parser.add_argument("--port", type=int, help="TCP-Port (Standard 8787)")
    parser.add_argument("--host", help="Bind-Adresse (Standard 0.0.0.0)")
    parser.add_argument("--token", help="Shared Secret fuer die Uhr")
    parser.add_argument("--vin", help="VIN, falls mehrere Fahrzeuge im Konto")
    parser.add_argument("--allow-commands", action="store_true", help="Remote-Befehle erlauben")
    parser.add_argument("--once", action="store_true", help="Einmal abrufen, ausgeben, beenden")
    parser.add_argument("--watch-json", action="store_true", help="mit --once kompaktes Uhr-JSON")
    parser.add_argument("--print-url", action="store_true", help="Uhr-URL anzeigen und beenden")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    cfg = Config.load(args.config)
    if args.provider:
        cfg.provider = args.provider
    if args.port:
        cfg.port = args.port
    if args.host:
        cfg.host = args.host
    if args.token:
        cfg.token = args.token
    if args.vin:
        cfg.vin = args.vin
    if args.allow_commands:
        cfg.allow_commands = True
    if args.verbose:
        cfg.log_level = "debug"
    cfg.save()

    url = "http://%s:%d/api/v1/watch?t=%s" % (local_ip(), cfg.port, cfg.token)
    if args.print_url:
        print(url)
        return 0

    if args.once:
        import logging

        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
        service = VehicleService(cfg)
        data, error = service.refresh(force=True)
        if error:
            print("FEHLER: %s" % error, file=sys.stderr)
        if data is None:
            return 2
        payload = data if args.watch_json else service.full_state()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("=" * 64)
    print(" Opel Bridge fuer Huawei Watch GT6")
    print(" Provider : %s" % cfg.provider)
    print(" Uhr-URL  : %s" % url)
    print(" Diese URL in watchapp/.../common/config.js eintragen.")
    print("=" * 64)
    serve(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
