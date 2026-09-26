"""matprobe: check USB dance mats and write the pad bridge config.

    sudo python3 -m piddr.matprobe list    # mats, USB ports, HID type, polling
    sudo python3 -m piddr.matprobe watch   # live events, measured polling, chatter
    sudo python3 -m piddr.matprobe learn --out /etc/pi-ddr/padbridge.conf

Run as root: once the pad bridge's udev rule is installed, only root can open
the raw mats. Stop the bridge first (sudo systemctl stop pi-ddr-padbridge),
because it holds the mats exclusively while it runs.
"""

import argparse
import errno
import glob
import os
import selectors
import sys
import time

from . import evcodes, sysfs
from .config import BridgeConfig, PlayerConfig, format_config
from .mapping import AXIS_THRESHOLD, Mapper, Source, format_source
from .padbridge import VIRTUAL_VENDOR
from .timing import ChatterDetector, estimate_poll_interval

OPTIONAL_CONTROLS = ("start", "back", "select")
CORNER_CONTROLS = ("upleft", "upright", "downleft", "downright")
# BTN_0..9, joystick and gamepad buttons, d-pad buttons, BTN_TRIGGER_HAPPY*.
# Mouse buttons (0x110-0x117) are deliberately left out.
GAME_BUTTON_RANGES = ((0x100, 0x10A), (0x120, 0x13F), (0x220, 0x224), (0x2C0, 0x2E8))


def by_path_links():
    """Map /dev/input/eventN to its stable /dev/input/by-path link."""
    links = {}
    for link in sorted(glob.glob("/dev/input/by-path/*-event-*")):
        target = os.path.realpath(link)
        if target not in links or link.endswith("-event-joystick"):
            links[target] = link
    return links


def _natural_key(path):
    name = os.path.basename(path)
    digits = name[len(name.rstrip("0123456789")) :]
    return (name.rstrip("0123456789"), int(digits) if digits else -1)


def is_game_controller(caps):
    keys = caps.get(evcodes.EV_KEY, [])
    axes = [code for code, _ in caps.get(evcodes.EV_ABS, [])]
    has_buttons = any(lo <= k < hi for k in keys for lo, hi in GAME_BUTTON_RANGES)
    return has_buttons or evcodes.ABS_X in axes


def is_virtual_pad(dev):
    return dev.info.vendor == VIRTUAL_VENDOR and dev.name.startswith("pi-DDR")


def open_controllers(evdev, paths=None, include_virtual=False):
    """Open the given devices, or every game controller except our virtual pads."""
    opened, denied = [], []
    for path in paths or sorted(evdev.list_devices(), key=_natural_key):
        try:
            dev = evdev.InputDevice(path)
        except PermissionError:
            denied.append(path)
            continue
        except OSError as e:
            print(f"{path}: {e.strerror or e}", file=sys.stderr)
            continue
        caps = dev.capabilities(absinfo=True)
        wanted = bool(paths) or (is_game_controller(caps) and (include_virtual or not is_virtual_pad(dev)))
        if wanted:
            opened.append(dev)
        else:
            dev.close()
    if denied:
        print(f"permission denied for {len(denied)} device(s); run with sudo to see raw mats", file=sys.stderr)
    return opened


def grab_or_explain(dev):
    try:
        dev.grab()
        return True
    except OSError as e:
        if e.errno == errno.EBUSY:
            print(
                f"{dev.path} is held by another program (probably the pad bridge).\n"
                "  Stop it first: sudo systemctl stop pi-ddr-padbridge",
                file=sys.stderr,
            )
        else:
            print(f"{dev.path}: cannot grab: {e.strerror or e}", file=sys.stderr)
        return False


def _abs_ranges(dev):
    return {code: (info.min, info.max) for code, info in dev.capabilities(absinfo=True).get(evcodes.EV_ABS, [])}


# -- list ---------------------------------------------------------------------


