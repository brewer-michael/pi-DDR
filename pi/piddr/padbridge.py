"""pi-DDR pad bridge: two physical mats in, two stable virtual pads out.

OutFox (like the StepMania 5.1 code it grew from) numbers pads in the order
Linux registered them. A replug, or a different boot order, can swap P1 and
P2. This daemon creates the virtual pads "pi-DDR P1" and "pi-DDR P2" at boot,
always in that order, and feeds each from the mat in one fixed USB port. The
virtual pads never go away, so the game's numbering stays put even when a mat
is unplugged mid-song.

Runs as the systemd service pi-ddr-padbridge (see pi/padbridge/).
"""

import argparse
import errno
import gc
import glob
import os
import selectors
import signal
import sys
import time

from . import evcodes, sysfs
from .config import ConfigError, load_config, udev_rules
from .mapping import VIRTUAL_BUTTONS, Mapper
from .timing import DelayStats

DEFAULT_CONFIG = "/etc/pi-ddr/padbridge.conf"
VIRTUAL_VENDOR = 0x1209  # pid.codes vendor; these devices never appear on a real bus
VIRTUAL_PRODUCTS = {1: 0x0001, 2: 0x0002}
PLACEHOLDER_PRODUCT = 0x0003
VIRTUAL_NAME = "pi-DDR P{}"
RESCAN_INTERVAL = 1.0
MAX_ORDER_ATTEMPTS = 8


def _trailing_number(name):
    digits = name[len(name.rstrip("0123456789")) :]
    return int(digits) if digits else -1


def sorts_before(a, b):
    """True if sysfs name ``a`` comes first both as text and as a number.

    Games sort ``input9`` after ``input10`` when they compare names as text,
    so the P1 pad must win under both orderings.
    """
    return a < b and _trailing_number(a) < _trailing_number(b)


class Player:
    def __init__(self, config, pad, release_debounce):
        self.config = config
        self.pad = pad
        self.mapper = Mapper(config.mapping, release_debounce=release_debounce)
        self.dev = None
        self.dropped = False
        self.last_note = None

    @property
    def label(self):
        return f"P{self.config.number}"


