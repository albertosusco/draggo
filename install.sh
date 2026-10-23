#!/usr/bin/env bash
# Install Draggo (app + GNOME Shell extension).
#
#   ./install.sh            install for the current user (~/.local)
#   sudo ./install.sh --system   install for every user (/usr/local)
set -euo pipefail

APP_ID="io.github.albertosusco.Draggo"
EXT_UUID="draggo@albertosusco.github.io"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODE=user
if [[ "${1:-}" == "--system" ]]; then
    MODE=system
fi

if [[ $MODE == user ]]; then
    PREFIX="${PREFIX:-$HOME/.local}"
    DATADIR="${XDG_DATA_HOME:-$HOME/.local/share}"
    AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
else
    PREFIX="${PREFIX:-/usr/local}"
    DATADIR="$PREFIX/share"
    AUTOSTART_DIR="/etc/xdg/autostart"
fi
BINDIR="$PREFIX/bin"
PKGDATADIR="$DATADIR/draggo"
EXT_DIR="$DATADIR/gnome-shell/extensions/$EXT_UUID"

echo "==> Checking dependencies"
if ! python3 - <<'EOF'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
EOF
then
    echo "Missing dependencies. On Fedora install them with:" >&2
    echo "    sudo dnf install python3-gobject gtk4 libadwaita" >&2
    exit 1
fi

subst() {
    sed -e "s|@BINDIR@|$BINDIR|g" -e "s|@PKGDATADIR@|$PKGDATADIR|g" "$1" > "$2"
}

echo "==> Installing the app into $PREFIX"
install -d "$BINDIR" "$PKGDATADIR" "$DATADIR/applications" "$DATADIR/dbus-1/services" \
    "$DATADIR/icons/hicolor/scalable/apps" "$DATADIR/icons/hicolor/symbolic/apps" "$AUTOSTART_DIR"
rm -rf "$PKGDATADIR/draggo"
cp -r "$SRC/src/draggo" "$PKGDATADIR/draggo"
find "$PKGDATADIR/draggo" -name '__pycache__' -prune -exec rm -rf {} +

subst "$SRC/bin/draggo.in" "$BINDIR/draggo"
chmod 755 "$BINDIR/draggo"
subst "$SRC/data/$APP_ID.desktop.in" "$DATADIR/applications/$APP_ID.desktop"
subst "$SRC/data/$APP_ID.service.in" "$DATADIR/dbus-1/services/$APP_ID.service"
subst "$SRC/data/$APP_ID-autostart.desktop.in" "$AUTOSTART_DIR/$APP_ID.desktop"
install -m 644 "$SRC/data/icons/hicolor/scalable/apps/$APP_ID.svg" "$DATADIR/icons/hicolor/scalable/apps/"
install -m 644 "$SRC/data/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg" "$DATADIR/icons/hicolor/symbolic/apps/"

gtk-update-icon-cache -q -t -f "$DATADIR/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$DATADIR/applications" 2>/dev/null || true

echo "==> Installing the GNOME Shell extension into $EXT_DIR"
rm -rf "$EXT_DIR"
install -d "$EXT_DIR/schemas"
install -m 644 "$SRC/extension/$EXT_UUID/"{metadata.json,extension.js,prefs.js} "$EXT_DIR/"
install -m 644 "$SRC/extension/$EXT_UUID/schemas/"*.xml "$EXT_DIR/schemas/"
glib-compile-schemas "$EXT_DIR/schemas"

if [[ $MODE == user ]]; then
    # Let the session bus notice the new D-Bus service file.
    gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.ReloadConfig >/dev/null 2>&1 || true

    # Restart the app so the new version is used, then start it in the background.
    "$BINDIR/draggo" --quit >/dev/null 2>&1 || true
    (setsid "$BINDIR/draggo" --background >/dev/null 2>&1 &) || true

    if gnome-extensions enable "$EXT_UUID" 2>/dev/null; then
        echo "==> Extension enabled."
    else
        echo
        echo "GNOME Shell only discovers new extensions at login."
        echo "Log out and back in, then run:"
        echo "    gnome-extensions enable $EXT_UUID"
    fi
fi

echo
echo "Draggo installed. Start dragging something!"
