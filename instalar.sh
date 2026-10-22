#!/bin/bash
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo 'Execute como root.' >&2; exit 1; }
VERSION='v1.4.0'
REPOSITORY='brsxdlols/mkauth-backup-telegram'
TEMP_DIR="$(mktemp -d /tmp/mka-backup-telegram.XXXXXXXX)"
trap 'rm -rf -- "$TEMP_DIR"' EXIT
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
 "https://github.com/$REPOSITORY/archive/refs/tags/$VERSION.tar.gz" -o "$TEMP_DIR/pacote.tar.gz"
tar -xzf "$TEMP_DIR/pacote.tar.gz" -C "$TEMP_DIR"
bash "$TEMP_DIR/mkauth-backup-telegram-${VERSION#v}/install.sh" "$@"