def describe(dev, links, jspoll):
    info = sysfs.describe_event_device(os.path.basename(dev.path))
    caps = dev.capabilities(absinfo=True)
    buttons = caps.get(evcodes.EV_KEY, [])
    axes = [evcodes.abs_name(code) for code, _ in caps.get(evcodes.EV_ABS, [])]
    ids = f"{dev.info.vendor:04x}:{dev.info.product:04x}"
    lines = [f"{dev.path}  {dev.name!r}  {ids}  USB port {info['usb_port'] or '-'}"]
    lines.append(f"  by-path : {links.get(os.path.realpath(dev.path), '(none: not a USB port device)')}")
    lines.append(f"  inputs  : {len(buttons)} buttons; axes: {' '.join(axes) or 'none'}")
    if info["usb_port"] is None:
        return lines
    usage = info["hid_usage"]
    is_joystick = usage == sysfs.JOYSTICK_USAGE
    lines.append(
        f"  HID type: {sysfs.usage_name(usage)}"
        + (" (usbhid.jspoll can change its polling)" if is_joystick else " (usbhid.jspoll does NOT apply)")
    )
    native = info["poll_ms"]
    if native is None:
        lines.append("  polling : unknown")
        return lines
    text = f"  polling : bInterval {info['binterval']} -> every {native:g} ms on this Pi"
    if is_joystick and jspoll:
        forced = sysfs.xhci_poll_interval_ms(jspoll, info["speed_mbps"])
        text += f"; usbhid.jspoll={jspoll} forces {forced:g} ms (replug or reboot after changing it)"
    lines.append(text)
    if native > 1 and not (is_joystick and jspoll == 1):
        if is_joystick:
            lines.append("  advice  : add usbhid.jspoll=1 (pi/setup/configure-pi.sh does this) for 1 ms polling")
        else:
            lines.append("  advice  : jspoll cannot help; see docs/latency-and-sync.md, 'Mat polling'")
    return lines


def cmd_list(args):
    evdev = evcodes.require_evdev()
    links = by_path_links()
    jspoll = sysfs.usbhid_jspoll()
    devices = open_controllers(evdev, include_virtual=True)
    print(f"usbhid.jspoll = {jspoll if jspoll is not None else 'unknown'} (0 = each device's own rate)\n")
    if not devices:
        print("No game controllers found. Is the mat plugged in? (run with sudo to see hidden raw mats)")
        return 1
    for dev in devices:
        if is_virtual_pad(dev):
            print(f"{dev.path}  {dev.name!r}  virtual pad from pi-ddr-padbridge (this is what the game uses)\n")
        else:
            print("\n".join(describe(dev, links, jspoll)) + "\n")
        dev.close()
    return 0


# -- watch --------------------------------------------------------------------


class WatchState:
    def __init__(self, dev):
        self.dev = dev
        self.reports = []
        self.chatter = ChatterDetector()
        self.axes_used = set()


def print_summary(states):
    print()
    for st in states:
        est = estimate_poll_interval(st.reports)
        if est.interval_ms is None:
            polling = f"need more steps ({est.samples} usable gaps, want 20+)"
        else:
            polling = f"reports land on a {est.interval_ms:g} ms grid ({est.samples} gaps)"
        print(f"{st.dev.path} {st.dev.name!r}: {polling}")
        if st.chatter.hits:
            worst = min(gap for _, gap in st.chatter.hits) * 1000
            print(
                f"  chatter: {len(st.chatter.hits)} re-press(es) within 15 ms of a release (shortest {worst:.1f} ms)."
                " Set release_debounce_ms = 20 in the bridge config."
            )
        if st.axes_used:
            names = ", ".join(sorted(evcodes.abs_name(a) for a in st.axes_used))
            print(f"  arrows arrive on axes ({names}): check LEFT+RIGHT and UP+DOWN jumps both register.")


