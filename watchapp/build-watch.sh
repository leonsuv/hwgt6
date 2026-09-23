#!/usr/bin/env bash
# Baut die Watch-App von der Kommandozeile mit dem in DevEco Studio
# mitgelieferten hvigor - ohne die IDE zu oeffnen.
#
#   ./build-watch.sh            debug (unsigniert, wenn keine signingConfigs)
#   ./build-watch.sh release
#
# Der hvigor-Wrapper (hvigorw) will hvigor aus dem Huawei-Registry laden, was
# ohne ohpm-Konfiguration scheitert. Deshalb wird hier direkt das gebuendelte
# hvigor aus DevEco Studio benutzt.
set -euo pipefail
cd "$(dirname "$0")"

DEVECO="${DEVECO_HOME:-/Applications/DevEco-Studio.app/Contents}"
[ -d "$DEVECO" ] || { echo "DevEco Studio nicht gefunden unter $DEVECO (DEVECO_HOME setzen)"; exit 1; }

export DEVECO_SDK_HOME="$DEVECO/sdk"
export NODE_HOME="$DEVECO/tools/node"

# Shim, damit hvigor sein Plugin unter @ohos/... findet
SHIM="${TMPDIR:-/tmp}/hwgt6-hvigor-shim/node_modules/@ohos"
mkdir -p "$SHIM"
ln -sfn "$DEVECO/tools/hvigor/hvigor" "$SHIM/hvigor"
ln -sfn "$DEVECO/tools/hvigor/hvigor-ohos-plugin" "$SHIM/hvigor-ohos-plugin"
export NODE_PATH="$(dirname "$SHIM")"

MODE="${1:-debug}"
"$NODE_HOME/bin/node" "$DEVECO/tools/hvigor/hvigor/bin/hvigor.js" \
  assembleHap --mode module -p product=default -p buildMode="$MODE" --no-daemon

echo
echo "Ergebnis:"
ls -la entry/build/default/outputs/default/*.hap
