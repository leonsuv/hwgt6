#!/bin/sh
# Opel Bridge starten (Linux / macOS)
set -e
cd "$(dirname "$0")"

[ -f config.json ] || cp config.example.json config.json

exec python3 -m opelbridge "$@"