def cmd_watch(args):
    evdev = evcodes.require_evdev()
    devices = open_controllers(evdev, paths=args.devices)
    devices = [d for d in devices if grab_or_explain(d)]
    if not args.grab:
        for dev in devices:
            dev.ungrab()
    if not devices:
        return 1
    sel = selectors.DefaultSelector()
    states = []
    for dev in devices:
        st = WatchState(dev)
        states.append(st)
        sel.register(dev, selectors.EVENT_READ, st)
        print(f"watching {dev.path} {dev.name!r}")
    print("Step on the arrows in an uneven rhythm for about 30 seconds. Ctrl+C to stop.\n")
    start = time.time()
    next_summary = time.monotonic() + 10
    try:
        while True:
            for key, _ in sel.select(1.0):
                st = key.data
                try:
                    events = list(st.dev.read())
                except BlockingIOError:
                    continue
                except OSError as e:
                    print(f"{st.dev.path}: {e.strerror or e}; stopped watching it")
                    sel.unregister(st.dev)
                    continue
                for ev in events:
                    t = ev.timestamp()
                    tag = f"{t - start:9.3f}s  {os.path.basename(st.dev.path)}"
                    if ev.type == evcodes.EV_SYN and ev.code == evcodes.SYN_REPORT:
                        st.reports.append(t)
                    elif ev.type == evcodes.EV_KEY and ev.value in (0, 1):
                        gap = st.chatter.feed(t, ev.code, ev.value == 1)
                        note = f"   <- CHATTER {gap * 1000:.1f} ms after release" if gap is not None else ""
                        print(f"{tag}  {evcodes.key_name(ev.code):<20} {'down' if ev.value else 'up'}{note}")
                    elif ev.type == evcodes.EV_ABS:
                        st.axes_used.add(ev.code)
                        print(f"{tag}  {evcodes.abs_name(ev.code):<20} {ev.value}")
            if time.monotonic() >= next_summary:
                print_summary(states)
                print()
                next_summary = time.monotonic() + 10
    except KeyboardInterrupt:
        pass
    print_summary(states)
    return 0


# -- learn --------------------------------------------------------------------


