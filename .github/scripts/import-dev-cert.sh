#!/usr/bin/env bash
# Import the owner's existing Apple Development identity (exported once as p12, stored as repo secrets) into a
# throwaway keychain, so Xcode's automatic signing reuses it instead of creating a new certificate per run.
set -euo pipefail
umask 077
: "${DEV_CERT_P12_B64:?}" "${DEV_CERT_P12_PASSWORD:?}"
WANT=7349C8092EFACA630074C6352EBB001E11B67497
KC="$RUNNER_TEMP/dev-signing.keychain-db"
KCP="$(openssl rand -hex 24)"; echo "::add-mask::$KCP"
printf '%s' "$DEV_CERT_P12_B64" | base64 --decode > "$RUNNER_TEMP/dev.p12"
security create-keychain -p "$KCP" "$KC"
security set-keychain-settings -lut 7200 "$KC"
security unlock-keychain -p "$KCP" "$KC"
security import "$RUNNER_TEMP/dev.p12" -k "$KC" -f pkcs12 -P "$DEV_CERT_P12_PASSWORD" -T /usr/bin/codesign -T /usr/bin/security -T /usr/bin/productbuild >/dev/null
rm -f "$RUNNER_TEMP/dev.p12"
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KCP" "$KC" >/dev/null
security list-keychains -d user -s "$KC" $(security list-keychains -d user | tr -d '"')
security find-identity -v -p codesigning "$KC" | grep -q "$WANT" || { echo "::error::expected development identity not in the imported p12"; exit 1; }
echo "dev identity imported: ${WANT:0:8}"
