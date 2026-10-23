#!/usr/bin/env bash
# Remove Draggo. Use the same options you used for install.sh.
set -euo pipefail

APP_ID="io.github.albertosusco.Draggo"
EXT_UUID="draggo@albertosusco.github.io"

if [[ "${1:-}" == "--system" ]]; then
    PREFIX="${PREFIX:-/usr/local}"
    DATADIR="$PREFIX/share"
    AUTOSTART_DIR="/etc/xdg/autostart"
else
    PREFIX="${PREFIX:-$HOME/.local}"
    DATADIR="${XDG_DATA_HOME:-$HOME/.local/share}"
    AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
    gnome-extensions disable "$EXT_UUID" 2>/dev/null || true
    "$PREFIX/bin/draggo" --quit >/dev/null 2>&1 || true
fi

rm -f "$PREFIX/bin/draggo" \
      "$DATADIR/applications/$APP_ID.desktop" \
      "$DATADIR/dbus-1/services/$APP_ID.service" \
      "$AUTOSTART_DIR/$APP_ID.desktop" \
      "$DATADIR/icons/hicolor/scalable/apps/$APP_ID.svg" \
      "$DATADIR/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg"
rm -rf "$DATADIR/draggo/draggo" "$DATADIR/gnome-shell/extensions/$EXT_UUID"
rmdir "$DATADIR/draggo" 2>/dev/null || true

echo "Draggo removed. Your shelf contents in ~/.local/share/draggo were left in place."
