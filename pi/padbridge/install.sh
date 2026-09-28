#!/bin/sh
# Install or update the pi-DDR pad bridge. pi/install.sh runs this for you;
# run it directly only to update or remove just the bridge:
#
#   sudo sh pi/padbridge/install.sh              # install / apply config changes
#   sudo sh pi/padbridge/install.sh --uninstall
#
# Until the mats are mapped (`matprobe learn`) it installs the code and stops.
# Run it again afterwards, and whenever /etc/pi-ddr/padbridge.conf changes.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PI_DIR=$(dirname "$HERE")
PREFIX=/opt/pi-ddr
CONF_DIR=/etc/pi-ddr
CONF=$CONF_DIR/padbridge.conf
UNIT=/etc/systemd/system/pi-ddr-padbridge.service
RULES=/etc/udev/rules.d/65-pi-ddr-raw-mats.rules
MODULES=/etc/modules-load.d/pi-ddr-uinput.conf

if [ "$(id -u)" != 0 ]; then
    echo "Run with sudo." >&2
    exit 1
fi

reload_udev() {
    udevadm control --reload
    udevadm trigger --subsystem-match=input --action=change
}

if [ "${1:-}" = "--uninstall" ]; then
    systemctl disable --now pi-ddr-padbridge.service 2>/dev/null || true
    rm -f "$UNIT" "$RULES" "$MODULES"
    rm -rf "$PREFIX"
    systemctl daemon-reload
    reload_udev
    echo "Pad bridge removed (config kept in $CONF_DIR). Replug the mats or reboot."
    exit 0
fi

if ! python3 -c 'import evdev' 2>/dev/null; then
    apt-get install -y python3-evdev
fi

mkdir -p "$PREFIX" "$CONF_DIR"
rm -rf "$PREFIX/piddr"
cp -R "$PI_DIR/piddr" "$PREFIX/piddr"
rm -rf "$PREFIX/piddr/__pycache__"
echo uinput >"$MODULES"
modprobe uinput
echo "Installed code in $PREFIX."

if [ ! -f "$CONF" ]; then
    systemctl stop pi-ddr-padbridge.service 2>/dev/null || true
    echo
    echo "No $CONF yet. With both mats plugged into their P1/P2 ports, run:"
    echo "  sudo PYTHONPATH=$PREFIX python3 -m piddr.matprobe learn --out $CONF"
    echo "then run the installer again: sudo sh $PI_DIR/install.sh"
    exit 0
fi

PYTHONPATH=$PREFIX python3 -m piddr.padbridge --config "$CONF" --check

if PYTHONPATH=$PREFIX python3 -m piddr.padbridge --config "$CONF" --print-udev-rules >"$RULES.tmp"; then
    mv "$RULES.tmp" "$RULES"
    reload_udev
    echo "Installed $RULES (raw mats are now hidden from the game)."
else
    rm -f "$RULES.tmp"
    echo "Warning: no mat_ids in $CONF, so the game will also see the raw mats." >&2
fi

install -m 0644 "$HERE/pi-ddr-padbridge.service" "$UNIT"
systemctl daemon-reload
systemctl enable pi-ddr-padbridge.service
systemctl restart pi-ddr-padbridge.service
echo
echo "Pad bridge running. Replug both mats (or reboot) so the new permissions apply."
echo "Logs: journalctl -u pi-ddr-padbridge -f"