class LearnDevice:
    def __init__(self, dev):
        self.dev = dev
        self.ranges = _abs_ranges(dev)
        self.pressed_axes = set()  # (code, direction) currently past the threshold

    def poll_press(self):
        """Return the first new press as a Source, or None."""
        found = None
        try:
            events = list(self.dev.read())
        except BlockingIOError:
            return None
        for ev in events:
            if ev.type == evcodes.EV_KEY and ev.value == 1 and found is None:
                found = Source("key", ev.code)
            elif ev.type == evcodes.EV_ABS and ev.code in self.ranges:
                lo, hi = self.ranges[ev.code]
                span = hi - lo
                norm = 2.0 * (ev.value - lo) / span - 1.0 if span > 0 else 0.0
                for direction in (-1, 1):
                    active = norm * direction > AXIS_THRESHOLD
                    if active and (ev.code, direction) not in self.pressed_axes:
                        self.pressed_axes.add((ev.code, direction))
                        if found is None:
                            found = Source("abs", ev.code, direction)
                    elif not active:
                        self.pressed_axes.discard((ev.code, direction))
        return found

    def wait_release(self, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.poll_press()
            if not self.dev.active_keys() and not self.pressed_axes:
                return
            time.sleep(0.02)


def wait_for_press(sel, allow_skip):
    """Block until a mat reports a press; returns (LearnDevice, Source) or (None, None) on Enter."""
    while True:
        for key, _ in sel.select(0.5):
            if key.data is None:
                sys.stdin.readline()
                if allow_skip:
                    return None, None
                continue
            source = key.data.poll_press()
            if source is not None:
                return key.data, source


def check_jump(learn_dev, mapping, first, second, timeout=10.0):
    """Ask for a two-arrow jump and report whether both arrows registered together."""
    mapper = Mapper(mapping, abs_ranges=learn_dev.ranges)
    print(f"  Now JUMP onto {first.upper()} and {second.upper()} together (Enter to skip)...", flush=True)
    end = time.monotonic() + timeout
    sel = selectors.DefaultSelector()
    sel.register(learn_dev.dev, selectors.EVENT_READ, learn_dev)
    sel.register(sys.stdin, selectors.EVENT_READ, None)
    try:
        while time.monotonic() < end:
            for key, _ in sel.select(0.2):
                if key.data is None:
                    sys.stdin.readline()
                    return None
                try:
                    events = list(learn_dev.dev.read())
                except BlockingIOError:
                    continue
                for ev in events:
                    if ev.type == evcodes.EV_SYN and ev.code == evcodes.SYN_REPORT:
                        mapper.flush(time.monotonic())
                        if {first, second} <= mapper.held():
                            learn_dev.wait_release()
                            return True
                    else:
                        mapper.feed(ev.type, ev.code, ev.value)
        return False
    finally:
        sel.close()


def learn_player(number, candidates, links, with_corners):
    sel = selectors.DefaultSelector()
    for cand in candidates:
        sel.register(cand.dev, selectors.EVENT_READ, cand)
    print(f"\nPLAYER {number}: stand on the mat you want as P{number}.")
    print("  Step on LEFT...", flush=True)
    chosen, source = wait_for_press(sel, allow_skip=False)
    sel.close()
    mapping = {"left": (source,)}
    print(f"    left  = {format_source(source)}   ({chosen.dev.path} {chosen.dev.name!r})")
    chosen.wait_release()

    sel = selectors.DefaultSelector()
    sel.register(chosen.dev, selectors.EVENT_READ, chosen)
    sel.register(sys.stdin, selectors.EVENT_READ, None)
    order = ["down", "up", "right"] + list(OPTIONAL_CONTROLS) + (list(CORNER_CONTROLS) if with_corners else [])
    for control in order:
        optional = control not in ("down", "up", "right")
        hint = " (Enter to skip)" if optional else ""
        print(f"  Press {control.upper()}{hint}...", flush=True)
        _, source = wait_for_press(sel, allow_skip=optional)
        if source is None:
            print(f"    {control} skipped")
            continue
        mapping[control] = (source,)
        print(f"    {control:<5} = {format_source(source)}")
        chosen.wait_release()
    sel.close()

    for first, second in (("left", "right"), ("up", "down")):
        ok = check_jump(chosen, mapping, first, second)
        if ok is False:
            print(
                f"  WARNING: {first}+{second} never registered together. This mat (or its current mode)"
                " cannot do those jumps; look for a mode switch or button combo on the mat."
            )
        elif ok:
            print(f"    {first}+{second} jump OK")

    link = links.get(os.path.realpath(chosen.dev.path))
    if link is None:
        print(f"  WARNING: {chosen.dev.path} has no /dev/input/by-path link; its number can change after a replug.")
        link = chosen.dev.path
    ids = (chosen.dev.info.vendor, chosen.dev.info.product)
    return PlayerConfig(number, link, mapping), chosen, ids


def cmd_learn(args):
    evdev = evcodes.require_evdev()
    devices = [d for d in open_controllers(evdev) if grab_or_explain(d)]
    if not devices:
        print("No mats found. Plug them into their P1/P2 ports and run this with sudo.", file=sys.stderr)
        return 1
    links = by_path_links()
    candidates = [LearnDevice(d) for d in devices]
    players, mat_ids = [], set()
    try:
        for number in range(1, args.players + 1):
            player, chosen, ids = learn_player(number, candidates, links, args.corners)
            players.append(player)
            mat_ids.add(ids)
            candidates = [c for c in candidates if c is not chosen]
            if number < args.players and not candidates:
                print("No other mat is connected for the next player.", file=sys.stderr)
                return 1
    finally:
        for dev in devices:
            dev.close()

    config = BridgeConfig(players=players, release_debounce_ms=args.debounce_ms, mat_ids=sorted(mat_ids))
    text = format_config(config)
    if not args.out:
        print("\n" + text)
        return 0
    if os.path.exists(args.out):
        os.replace(args.out, args.out + ".bak")
        print(f"\nprevious config kept as {args.out}.bak")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {args.out}. Apply it: sudo sh pi/padbridge/install.sh")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m piddr.matprobe", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list mats with USB port, HID type and polling interval")
    watch = sub.add_parser("watch", help="show live events and measure the real polling interval")
    watch.add_argument("devices", nargs="*", help="event devices to watch (default: all controllers)")
    watch.add_argument("--grab", action="store_true", help="keep other programs (the game) from seeing input")
    learn = sub.add_parser("learn", help="map the arrows of each mat and write the pad bridge config")
    learn.add_argument("--out", help="write the config here (default: print it)")
    learn.add_argument("--players", type=int, choices=(1, 2), default=2)
    learn.add_argument("--corners", action="store_true", help="also map the corner arrows (for 'solo' charts)")
    learn.add_argument("--debounce-ms", type=float, default=0.0, help="release_debounce_ms to write")
    args = parser.parse_args(argv)
    handler = {"list": cmd_list, "watch": cmd_watch, "learn": cmd_learn}[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
