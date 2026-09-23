#!/usr/bin/env bash
# Baut "Gadgetbridge (opel)": Upstream-Gadgetbridge + hwgt6-opel.patch.
#
#   ./build.sh            klont Gadgetbridge nach ./src (einmalig), wendet den
#                         Patch an und baut die Debug-APK
#   ./build.sh --install  zusaetzlich per adb auf das Telefon installieren
#
# Voraussetzungen: git, OpenJDK 21 (mit jlink), Android SDK mit
# "platforms;android-37.0" und "build-tools;37.0.0".
set -euo pipefail

cd "$(dirname "$0")"
HERE="$PWD"

# Getesteter Upstream-Stand (Gadgetbridge master vom 2026-09-21)
UPSTREAM=https://codeberg.org/Freeyourgadget/Gadgetbridge.git
COMMIT=e2ef406cd6219f0cbefef3d9ef25abe6f745917a

: "${JAVA_HOME:=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home}"
: "${ANDROID_HOME:=$HOME/Library/Android/sdk}"
export JAVA_HOME ANDROID_HOME

if [ ! -d src/.git ]; then
  echo "==> Gadgetbridge klonen (einmalig, dauert etwas)"
  git clone --filter=blob:none "$UPSTREAM" src
fi

cd src
if ! git diff --quiet || [ -n "$(git ls-files --others --exclude-standard app/src)" ]; then
  echo "==> src/ enthaelt schon Aenderungen - Patch wird nicht erneut angewendet"
else
  echo "==> Stand $COMMIT auschecken und Patch anwenden"
  git checkout -q --detach "$COMMIT"
  git apply "$HERE/hwgt6-opel.patch"
fi

echo "==> Bauen (mainline, debug)"
./gradlew :app:assembleMainlineDebug -x lint --no-daemon \
  -Porg.gradle.java.installations.paths="$JAVA_HOME"

APK="$PWD/app/build/outputs/apk/mainline/debug/app-mainline-debug.apk"
mkdir -p "$HERE/../dist"
cp "$APK" "$HERE/../dist/Gadgetbridge-gt6-opel.apk"
echo "==> Fertig: dist/Gadgetbridge-gt6-opel.apk"

if [ "${1:-}" = "--install" ]; then
  "$ANDROID_HOME/platform-tools/adb" install -r "$HERE/../dist/Gadgetbridge-gt6-opel.apk"
fi
