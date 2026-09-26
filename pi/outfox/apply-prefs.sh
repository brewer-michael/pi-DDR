#!/bin/sh
# Merge pi-DDR's recommended settings into OutFox's Preferences.ini.
#
#   sh pi/outfox/apply-prefs.sh [path/to/Preferences.ini]
#
# Default target: ~/.project-outfox/Save/Preferences.ini. Run it as the user
# who plays (not root) while OutFox is closed: OutFox rewrites the file on exit.
# Keys already present are replaced in place; missing ones are added to
# [Options]. Everything else in the file is left alone. A backup is kept as
# Preferences.ini.bak.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
SETTINGS=$HERE/pi-ddr.prefs
TARGET=${1:-$HOME/.project-outfox/Save/Preferences.ini}

if pgrep -x OutFox >/dev/null 2>&1; then
    echo "OutFox is running; quit it first (it overwrites Preferences.ini on exit)." >&2
    exit 1
fi

mkdir -p "$(dirname "$TARGET")"
[ -f "$TARGET" ] || : >"$TARGET"
cp "$TARGET" "$TARGET.bak"

awk -v settings="$SETTINGS" '
function key_of(line) { return substr(line, 1, index(line, "=") - 1) }
function add_missing(   i) {
    for (i = 1; i <= n; i++)
        if (!(order[i] in done)) { print want[order[i]]; done[order[i]] = 1 }
}
# Blank lines are held back so new keys land before the gap, not after it.
function flush_blanks() { printf "%s", blanks; blanks = "" }
BEGIN {
    while ((getline line < settings) > 0)
        if (line ~ /^[A-Za-z0-9]+=/) { k = key_of(line); want[k] = line; order[++n] = k }
}
/^[ \t\r]*$/ { blanks = blanks $0 "\n"; next }
/^\[/ {
    if (in_options) add_missing()
    flush_blanks()
    in_options = ($0 == "[Options]")
    if (in_options) seen = 1
    print
    next
}
{ flush_blanks() }
in_options && /^[A-Za-z0-9]+=/ {
    k = key_of($0)
    if (k in want) { print want[k]; done[k] = 1; next }
}
{ print }
END {
    if (in_options) add_missing()
    flush_blanks()
    if (!seen) { print "[Options]"; add_missing() }
}
' "$TARGET.bak" >"$TARGET"

echo "Updated $TARGET (backup: $TARGET.bak):"
grep -v '^#' "$SETTINGS" | grep '=' | sed 's/^/  /'
