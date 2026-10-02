#!/bin/sh
# Share OutFox's song folder on the home network (SMB), so song packs can be
# dragged onto the Pi from another computer. pi/install.sh installs Samba and
# runs this for you.
#
#   sudo sh pi/setup/songs-share.sh
#
# The share is \\HOSTNAME.local\Songs (in a file manager on macOS or Linux:
# smb://HOSTNAME.local/Songs), backed by ~/.project-outfox/Songs of the account
# that ran sudo. Signing in takes that user name and a Samba password, which is
# separate from the login password: the first run asks for it, and
# `sudo smbpasswd -a USER` changes it later. Files arrive owned by that user.
# Samba runs at a lower CPU priority, so a copy during a song gives way to the
# game. Safe to run again; it rewrites /etc/samba/pi-ddr-songs.conf each time.
set -eu

PLAYER=${SUDO_USER:-}
if [ "$(id -u)" != 0 ] || [ -z "$PLAYER" ] || [ "$PLAYER" = root ]; then
    echo "Run this with sudo from the account that plays: sudo sh pi/setup/songs-share.sh" >&2
    exit 1
fi
PLAYER_HOME=$(getent passwd "$PLAYER" | cut -d: -f6)
PLAYER_GROUP=$(id -gn "$PLAYER")
SONGS=$PLAYER_HOME/.project-outfox/Songs
SHARE_CONF=/etc/samba/pi-ddr-songs.conf
SMB_CONF=/etc/samba/smb.conf
DROP_IN=/etc/systemd/system/smbd.service.d/pi-ddr.conf

if ! command -v smbd >/dev/null 2>&1; then
    echo "Samba isn't installed. Run the installer, which installs it:" >&2
    echo "  sudo sh $(cd "$(dirname "$0")/.." && pwd)/install.sh" >&2
    exit 1
fi

sudo -u "$PLAYER" mkdir -p "$SONGS"

cat >"$SHARE_CONF" <<EOF
# pi-DDR: OutFox's song folder, shared for dragging in song packs.
# Written by pi/setup/songs-share.sh, which overwrites any edits here.
[Songs]
   comment = pi-DDR songs
   path = $SONGS
   valid users = $PLAYER
   force user = $PLAYER
   force group = $PLAYER_GROUP
   read only = no
   create mask = 0644
   directory mask = 0755
   # Desktop clutter that Windows and macOS write next to copied files.
   veto files = /._*/.DS_Store/Thumbs.db/desktop.ini/
   delete veto files = yes
EOF
echo "  wrote $SHARE_CONF"

if grep -qs "^include = $SHARE_CONF" "$SMB_CONF"; then
    echo "  $SMB_CONF already includes it"
else
    {
        echo
        echo "# pi-DDR: the Songs share"
        echo "include = $SHARE_CONF"
    } >>"$SMB_CONF"
    echo "  added an include line to $SMB_CONF"
fi
testparm -s >/dev/null 2>&1 || {
    echo "Samba rejects its configuration; see: testparm -s" >&2
    exit 1
}

mkdir -p "$(dirname "$DROP_IN")"
cat >"$DROP_IN" <<'EOF'
# pi-DDR: a copy running during a song yields the CPU to the game.
[Service]
Nice=10
EOF
systemctl daemon-reload
systemctl enable smbd.service >/dev/null 2>&1
systemctl restart smbd.service
echo "  smbd running at nice 10"

# smbpasswd -a can fail (the two entries don't match), so check Samba's user
# database afterwards rather than trusting it, and ask again.
if pdbedit -L -u "$PLAYER" >/dev/null 2>&1; then
    echo "  $PLAYER already has a Samba password"
elif [ -t 0 ]; then
    echo "  Choose the password other computers will use to open the share (user $PLAYER):"
    tries=0
    until pdbedit -L -u "$PLAYER" >/dev/null 2>&1; do
        if [ "$tries" -ge 3 ]; then
            echo "  No Samba password set for $PLAYER. Set one with: sudo smbpasswd -a $PLAYER" >&2
            exit 1
        fi
        tries=$((tries + 1))
        smbpasswd -a "$PLAYER" || echo "  Not set; try again." >&2
    done
    echo "  Samba password set for $PLAYER"
else
    echo "  No Samba password yet. Set one with: sudo smbpasswd -a $PLAYER"
fi
