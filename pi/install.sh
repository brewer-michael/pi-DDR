#!/bin/sh
# Install pi-DDR on a Raspberry Pi 4 running Raspberry Pi OS Lite (64-bit).
# Run it from the repo, as the account that will play:
#
#   sudo sh pi/install.sh
#
# Safe to run again at any time: after `git pull`, and after mapping the mats.
# Each run:
#   1. installs the packages pi-DDR needs;
#   2. applies the low-latency system settings (setup/configure-pi.sh);
#   3. installs the pad bridge, plus its udev rule once the mats are mapped
#      (padbridge/install.sh);
#   4. shares the song folder on the network (setup/songs-share.sh);
#   5. merges the recommended OutFox preferences (outfox/apply-prefs.sh);
#   6. makes the Pi boot straight into OutFox on the console.
# It doesn't download OutFox: unpack OutFox's Raspberry Pi build under
# ~/ProjectOutFox/ first (docs/latency-and-sync.md, "Setup, in order").
#
# PIDDR_VIDEO sets the HDMI mode (default 1920x1080@60).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
VIDEO=${PIDDR_VIDEO:-1920x1080@60}
PLAYER=${SUDO_USER:-}

if [ "$(id -u)" != 0 ] || [ -z "$PLAYER" ] || [ "$PLAYER" = root ]; then
    echo "Run this with sudo from the account that will play: sudo sh pi/install.sh" >&2
    exit 1
fi
PLAYER_HOME=$(getent passwd "$PLAYER" | cut -d: -f6)

step() { printf '\n== %s\n' "$*"; }

step "Packages"
apt-get update
apt-get install -y --no-install-recommends \
    xserver-xorg xinit x11-xserver-utils libgl1-mesa-dri \
    python3-evdev alsa-utils

step "System settings"
sh "$HERE/setup/configure-pi.sh" --video "$VIDEO"

step "Pad bridge"
sh "$HERE/padbridge/install.sh"

step "Song share"
sh "$HERE/setup/songs-share.sh"

step "OutFox preferences"
# OutFox rewrites Preferences.ini when it exits, and the console autologin
# restarts it as soon as it quits, so end that session first. The summary at
# the end says to reboot, which starts the game again.
if pgrep -u "$PLAYER" -x -i outfox >/dev/null 2>&1; then
    echo "Stopping the game on tty1 so its preferences can be updated."
    systemctl stop getty@tty1.service
    tries=0
    while pgrep -u "$PLAYER" -x -i outfox >/dev/null 2>&1 && [ "$tries" -lt 15 ]; do
        sleep 1
        tries=$((tries + 1))
    done
fi
if ! sudo -u "$PLAYER" -H sh "$HERE/outfox/apply-prefs.sh"; then
    echo "Skipped. With OutFox stopped, run: sh $HERE/outfox/apply-prefs.sh" >&2
fi

step "Boot into the game"
raspi-config nonint do_boot_behaviour B2 # console autologin for $SUDO_USER
PROFILE=$PLAYER_HOME/.profile
if grep -qs 'setup/xinitrc' "$PROFILE"; then
    echo "$PROFILE already starts the game on tty1"
else
    {
        echo
        echo '# pi-DDR: start the game on the console (tty1 only; SSH logins are unaffected)'
        echo "[ \"\$(tty)\" = /dev/tty1 ] && exec startx \"$HERE/setup/xinitrc\" -- -nocursor"
    } >>"$PROFILE"
    chown "$PLAYER": "$PROFILE"
    echo "Added the game autostart to $PROFILE"
fi

step "Status"
outfox=""
for candidate in "$PLAYER_HOME"/ProjectOutFox/*/[Oo]ut[Ff]ox; do
    if [ -f "$candidate" ] && [ -x "$candidate" ]; then
        outfox=$candidate
    fi
done
if [ -n "$outfox" ]; then
    echo "OutFox: $outfox"
else
    echo "OutFox: not found. Unpack its Raspberry Pi build under $PLAYER_HOME/ProjectOutFox/"
fi
if [ -f /etc/pi-ddr/padbridge.conf ]; then
    echo "Mats:   mapped (/etc/pi-ddr/padbridge.conf)"
else
    echo "Mats:   not mapped yet. With both mats in their P1/P2 ports, run:"
    echo "          cd $HERE && sudo python3 -m piddr.matprobe learn --out /etc/pi-ddr/padbridge.conf"
    echo "          sudo sh $HERE/install.sh"
fi
printf 'Songs:  \\\\%s.local\\Songs (SMB, user %s)\n' "$(hostname)" "$PLAYER"
echo "Then reboot to play: sudo reboot"
