#!/bin/sh
# Low-latency system settings for the pi-DDR Raspberry Pi 4.
#
#   sudo sh pi/setup/configure-pi.sh [--dry-run] [--video 1920x1080@60]
#
# What it changes (each step is explained in docs/latency-and-sync.md):
#   1. Kernel command line: usbhid.jspoll=1 (poll mats every 1 ms instead of
#      the 8 ms a typical cheap mat asks for) and usbcore.autosuspend=-1 (an
#      idle mat is never put to sleep). --video also pins the HDMI mode.
#   2. CPU governor "performance", so clocks don't ramp up mid-song.
#   3. Lets the audio group raise thread priority to nice -15, which OutFox's
#      ALSA mixer thread asks for (without it the request silently fails).
# Safe to run again; the original cmdline.txt is kept as cmdline.txt.pi-ddr.bak.
# Reboot afterwards.
set -eu

DRY_RUN=0
VIDEO=""

usage() {
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --video)
            if [ $# -lt 2 ]; then
                echo "--video needs a mode, for example --video 1920x1080@60" >&2
                exit 2
            fi
            shift
            VIDEO=$1
            case "$VIDEO" in
                *x*@*) ;;
                *)
                    echo "--video expects WIDTHxHEIGHT@HZ, for example 1920x1080@60 (got '$VIDEO')" >&2
                    exit 2
                    ;;
            esac
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "unknown option: $1" >&2
            exit 2
            ;;
    esac
    shift
done

say() { printf '%s\n' "$*"; }

write_file() { # path; content on stdin
    if [ "$DRY_RUN" = 1 ]; then
        say "  would write $1:"
        sed 's/^/    | /'
    else
        cat >"$1"
        say "  wrote $1"
    fi
}

if [ "$DRY_RUN" = 0 ] && [ "$(id -u)" != 0 ]; then
    say "Run with sudo (or add --dry-run to preview)."
    exit 1
fi

model="unknown machine"
[ -r /proc/device-tree/model ] && model=$(tr -d '\0' </proc/device-tree/model)
case "$model" in
    *"Raspberry Pi 4"*) say "Machine: $model" ;;
    *) say "Warning: this is '$model', not a Raspberry Pi 4. Continuing anyway." ;;
esac

# 1. Kernel command line --------------------------------------------------
CMDLINE=/boot/firmware/cmdline.txt
[ -f "$CMDLINE" ] || CMDLINE=/boot/cmdline.txt
if [ ! -f "$CMDLINE" ]; then
    say "Cannot find cmdline.txt; skipping kernel parameters."
else
    say "Kernel command line ($CMDLINE):"
    cmdline_set() { # $1 = prefix of the token to replace, $2 = token to set
        current=$(cat "$CMDLINE")
        case " $current " in
            *" $2 "*)
                say "  $2 (already set)"
                return
                ;;
        esac
        updated=$(printf '%s\n' "$current" | awk -v pre="$1" -v tok="$2" '{
            out = ""
            for (i = 1; i <= NF; i++) if (index($i, pre) != 1) out = out (out == "" ? "" : " ") $i
            print out (out == "" ? "" : " ") tok
        }')
        say "  $2"
        if [ "$DRY_RUN" = 0 ]; then
            [ -f "$CMDLINE.pi-ddr.bak" ] || cp "$CMDLINE" "$CMDLINE.pi-ddr.bak"
            # cmdline.txt must stay a single line.
            printf '%s\n' "$updated" >"$CMDLINE"
        fi
    }
    cmdline_set "usbhid.jspoll=" "usbhid.jspoll=1"
    cmdline_set "usbcore.autosuspend=" "usbcore.autosuspend=-1"
    if [ -n "$VIDEO" ]; then
        cmdline_set "video=HDMI-A-1:" "video=HDMI-A-1:$VIDEO"
    fi
fi

# 2. CPU governor ----------------------------------------------------------
say "CPU governor:"
write_file /etc/systemd/system/pi-ddr-cpu-performance.service <<'EOF'
[Unit]
Description=pi-DDR: keep the CPU at full clock (no ramp-up stutter mid-song)

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'for g in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do echo performance > "$g"; done'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
if [ "$DRY_RUN" = 0 ]; then
    systemctl daemon-reload
    systemctl enable --now pi-ddr-cpu-performance.service >/dev/null
    say "  now: $(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor 2>/dev/null || echo unknown)"
fi

# 3. Audio thread priority -------------------------------------------------
say "Audio thread priority:"
write_file /etc/security/limits.d/90-pi-ddr-audio.conf <<'EOF'
# pi-DDR: OutFox's ALSA mixer thread calls setpriority(-15). Allow it for
# members of the audio group so the mixer wins against rendering under load.
@audio   -   nice   -15
EOF
target_user="${SUDO_USER:-}"
if [ -n "$target_user" ] && [ "$target_user" != root ]; then
    if id -nG "$target_user" | tr ' ' '\n' | grep -qx audio; then
        say "  $target_user is in the audio group"
    elif [ "$DRY_RUN" = 1 ]; then
        say "  would add $target_user to the audio group"
    else
        usermod -aG audio "$target_user"
        say "  added $target_user to the audio group"
    fi
fi

say ""
if [ "$DRY_RUN" = 1 ]; then
    say "Dry run: nothing was changed."
else
    say "Done. Reboot, then check the mats with:"
    say "  cd pi && sudo python3 -m piddr.matprobe list"
fi
