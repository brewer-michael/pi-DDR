"""pi-DDR pad bridge: two physical mats in, one virtual stage out.

OutFox reads joysticks through SDL and names them Joy1, Joy2, ... in the
order it opens them, which follows the order Linux registered the devices.
Two identical mats can therefore swap between boots, and a replugged mat
comes back as a new device. This daemon hides the raw mats and gives the game
a single virtual joystick, "pi-DDR Stage": P1's mat drives buttons 1-11 and
P2's mat buttons 12-22, each taken from one fixed USB port. Which player is
which is decided by button number, so device order never matters, and the
stage never goes away, even when a mat is unplugged mid-song.

Runs as the systemd service pi-ddr-padbridge (see pi/padbridge/).
"""

import argparse
import errno
import gc
import glob
import os
import selectors
import signal
import socket
import sys
import time

import evdev

from . import evcodes, sysfs
from .config import ConfigError, load_config, udev_rules
from .mapping import STAGE_BUTTONS, Mapper
from .timing import DelayStats

DEFAULT_CONFIG = "/etc/pi-ddr/padbridge.conf"
VIRTUAL_VENDOR = 0x1209  # pid.codes vendor; this device never appears on a real bus
VIRTUAL_PRODUCT = 0x0001
VIRTUAL_NAME = "pi-DDR Stage"
RESCAN_INTERVAL = 1.0


def notify_systemd(message=b"READY=1"):
    """Tell systemd (Type=notify) the virtual stage exists. No-op outside systemd.

    The unit orders the tty1 autologin that starts the game after this, so the
    stage is already there when OutFox opens its joysticks at startup.
    """
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return False
    if address.startswith("@"):
        address = "\0" + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.connect(address)
        sock.sendall(message)
    return True


def _close_quietly(dev):
    try:
        dev.close()
    except OSError:
        pass


class Player:
    def __init__(self, config, pad, release_debounce):
        self.config = config
        self.pad = pad  # the shared virtual stage
        self.mapper = Mapper(config.mapping, release_debounce=release_debounce, player=config.number)
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
        self.pad = None
        self.stop_requested = False
        self.stats_requested = False
        self._warned_ports = set()
        self._last_links = None

    # -- the virtual stage ---------------------------------------------------

    def create_stage(self):
        """Create the one joystick the game sees, with both players' buttons."""
        axis = self.evdev.AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)
        events = {
            evcodes.EV_KEY: list(STAGE_BUTTONS),
            # Two idle axes: SDL's own check (SDL_EVDEV_GuessDeviceClass) only
            # counts an input device as a joystick if it has ABS_X and ABS_Y.
            # With them, udev, the kernel's joydev and SDL all agree it is one.
            evcodes.EV_ABS: [(evcodes.ABS_X, axis), (evcodes.ABS_Y, axis)],
        }
        stage = self.evdev.UInput(
            events, name=VIRTUAL_NAME, vendor=VIRTUAL_VENDOR, product=VIRTUAL_PRODUCT, version=1, bustype=evcodes.BUS_USB
        )
        nodes = [os.path.basename(stage.device.path), *self._joystick_nodes(stage)]
        self.log(f"virtual stage ready: {VIRTUAL_NAME!r} ({', '.join(nodes)})")
        return stage

    def _joystick_nodes(self, stage):
        """The classic joystick node (jsN) of the stage, which OutFox reads by default."""
        event = os.path.basename(stage.device.path)
        return sysfs.joystick_nodes(sysfs.input_sysname(event))

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
            _close_quietly(dev)
            self._note(player, f"cannot grab {path}: {e.strerror or e} (is matprobe running?)")
            return False
        try:
            absinfo = dict(dev.capabilities(absinfo=True).get(evcodes.EV_ABS, []))
            keys = dev.active_keys()
        except OSError as e:
            _close_quietly(dev)
            self._note(player, f"lost {path} while connecting: {e.strerror or e}")
            return False
        player.mapper.set_abs_ranges({code: (info.min, info.max) for code, info in absinfo.items()})
        player.dev = dev
        player.dropped = False
        values = {code: info.value for code, info in absinfo.items()}
        self._send(player, player.mapper.reset(keys, values, self.clock()))
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
        _close_quietly(dev)
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
                elif ev.code == evcodes.SYN_REPORT and not self._report(player, ev):
                    return
            elif not player.dropped:
                player.mapper.feed(ev.type, ev.code, ev.value)

    def _report(self, player, ev):
        """Forward one report. Returns False if the mat vanished meanwhile."""
        now = self.clock()
        if player.dropped:
            # The kernel queue overflowed: rebuild the state from the device.
            player.dropped = False
            dev = player.dev
            try:
                values = {code: dev.absinfo(code).value for code in player.mapper.abs_codes}
                keys = dev.active_keys()
            except OSError as e:
                self.disconnect(player, e.strerror or str(e))
                return False
            changes = player.mapper.reset(keys, values, now)
        else:
            changes = player.mapper.flush(now)
        if changes:
            self._send(player, changes)
            self.delays.add(self.wallclock() - ev.timestamp())
        return True

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
        links = {link: os.path.realpath(link) for link in glob.glob("/dev/input/by-path/*-event-joystick")}
        if links == self._last_links:
            return  # nothing plugged or unplugged since the last look
        self._last_links = links
        self._warned_ports &= set(links)  # a mat that leaves and comes back is reported again
        configured = {os.path.realpath(p.config.device) for p in self.players}
        for link, target in links.items():
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
        self.pad = self.create_stage()
        debounce = self.config.release_debounce_ms / 1000.0
        self.players = [Player(cfg, self.pad, debounce) for cfg in self.config.players]

    def run(self):
        self.start()
        notify_systemd()
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
                self.log(f"forwarding delay (mat report to virtual stage): {self.delays.summary()}")
                next_stats = now + interval if interval > 0 else float("inf")
        self.close()

    def close(self):
        for player in self.players:
            self._send(player, player.mapper.release_all())
            if player.dev is not None:
                _close_quietly(player.dev)
                player.dev = None
        if self.pad is not None:
            self.pad.close()
            self.pad = None


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m piddr.padbridge",
        description="Expose two USB dance mats to the game as one virtual joystick, 'pi-DDR Stage'.",
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

    bridge = Bridge(config, evdev)

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
