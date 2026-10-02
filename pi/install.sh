#!/bin/sh
# Install pi-DDR on a Raspberry Pi 4 running Raspberry Pi OS Lite (64-bit).
# Run it from the repo, as the account that will play:
#
#   sudo sh pi/install.sh
#
# Safe to run again: after `git pull`, and after mapping the mats. In order:
#   1. Packages: everything pi-DDR needs, in one apt run. Nothing else here
#      installs packages.
#   2. System settings: low-latency tuning (setup/configure-pi.sh).
#   3. Pad bridge, plus its udev rule once the mats are mapped
#      (padbridge/install.sh).
#   4. OutFox preferences (outfox/apply-prefs.sh).
#   5. Boot straight into OutFox on the console.
#   6. Song share (setup/songs-share.sh). It comes last because the first run
#      asks for the share's password.
#   7. Summary: what is left to do.
# It doesn't download OutFox: unpack OutFox's Raspberry Pi build under
# ~/ProjectOutFox/ first (docs/latency-and-sync.md, "Setup, in order").
#
# PIDDR_VIDEO sets the HDMI mode (default 1920x1080@60).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
VIDEO=${PIDDR_VIDEO:-1920x1080@60}
PLAYER=${SUDO_USER:-}

if [ "$(id -u)" != 0 ] || [ -z "$PLAYER" ] || [ "$PLAYER" = root ]; then
    echo "Run this with sudo from the account that will play: sudo sh $HERE/install.sh" >&2
    exit 1
fi
PLAYER_HOME=$(getent passwd "$PLAYER" | cut -d: -f6)

# The scripts called below leave next-step advice to the summary at the end.
PIDDR_INSTALLER=1
export PIDDR_INSTALLER

STEP=""
step() {
    STEP=$1
    printf '\n== %s\n' "$1"
}
# If any step fails (set -e), say where the run stopped and how to resume.
on_exit() {
    status=$?
    if [ "$status" != 0 ] && [ -n "$STEP" ]; then
        printf '\ninstall.sh stopped during "%s"; the steps after it did not run.\n' "$STEP" >&2
        printf 'Fix the error above, then run it again: sudo sh %s/install.sh\n' "$HERE" >&2
    fi
    exit "$status"
}
trap on_exit EXIT

step "Packages"
# Everything pi-DDR needs, in one apt run:
#   X for the game:      xserver-xorg xinit x11-xserver-utils libgl1-mesa-dri
#   OutFox's libraries:  libgl1 libfreetype6 libpulse0 libjack-jackd2-0 (ldd
#                        finds them missing on Pi OS Lite; libpulse0 and
#                        libjack-jackd2-0 are client libraries, no servers)
#   pad bridge:          python3-evdev
#   audio tools:         alsa-utils
#   song share:          samba (its recommends are AD domain controller and
#                        Python extras, which a file share doesn't use)
# DEBIAN_FRONTEND takes the default answer to samba-common's WINS question.
# DPkg::Lock::Timeout lets the install wait while Debian's apt-daily job holds
# the dpkg lock; apt-get update has no equivalent and fails at once instead.
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=60 install -y --no-install-recommends \
    xserver-xorg xinit x11-xserver-utils libgl1-mesa-dri \
    libgl1 libfreetype6 libpulse0 libjack-jackd2-0 \
    python3-evdev alsa-utils samba

step "System settings"
sh "$HERE/setup/configure-pi.sh" --video "$VIDEO"

step "Pad bridge"
sh "$HERE/padbridge/install.sh"

step "OutFox preferences"
# OutFox rewrites Preferences.ini when it exits, and the console autologin
# restarts it as soon as it quits, so end that session first. Rebooting at the
# end starts the game again.
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

step "Song share"
sh "$HERE/setup/songs-share.sh"

step "Summary"
outfox=""
for candidate in "$PLAYER_HOME"/ProjectOutFox/*/[Oo]ut[Ff]ox; do
    if [ -f "$candidate" ] && [ -x "$candidate" ]; then
        outfox=$candidate
    fi
done
if [ -n "$outfox" ]; then
    echo "OutFox: $outfox"
    missing=$(ldd "$outfox" 2>/dev/null | awk '/not found/ { printf "%s ", $1 }')
    if [ -n "$missing" ]; then
        echo "        can't start, libraries missing: $missing"
        echo "        (add their packages to the list at the top of $HERE/install.sh)"
    fi
else
    echo "OutFox: not found. Unpack its Raspberry Pi build under $PLAYER_HOME/ProjectOutFox/,"
    echo "        then run this again."
fi
if [ -f /etc/pi-ddr/padbridge.conf ]; then
    echo "Mats:   mapped (/etc/pi-ddr/padbridge.conf)"
else
    echo "Mats:   not mapped yet. With both mats in their P1/P2 ports, run:"
    echo "          cd $HERE && sudo python3 -m piddr.matprobe learn --out /etc/pi-ddr/padbridge.conf"
    echo "          sudo sh $HERE/install.sh"
fi
ip=$(hostname -I 2>/dev/null | awk '{ print $1 }')
printf 'Songs:  \\\\%s.local\\Songs' "$(hostname)"
if [ -n "$ip" ]; then
    printf ' or \\\\%s\\Songs' "$ip"
fi
if pdbedit -L -u "$PLAYER" >/dev/null 2>&1; then
    printf ' (SMB, user %s)\n' "$PLAYER"
else
    printf "\n        no Samba password for %s yet, so it won't open: sudo smbpasswd -a %s\n" "$PLAYER" "$PLAYER"
fi
echo "Reboot to play: sudo reboot"