class Bridge:
    def __init__(self, config, evdev, log=None, selector=None, clock=time.monotonic, wallclock=time.time):
        self.config = config
        self.evdev = evdev
        self.log = log or (lambda msg: print(msg, flush=True))
        self.selector = selector or selectors.DefaultSelector()
        self.clock = clock
        self.wallclock = wallclock
        self.delays = DelayStats()
        self.players = []
        self.pads = {}
        self.stop_requested = False
        self.stats_requested = False
        self._warned_ports = set()

    # -- virtual pads -------------------------------------------------------

    def _new_pad(self, name, product):
        axis = self.evdev.AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)
        events = {
            evcodes.EV_KEY: sorted(VIRTUAL_BUTTONS.values()),
            # OutFox's Linux input code (from StepMania 5.1) ignores devices
            # without an X axis, so the pads carry two idle axes.
            evcodes.EV_ABS: [(evcodes.ABS_X, axis), (evcodes.ABS_Y, axis)],
        }
        return self.evdev.UInput(
            events, name=name, vendor=VIRTUAL_VENDOR, product=product, version=1, bustype=evcodes.BUS_USB
        )

    def _sysnames(self, pad):
        event = os.path.basename(pad.device.path)
        return (sysfs.input_sysname(event), event)

    def create_pads(self):
        """Create P1 then P2, retrying until P1 sorts first by every rule."""
        placeholders = []
        try:
            for _ in range(MAX_ORDER_ATTEMPTS):
                pads = {n: self._new_pad(VIRTUAL_NAME.format(n), VIRTUAL_PRODUCTS[n]) for n in (1, 2)}
                names = {n: self._sysnames(pad) for n, pad in pads.items()}
                if all(sorts_before(a, b) for a, b in zip(names[1], names[2])):
                    self.log(f"virtual pads ready: P1={'/'.join(names[1])} P2={'/'.join(names[2])}")
                    return pads
                for pad in pads.values():
                    pad.close()
                # Hold the next numbers so the retry lands on same-length names.
                placeholders.append(self._new_pad("pi-DDR placeholder", PLACEHOLDER_PRODUCT))
            raise RuntimeError("could not create the virtual pads in P1, P2 order")
        finally:
            for placeholder in placeholders:
                placeholder.close()

    # -- physical mats ------------------------------------------------------

    def _note(self, player, message):
        if player.last_note != message:
            player.last_note = message
            self.log(f"{player.label}: {message}")

    def connect(self, player):
        path = player.config.device
        if not os.path.exists(path):
            self._note(player, f"waiting for mat at {path}")
            return False
        try:
            dev = self.evdev.InputDevice(path)
        except OSError as e:
            self._note(player, f"cannot open {path}: {e.strerror or e}")
            return False
        try:
            dev.grab()
        except OSError as e:
            dev.close()
            self._note(player, f"cannot grab {path}: {e.strerror or e} (is matprobe running?)")
            return False
        absinfo = dict(dev.capabilities(absinfo=True).get(evcodes.EV_ABS, []))
        player.mapper.set_abs_ranges({code: (info.min, info.max) for code, info in absinfo.items()})
        player.dev = dev
        player.dropped = False
        values = {code: info.value for code, info in absinfo.items()}
        self._send(player, player.mapper.reset(dev.active_keys(), values, self.clock()))
        self.selector.register(dev, selectors.EVENT_READ, player)
        info = dev.info
        self._note(player, f"mat connected: {dev.name!r} ({info.vendor:04x}:{info.product:04x}) at {path}")
        return True

    def disconnect(self, player, reason):
        dev, player.dev = player.dev, None
        if dev is None:
            return
        try:
            self.selector.unregister(dev)
        except (KeyError, ValueError):
            pass
        try:
            dev.close()
        except OSError:
            pass
        self._send(player, player.mapper.release_all())
        self._note(player, f"mat disconnected ({reason}); its arrows were released")

    def pump(self, player):
        """Forward everything the mat has sent since the last call."""
        try:
            events = list(player.dev.read())
        except BlockingIOError:
            return
        except OSError as e:
            reason = "unplugged" if e.errno == errno.ENODEV else (e.strerror or str(e))
            self.disconnect(player, reason)
            return
        for ev in events:
            if ev.type == evcodes.EV_SYN:
                if ev.code == evcodes.SYN_DROPPED:
                    player.dropped = True
                elif ev.code == evcodes.SYN_REPORT:
                    self._report(player, ev)
            elif not player.dropped:
                player.mapper.feed(ev.type, ev.code, ev.value)

    def _report(self, player, ev):
        now = self.clock()
        if player.dropped:
            # The kernel queue overflowed: rebuild the state from the device.
            player.dropped = False
            dev = player.dev
            values = {code: dev.absinfo(code).value for code in player.mapper.abs_codes}
            changes = player.mapper.reset(dev.active_keys(), values, now)
        else:
            changes = player.mapper.flush(now)
        if changes:
            self._send(player, changes)
            self.delays.add(self.wallclock() - ev.timestamp())

    def _send(self, player, changes):
        if not changes:
            return
        for code, value in changes:
            player.pad.write(evcodes.EV_KEY, code, value)
        player.pad.syn()

    def _warn_stray_mats(self):
        """Point out a mat that is plugged into a port nobody is configured for."""
        if not self.config.mat_ids:
            return
        configured = {os.path.realpath(p.config.device) for p in self.players}
        for link in glob.glob("/dev/input/by-path/*-event-joystick"):
            target = os.path.realpath(link)
            if target in configured or link in self._warned_ports:
                continue
            info = sysfs.describe_event_device(os.path.basename(target))
            if (info["vid"], info["pid"]) in self.config.mat_ids:
                self._warned_ports.add(link)
                self.log(
                    f"a mat is plugged into a port that is not P1 or P2: {link}. "
                    "Move it to its labelled port, or re-run `matprobe learn`."
                )

    # -- main loop ----------------------------------------------------------

    def start(self):
        self.pads = self.create_pads()
        debounce = self.config.release_debounce_ms / 1000.0
        self.players = [Player(cfg, self.pads[cfg.number], debounce) for cfg in self.config.players]

    def run(self):
        self.start()
        gc.freeze()  # keep the long-lived setup objects out of garbage collection passes
        interval = self.config.stats_interval_s
        next_scan = 0.0
        next_stats = self.clock() + interval if interval > 0 else float("inf")
        while not self.stop_requested:
            now = self.clock()
            if now >= next_scan:
                missing = [p for p in self.players if p.dev is None]
                for player in missing:
                    self.connect(player)
                if missing:
                    self._warn_stray_mats()
                next_scan = now + RESCAN_INTERVAL
            deadlines = [next_scan, next_stats]
            deadlines += [d for d in (p.mapper.next_deadline() for p in self.players) if d is not None]
            for key, _ in self.selector.select(max(0.0, min(deadlines) - now)):
                self.pump(key.data)
            now = self.clock()
            for player in self.players:
                self._send(player, player.mapper.expire(now))
            if self.stats_requested or now >= next_stats:
                self.stats_requested = False
                self.log(f"forwarding delay (mat report to virtual pad): {self.delays.summary()}")
                next_stats = now + interval if interval > 0 else float("inf")
        self.close()

    def close(self):
        for player in self.players:
            self._send(player, player.mapper.release_all())
            if player.dev is not None:
                try:
                    player.dev.close()
                except OSError:
                    pass
                player.dev = None
        for pad in self.pads.values():
            pad.close()
        self.pads = {}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m piddr.padbridge",
        description="Expose two USB dance mats as stable virtual pads 'pi-DDR P1' and 'pi-DDR P2'.",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"config file (default {DEFAULT_CONFIG})")
    parser.add_argument("--check", action="store_true", help="validate the config and exit")
    parser.add_argument(
        "--print-udev-rules", action="store_true", help="print the udev rules that hide the raw mats, then exit"
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (OSError, ConfigError) as e:
        print(f"padbridge: {args.config}: {e}", file=sys.stderr)
        return 2

    if args.print_udev_rules:
        if not config.mat_ids:
            print("padbridge: mat_ids is empty; run `matprobe learn` first", file=sys.stderr)
            return 2
        sys.stdout.write(udev_rules(config.mat_ids))
        return 0
    if args.check:
        for player in config.players:
            controls = ", ".join(player.mapping)
            print(f"P{player.number}: {player.device}\n    controls: {controls}")
        print(f"release_debounce_ms={config.release_debounce_ms:g} mat_ids={config.mat_ids}")
        return 0

    bridge = Bridge(config, evcodes.require_evdev())

    def request_stop(signum, frame):
        bridge.stop_requested = True

    def request_stats(signum, frame):
        bridge.stats_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGUSR1, request_stats)
    bridge.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
