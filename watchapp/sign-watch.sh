#!/usr/bin/env bash
# Packt und signiert die Watch-App fuer die GT-Serie.
#
# Warum nicht hvigor signieren lassen?
#  * hvigor akzeptiert nur von DevEco verschluesselte Passwoerter.
#  * Die GT-Uhren lehnen die von hvigor erzeugte config.json ab
#    ("Installation failed: 40. Invalid configuration file format") -
#    sie erwarten das klassische API-6-Format. Hier wird die config.json
#    deshalb umgeschrieben, bevor haptobin das .bin baut.
#
# Voraussetzung: ./build-watch.sh ist gelaufen; signing/ enthaelt
#   opelwatch.p12, keystore-password.txt, opelwatch-debug.cer, opelwatch-debug.p7b
#
#   ./sign-watch.sh [api]      api = compatible/target apiVersion, Standard 6
set -euo pipefail
cd "$(dirname "$0")"
API="${1:-6}"
DEVECO="${DEVECO_HOME:-/Applications/DevEco-Studio.app/Contents}"
J="$DEVECO/jbr/Contents/Home/bin/java"
TOOLCHAIN="$DEVECO/sdk/default/openharmony/toolchains/lib"
HAPTOBIN="$DEVECO/sdk/default/openharmony/js/build-tools/binary-tools/haptobin_tool.jar"
SRC=entry/build/default/intermediates/lite_source/default
OUT=entry/build/default/outputs/default
PW=$(cat signing/keystore-password.txt)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

cp -R "$SRC" "$WORK/src"
python3 - "$WORK/src/config.json" "$API" <<'PY'
import json, sys
p, api = sys.argv[1], int(sys.argv[2])
c = json.load(open(p))
c['app']['apiVersion'] = {"compatible": api, "target": api, "releaseType": "Release"}
c['app'].pop('appEnvironments', None)
c['deviceConfig'] = {}
m = c['module']
# Exakt das Format, das funktionierende GT-Apps benutzen (z. B. das
# Wear-Engine-Demo von minkiapps): Ability und JS-Bundle heissen "default",
# keine package/name/mainAbility-Felder.
m.pop('package', None); m.pop('name', None); m.pop('mainAbility', None)
for ab in m['abilities']:
    ab.pop('srcLanguage', None); ab.pop('srcPath', None)
    ab['name'] = 'default'
for js in m['js']:
    js['name'] = 'default'
json.dump(c, open(p, 'w'), indent=2, ensure_ascii=False)
PY

# Der GT-Bundle-Manager (gt_bundle_parser.cpp) verlangt im Media-Ordner des
# Icons genau "icon.bin" und "icon_small.bin"; die Toolchain erzeugt aber
# "<name>.png.bin". Deshalb hier umbenennen.
MEDIA="$WORK/src/assets/entry/resources/base/media"
cp "$MEDIA/icon.png.bin" "$MEDIA/icon.bin"
cp "$MEDIA/icon_small.png.bin" "$MEDIA/icon_small.bin"

"$J" -jar "$HAPTOBIN" --project-path "$WORK/src" --bin-path "$WORK/entry.bin" >/dev/null
SIGN="$J -jar $TOOLCHAIN/hap-sign-tool.jar sign-app -mode localSign -keyAlias opelwatch -keyPwd $PW \
  -appCertFile signing/opelwatch-debug.cer -profileFile signing/opelwatch-debug.p7b \
  -signAlg SHA256withECDSA -keystoreFile signing/opelwatch.p12 -keystorePwd $PW -compatibleVersion $API"
$SIGN -inFile "$WORK/entry.bin" -inForm bin -outFile "$WORK/entry-default-signed.bin" | grep -q "sign-app success"
( cd "$WORK" && rm -f hap.zip && zip -q -X hap.zip entry-default-signed.bin )
$SIGN -inFile "$WORK/hap.zip" -inForm zip -signCode 0 -outFile "$OUT/entry-default-signed.hap" | grep -q "sign-app success"
"$J" -jar "$TOOLCHAIN/hap-sign-tool.jar" verify-app -inFile "$OUT/entry-default-signed.hap" \
  -outCertChain "$WORK/c.cer" -outProfile "$WORK/p.p7b" | grep -q "verify-app success"
mkdir -p ../dist
cp "$OUT/entry-default-signed.hap" ../dist/OpelWatch-signed.hap
# Fuer den Datei-Installer von Gadgetbridge: das signierte .bin allein
# (HuaweiBinApp-Format), unter einer Endung, die der Installer annimmt.
cp "$WORK/entry-default-signed.bin" ../dist/OpelWatch.fw
echo "OK: ../dist/OpelWatch-signed.hap und ../dist/OpelWatch.fw (apiVersion $API)"
